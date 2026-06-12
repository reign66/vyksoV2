"""
Stripe Webhook Handler
======================
Single, complete Stripe webhook handler for the API
(the legacy handler in main.py is removed — this file is the only one).

Guarantees:
- Signature verification (STRIPE_WEBHOOK_SECRET)
- Idempotency: events are claimed in webhook_logs (UNIQUE on event_id)
  BEFORE processing. Duplicates return 200 {"status": "duplicate"}.
- Error semantics: unhandled event types return 200; REAL processing
  failures raise 500 so Stripe retries (the claim is released on failure
  so the retry can be processed).

Events handled:
- checkout.session.completed: new subscription / one-time credit purchase
- customer.subscription.updated: plan change, cancel_at_period_end, status
- customer.subscription.deleted: downgrade to free
- invoice.payment_succeeded: monthly credit refill (subscription_cycle only)
- invoice.payment_failed: notification, no credit change
"""

import os
import stripe
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request

from config.stripe_config import get_stripe_config, get_plan_type
from services.supabase_service import (
    update_user_subscription,
    add_credits_to_user,
    log_credit_transaction,
    notify_payment_failed,
    get_user_profile,
    get_user_by_stripe_subscription,
    get_user_by_stripe_customer,
    claim_webhook_event,
    release_webhook_event,
    set_cancel_at_period_end,
)


router = APIRouter(tags=["webhook"])

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


class WebhookProcessingError(Exception):
    """A real processing failure: the webhook must return 500 so Stripe retries."""


def _notify(event: str, details: dict):
    """Best-effort external notification — NEVER breaks the webhook."""
    try:
        from utils.notify import notify_event
        notify_event(event, details)
    except ImportError:
        pass  # utils.notify not deployed yet
    except Exception as e:
        print(f"⚠️ notify_event('{event}') failed (non-blocking): {e}")


def _extract_price_id(subscription: dict) -> Optional[str]:
    """Defensively extract the price ID from a Stripe subscription object."""
    try:
        items = subscription.get('items') or {}
        data = items.get('data') or []
        if not data:
            return None
        price = data[0].get('price') or {}
        return price.get('id')
    except Exception:
        return None


def _period_end_iso(subscription: dict) -> Optional[str]:
    """Defensively convert current_period_end (unix ts) to ISO, or None."""
    ts = subscription.get('current_period_end')
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _subscription_id_from_invoice(invoice: dict) -> Optional[str]:
    """Invoice.subscription can be a string ID or an expanded object."""
    sub = invoice.get('subscription')
    if isinstance(sub, dict):
        return sub.get('id')
    return sub


@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Main (and only) Stripe webhook handler.

    Flow:
    1. Verify signature (raw body)
    2. Claim the event in webhook_logs (idempotency) — duplicate -> 200
    3. Dispatch to the handler — unhandled type -> 200
    4. Real failure -> release the claim + 500 (Stripe retries safely)
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    # 1. Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        print(f"❌ Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event['type']
    event_id = event['id']
    data_object = event['data']['object']

    print(f"📨 [{datetime.utcnow().isoformat()}] Stripe webhook: {event_type} (ID: {event_id})")

    # 2. Idempotency claim FIRST (insert into webhook_logs, UNIQUE on event_id)
    try:
        claimed = claim_webhook_event(event_id, event_type, data_object)
    except Exception as e:
        print(f"❌ Could not claim webhook event {event_id}: {e}")
        raise HTTPException(status_code=500, detail="Webhook idempotency store unavailable")

    if not claimed:
        return {"status": "duplicate", "event_type": event_type, "event_id": event_id}

    # 3. Dispatch
    try:
        if event_type == 'checkout.session.completed':
            await handle_checkout_completed(data_object)

        elif event_type == 'customer.subscription.updated':
            await handle_subscription_updated(data_object)

        elif event_type == 'customer.subscription.deleted':
            await handle_subscription_deleted(data_object)

        elif event_type == 'invoice.payment_succeeded':
            await handle_payment_succeeded(data_object)

        elif event_type == 'invoice.payment_failed':
            await handle_payment_failed(data_object)

        else:
            # Unknown/unhandled event types are acknowledged with 200
            print(f"ℹ️ Unhandled event type: {event_type}")
            return {"status": "ignored", "event_type": event_type}

        return {"status": "success", "event_type": event_type}

    except HTTPException:
        release_webhook_event(event_id)
        raise
    except Exception as e:
        # 4. REAL processing failure: release the claim and let Stripe retry
        print(f"❌ Error processing webhook {event_type} ({event_id}): {e}")
        import traceback
        traceback.print_exc()
        release_webhook_event(event_id)
        raise HTTPException(
            status_code=500,
            detail=f"Webhook processing failed for {event_type}",
        )


async def handle_checkout_completed(session: dict):
    """
    Handle checkout.session.completed.

    - mode=subscription: set plan (new taxonomy), plan_family, credits,
      stripe IDs, current_period_end.
    - metadata.type=credit_purchase: add credits atomically via add_credits RPC.
    """
    config = get_stripe_config()

    metadata = session.get('metadata') or {}
    user_id = (
        metadata.get('user_id')
        or metadata.get('userId')
        or session.get('client_reference_id')
    )
    subscription_id = session.get('subscription')
    customer_id = session.get('customer')

    if not user_id:
        # Cannot be fixed by a retry — log loudly but acknowledge
        print(f"❌ checkout.session.completed without user_id (session {session.get('id')})")
        _notify("webhook_missing_user", {
            "event": "checkout.session.completed",
            "session_id": session.get('id'),
        })
        return

    # ----- One-time credit purchase -----
    if metadata.get('type') == 'credit_purchase':
        try:
            credits_to_add = int(metadata.get('credits') or 0)
        except (TypeError, ValueError):
            credits_to_add = 0

        if credits_to_add <= 0:
            raise WebhookProcessingError(
                f"credit_purchase with invalid credits metadata: {metadata.get('credits')!r}"
            )

        print(f"💳 Credit purchase: {credits_to_add} credits for user {user_id}")

        # Atomic increment (add_credits RPC) — NOT read-modify-write
        if not add_credits_to_user(user_id, credits_to_add):
            raise WebhookProcessingError(
                f"Failed to add {credits_to_add} credits to user {user_id}"
            )

        _notify("credit_purchase", {
            "user_id": user_id,
            "credits": credits_to_add,
            "session_id": session.get('id'),
        })
        print(f"✅ Added {credits_to_add} credits to user {user_id}")
        return

    # ----- Subscription checkout -----
    if not subscription_id:
        print("⚠️ checkout.session.completed without subscription (and not a credit purchase) — ignored")
        return

    # Fetch full subscription from Stripe
    subscription = stripe.Subscription.retrieve(subscription_id)
    price_id = _extract_price_id(subscription)
    if not price_id:
        raise WebhookProcessingError(
            f"Could not extract price_id from subscription {subscription_id}"
        )

    plan_info = get_plan_type(price_id)
    plan_name = config.get_plan_name_from_price_id(price_id)

    if not plan_info or not plan_name:
        raise WebhookProcessingError(
            f"Unknown price ID {price_id} on subscription {subscription_id} — "
            f"check STRIPE_PRICE_* env configuration"
        )

    update_data = {
        'stripe_customer_id': customer_id,
        'stripe_subscription_id': subscription_id,
        'price_id': price_id,
        'status': 'active',
        'plan': plan_name,
        'plan_tier': plan_info['plan'],
        'plan_interval': plan_info['interval'],
        'plan_family': plan_info['plan_family'],
        'credits': plan_info['credits'],
    }

    period_end = _period_end_iso(subscription)
    if period_end:
        update_data['current_period_end'] = period_end

    print(f"✅ New subscription for user {user_id}")
    print(f"   Plan: {plan_name} ({plan_info['plan_family']}, {plan_info['interval']})")
    print(f"   Credits: {plan_info['credits']}")

    # If the profile row is missing this returns False -> 500 -> Stripe retries.
    # NO "paid but never credited" black hole.
    if not update_user_subscription(user_id=user_id, data=update_data):
        raise WebhookProcessingError(
            f"Failed to apply subscription to profile {user_id} (profile missing?)"
        )

    log_credit_transaction(
        user_id, plan_info['credits'], 'subscription',
        f"New subscription {plan_name}: {plan_info['credits']} credits"
    )

    _notify("new_subscription", {
        "user_id": user_id,
        "plan": plan_name,
        "plan_family": plan_info['plan_family'],
        "interval": plan_info['interval'],
        "credits": plan_info['credits'],
        "subscription_id": subscription_id,
    })


def _find_user_id_for_subscription(subscription: dict) -> Optional[str]:
    """Resolve our user_id from a Stripe subscription object."""
    metadata = subscription.get('metadata') or {}
    user_id = metadata.get('user_id') or metadata.get('userId')
    if user_id:
        return user_id

    user = get_user_by_stripe_subscription(subscription.get('id'))
    if user:
        return user.get('id')

    customer_id = subscription.get('customer')
    if customer_id:
        user = get_user_by_stripe_customer(customer_id)
        if user:
            return user.get('id')

    return None


async def handle_subscription_updated(subscription: dict):
    """
    Handle customer.subscription.updated.

    Rules:
    - cancel_at_period_end=true -> store the flag, DO NOT touch credits.
    - status past_due/unpaid -> DO NOT recharge, send a notification.
    - price_id changed (real plan change) -> update plan + reset credits.
    - anything else (status/payment-method updates) -> metadata only,
      credits untouched.
    """
    config = get_stripe_config()

    user_id = _find_user_id_for_subscription(subscription)
    if not user_id:
        print(f"⚠️ No user found for subscription {subscription.get('id')} — ignored")
        return

    new_price_id = _extract_price_id(subscription)
    status = subscription.get('status')
    period_end = _period_end_iso(subscription)

    # Base metadata update (never includes credits)
    base_update = {}
    if status:
        base_update['status'] = status
    if period_end:
        base_update['current_period_end'] = period_end

    # --- Scheduled cancellation: store the flag, never touch credits ---
    cancel_at_period_end = bool(subscription.get('cancel_at_period_end'))
    set_cancel_at_period_end(user_id, cancel_at_period_end)  # best effort
    if cancel_at_period_end:
        print(f"🗓️ Subscription {subscription.get('id')} will cancel at period end (user {user_id})")
        if base_update and not update_user_subscription(user_id=user_id, data=base_update):
            raise WebhookProcessingError(f"Failed to update profile {user_id} (cancel_at_period_end)")
        _notify("subscription_cancel_scheduled", {
            "user_id": user_id,
            "subscription_id": subscription.get('id'),
            "current_period_end": period_end,
        })
        return

    # --- Payment trouble: never recharge ---
    if status in ('past_due', 'unpaid'):
        print(f"⚠️ Subscription {subscription.get('id')} is {status} for user {user_id} — no credit change")
        if base_update and not update_user_subscription(user_id=user_id, data=base_update):
            raise WebhookProcessingError(f"Failed to update profile {user_id} (status {status})")
        _notify("subscription_payment_trouble", {
            "user_id": user_id,
            "subscription_id": subscription.get('id'),
            "status": status,
        })
        return

    # --- Detect a REAL plan change by comparing the stored price_id ---
    profile = get_user_profile(user_id)
    stored_price_id = (profile or {}).get('price_id')

    if new_price_id and new_price_id != stored_price_id:
        plan_info = get_plan_type(new_price_id)
        plan_name = config.get_plan_name_from_price_id(new_price_id)

        if not plan_info or not plan_name:
            raise WebhookProcessingError(
                f"Unknown price ID {new_price_id} in subscription update — "
                f"check STRIPE_PRICE_* env configuration"
            )

        print(f"📝 Plan change for user {user_id}: {stored_price_id} -> {new_price_id} ({plan_name})")

        update_data = dict(base_update)
        update_data.update({
            'price_id': new_price_id,
            'plan': plan_name,
            'plan_tier': plan_info['plan'],
            'plan_interval': plan_info['interval'],
            'plan_family': plan_info['plan_family'],
            'credits': plan_info['credits'],  # reset ONLY on plan change
        })

        if not update_user_subscription(user_id=user_id, data=update_data):
            raise WebhookProcessingError(f"Failed to apply plan change to profile {user_id}")

        log_credit_transaction(
            user_id, plan_info['credits'], 'subscription',
            f"Plan change to {plan_name}: credits reset to {plan_info['credits']}"
        )
        return

    # --- Plain status / payment-method update: metadata only, credits untouched ---
    print(f"📝 Subscription metadata update for user {user_id} (status: {status}) — credits untouched")
    if base_update and not update_user_subscription(user_id=user_id, data=base_update):
        raise WebhookProcessingError(f"Failed to update profile {user_id} (metadata update)")


async def handle_subscription_deleted(subscription: dict):
    """
    Handle customer.subscription.deleted:
    plan='free', plan_family='creator', credits=0, clear stripe_subscription_id.
    """
    user_id = _find_user_id_for_subscription(subscription)
    if not user_id:
        print(f"⚠️ No user found for canceled subscription {subscription.get('id')} — ignored")
        return

    print(f"🚫 Subscription canceled for user {user_id}")

    if not update_user_subscription(
        user_id=user_id,
        data={
            'status': 'canceled',
            'plan': 'free',
            'plan_family': 'creator',
            'credits': 0,
            'stripe_subscription_id': None,
            'canceled_at': datetime.utcnow().isoformat(),
        }
    ):
        raise WebhookProcessingError(f"Failed to downgrade profile {user_id} after cancellation")

    set_cancel_at_period_end(user_id, False)  # best effort, flag no longer relevant

    _notify("subscription_cancelled", {
        "user_id": user_id,
        "subscription_id": subscription.get('id'),
    })


async def handle_payment_succeeded(invoice: dict):
    """
    Handle invoice.payment_succeeded.

    Credits are refilled ONLY for billing_reason == 'subscription_cycle'
    (monthly/annual renewal). Initial payments are handled by
    checkout.session.completed.
    """
    config = get_stripe_config()

    subscription_id = _subscription_id_from_invoice(invoice)
    billing_reason = invoice.get('billing_reason')

    if not subscription_id:
        print("ℹ️ No subscription in invoice (one-time payment) — handled by checkout.session.completed")
        return

    if billing_reason != 'subscription_cycle':
        print(f"ℹ️ invoice.payment_succeeded (reason: {billing_reason}) — no credit refill")
        return

    user = get_user_by_stripe_subscription(subscription_id)
    if not user:
        print(f"⚠️ No user found for subscription {subscription_id} — ignored")
        return

    user_id = user.get('id')
    current_plan = user.get('plan') or 'free'

    print(f"🔄 Subscription renewal for user {user_id} (plan: {current_plan})")

    # Lookup by stored plan name (new taxonomy)
    credits = config.get_credits_for_plan(current_plan)

    # Fallback: re-derive from the Stripe subscription's price_id
    if credits == 0:
        subscription = stripe.Subscription.retrieve(subscription_id)
        price_id = _extract_price_id(subscription)
        plan_info = get_plan_type(price_id) if price_id else None
        if plan_info:
            credits = plan_info['credits']

    if credits <= 0:
        # A paid renewal we cannot credit IS a real failure: 500 -> Stripe retries
        # and the team is alerted before the customer notices.
        _notify("renewal_credit_failure", {
            "user_id": user_id,
            "plan": current_plan,
            "subscription_id": subscription_id,
        })
        raise WebhookProcessingError(
            f"Could not determine renewal credits for user {user_id} (plan: {current_plan})"
        )

    if not update_user_subscription(user_id=user_id, data={'credits': credits, 'status': 'active'}):
        raise WebhookProcessingError(f"Failed to refill {credits} credits for user {user_id}")

    log_credit_transaction(
        user_id, credits, 'subscription',
        f"Renewal refill ({current_plan}): credits set to {credits}"
    )
    print(f"✅ Refilled {credits} credits for user {user_id} (plan: {current_plan})")


async def handle_payment_failed(invoice: dict):
    """
    Handle invoice.payment_failed: notify (in-app + notify_event), NO credit change.
    """
    subscription_id = _subscription_id_from_invoice(invoice)

    if not subscription_id:
        print("ℹ️ No subscription in failed invoice — ignored")
        return

    user = get_user_by_stripe_subscription(subscription_id)
    if not user:
        print(f"⚠️ No user found for subscription {subscription_id} — ignored")
        return

    user_id = user.get('id')
    user_email = user.get('email')

    print(f"❌ Payment failed for user {user_id}")

    # In-app notification + notify_event channel (best effort, never raises)
    notify_payment_failed(
        user_id=user_id,
        email=user_email,
        invoice_url=invoice.get('hosted_invoice_url'),
        amount=(invoice.get('amount_due') or 0) / 100,  # cents -> EUR
        currency=(invoice.get('currency') or 'eur').upper(),
    )

    print(f"📧 Payment failure notification sent for user {user_id}")
