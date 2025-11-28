"""
Stripe Webhook Handler
======================
Handles all Stripe webhook events for subscription management.

IMPORTANT: This route MUST be registered BEFORE express.json() middleware
to receive the raw body for signature verification.

Events handled:
- checkout.session.completed: Initial subscription creation
- customer.subscription.updated: Plan changes
- customer.subscription.deleted: Subscription cancellation
- invoice.payment_succeeded: Renewal and credit recharge
- invoice.payment_failed: Payment failure notification
"""

import os
import stripe
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Request

from config.stripe_config import get_stripe_config, get_plan_type
from services.supabase_service import (
    update_user_subscription,
    add_credits_to_user,
    notify_payment_failed,
    get_user_by_stripe_subscription,
    log_webhook_event
)


router = APIRouter(tags=["webhook"])

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Main Stripe webhook handler.
    
    CRITICAL: This endpoint receives raw body for signature verification.
    
    Events handled:
    1. checkout.session.completed - New subscription
    2. customer.subscription.updated - Plan changes
    3. customer.subscription.deleted - Cancellation
    4. invoice.payment_succeeded - Renewal/recharge
    5. invoice.payment_failed - Payment failure
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    # Verify webhook signature
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
    timestamp = datetime.utcnow().isoformat()
    
    print(f"📨 [{timestamp}] Received Stripe webhook: {event_type} (ID: {event_id})")
    
    # Log all events
    try:
        log_webhook_event(event_type, event_id, event['data']['object'])
    except Exception as e:
        print(f"⚠️ Failed to log webhook event: {e}")
    
    try:
        # Handle different event types
        if event_type == 'checkout.session.completed':
            await handle_checkout_completed(event['data']['object'])
        
        elif event_type == 'customer.subscription.updated':
            await handle_subscription_updated(event['data']['object'])
        
        elif event_type == 'customer.subscription.deleted':
            await handle_subscription_deleted(event['data']['object'])
        
        elif event_type == 'invoice.payment_succeeded':
            await handle_payment_succeeded(event['data']['object'])
        
        elif event_type == 'invoice.payment_failed':
            await handle_payment_failed(event['data']['object'])
        
        else:
            print(f"ℹ️ Unhandled event type: {event_type}")
        
        # Always return 200 to prevent Stripe retries
        return {"status": "success", "event_type": event_type}
    
    except Exception as e:
        print(f"❌ Error processing webhook {event_type}: {e}")
        import traceback
        traceback.print_exc()
        # Still return 200 to prevent infinite retries
        # Log the error for investigation
        return {"status": "error", "event_type": event_type, "error": str(e)}


async def handle_checkout_completed(session: dict):
    """
    Handle checkout.session.completed event.
    
    Steps:
    1. Get subscriptionId and userId from metadata
    2. Fetch full subscription from Stripe
    3. Extract priceId from subscription
    4. Use getPlanType() to get plan info
    5. Create/update user in Supabase
    """
    config = get_stripe_config()
    
    metadata = session.get('metadata', {})
    user_id = metadata.get('userId') or metadata.get('user_id')
    subscription_id = session.get('subscription')
    customer_id = session.get('customer')
    
    if not user_id:
        print("❌ No user_id in checkout session metadata")
        return
    
    # Handle one-time credit purchase
    if metadata.get('type') == 'credit_purchase':
        credits_to_add = int(metadata.get('credits', 0))
        print(f"💳 Credit purchase: {credits_to_add} credits for user {user_id}")
        
        add_credits_to_user(user_id, credits_to_add)
        print(f"✅ Added {credits_to_add} credits to user {user_id}")
        return
    
    # Handle subscription
    if not subscription_id:
        print("⚠️ No subscription in checkout session")
        return
    
    # Fetch full subscription from Stripe
    subscription = stripe.Subscription.retrieve(subscription_id)
    price_id = subscription['items']['data'][0]['price']['id']
    
    # Get plan info
    plan_info = get_plan_type(price_id)
    if not plan_info:
        print(f"⚠️ Unknown price ID: {price_id}")
        plan_info = {
            'tier': metadata.get('tier', 'unknown'),
            'interval': metadata.get('interval', 'monthly'),
            'credits': int(metadata.get('credits', 100)),
            'planFamily': metadata.get('planFamily', 'creator'),
            'name': 'Unknown Plan'
        }
    
    plan_name = config.get_plan_name_from_price_id(price_id)
    
    # Calculate current period end
    current_period_end = datetime.fromtimestamp(
        subscription['current_period_end']
    ).isoformat()
    
    print(f"✅ New subscription for user {user_id}")
    print(f"   Plan: {plan_info['name']} ({plan_info['planFamily']})")
    print(f"   Tier: {plan_info['tier']}")
    print(f"   Credits: {plan_info['credits']}")
    
    # Update user in Supabase
    update_user_subscription(
        user_id=user_id,
        data={
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': subscription_id,
            'price_id': price_id,
            'status': 'active',
            'plan': plan_name or plan_info['tier'],
            'plan_tier': plan_info['tier'],
            'plan_interval': plan_info['interval'],
            'plan_family': plan_info['planFamily'],
            'credits': plan_info['credits'],
            'current_period_end': current_period_end,
        }
    )


async def handle_subscription_updated(subscription: dict):
    """
    Handle customer.subscription.updated event.
    
    Steps:
    1. Get userId from subscription metadata
    2. Extract new priceId
    3. Update plan and credits if changed
    """
    config = get_stripe_config()
    
    metadata = subscription.get('metadata', {})
    user_id = metadata.get('userId') or metadata.get('user_id')
    
    if not user_id:
        # Try to find user by subscription ID
        user = get_user_by_stripe_subscription(subscription['id'])
        if user:
            user_id = user.get('id')
    
    if not user_id:
        print(f"⚠️ No user found for subscription {subscription['id']}")
        return
    
    # Get new price ID
    price_id = subscription['items']['data'][0]['price']['id']
    status = subscription['status']
    
    # Get plan info
    plan_info = get_plan_type(price_id)
    if not plan_info:
        print(f"⚠️ Unknown price ID in subscription update: {price_id}")
        return
    
    plan_name = config.get_plan_name_from_price_id(price_id)
    
    # Calculate current period end
    current_period_end = datetime.fromtimestamp(
        subscription['current_period_end']
    ).isoformat()
    
    print(f"📝 Subscription updated for user {user_id}")
    print(f"   New plan: {plan_info['name']}")
    print(f"   Status: {status}")
    
    # Update user in Supabase
    update_data = {
        'price_id': price_id,
        'status': status,
        'plan': plan_name or plan_info['tier'],
        'plan_tier': plan_info['tier'],
        'plan_interval': plan_info['interval'],
        'plan_family': plan_info['planFamily'],
        'current_period_end': current_period_end,
    }
    
    # Only update credits if plan changed (not on simple status update)
    if status == 'active':
        update_data['credits'] = plan_info['credits']
    
    update_user_subscription(user_id=user_id, data=update_data)


async def handle_subscription_deleted(subscription: dict):
    """
    Handle customer.subscription.deleted event.
    
    Steps:
    1. Get userId from metadata
    2. Update status to 'canceled'
    3. Set credits to 0
    4. Record canceledAt timestamp
    """
    metadata = subscription.get('metadata', {})
    user_id = metadata.get('userId') or metadata.get('user_id')
    
    if not user_id:
        # Try to find user by subscription ID
        user = get_user_by_stripe_subscription(subscription['id'])
        if user:
            user_id = user.get('id')
    
    if not user_id:
        print(f"⚠️ No user found for canceled subscription {subscription['id']}")
        return
    
    canceled_at = datetime.utcnow().isoformat()
    
    print(f"🚫 Subscription canceled for user {user_id}")
    
    # Update user in Supabase
    update_user_subscription(
        user_id=user_id,
        data={
            'status': 'canceled',
            'credits': 0,
            'canceled_at': canceled_at,
            'plan': 'free',
        }
    )


async def handle_payment_succeeded(invoice: dict):
    """
    Handle invoice.payment_succeeded event.
    
    Steps:
    1. Check if this is a renewal (billing_reason === 'subscription_cycle')
    2. If renewal: recredited user based on their plan
    3. Log the operation
    """
    config = get_stripe_config()
    
    subscription_id = invoice.get('subscription')
    billing_reason = invoice.get('billing_reason')
    
    if not subscription_id:
        print("ℹ️ No subscription in invoice (one-time payment)")
        return
    
    # Get user by subscription
    user = get_user_by_stripe_subscription(subscription_id)
    if not user:
        print(f"⚠️ No user found for subscription {subscription_id}")
        return
    
    user_id = user.get('id')
    current_plan = user.get('plan', 'free')
    
    # Check if this is a renewal
    if billing_reason == 'subscription_cycle':
        print(f"🔄 Subscription renewal for user {user_id}")
        
        # Get credits for the plan
        credits = config.get_credits_for_plan(current_plan)
        if credits == 0:
            # Try to get from subscription
            subscription = stripe.Subscription.retrieve(subscription_id)
            price_id = subscription['items']['data'][0]['price']['id']
            plan_info = get_plan_type(price_id)
            if plan_info:
                credits = plan_info['credits']
        
        if credits > 0:
            # Recharge credits
            update_user_subscription(
                user_id=user_id,
                data={'credits': credits}
            )
            print(f"✅ Recharged {credits} credits for user {user_id} (plan: {current_plan})")
        else:
            print(f"⚠️ Could not determine credits for plan {current_plan}")
    
    elif billing_reason == 'subscription_create':
        print(f"ℹ️ Initial subscription payment for user {user_id}")
    
    else:
        print(f"ℹ️ Payment succeeded (reason: {billing_reason}) for user {user_id}")


async def handle_payment_failed(invoice: dict):
    """
    Handle invoice.payment_failed event.
    
    Steps:
    1. Get userId from subscription
    2. Notify user by email
    3. Log the failure
    """
    subscription_id = invoice.get('subscription')
    
    if not subscription_id:
        print("ℹ️ No subscription in failed invoice")
        return
    
    # Get user by subscription
    user = get_user_by_stripe_subscription(subscription_id)
    if not user:
        print(f"⚠️ No user found for subscription {subscription_id}")
        return
    
    user_id = user.get('id')
    user_email = user.get('email')
    
    print(f"❌ Payment failed for user {user_id}")
    
    # Get payment update link from hosted invoice URL
    hosted_invoice_url = invoice.get('hosted_invoice_url')
    
    # Notify user
    notify_payment_failed(
        user_id=user_id,
        email=user_email,
        invoice_url=hosted_invoice_url,
        amount=invoice.get('amount_due', 0) / 100,  # Convert from cents
        currency=invoice.get('currency', 'eur').upper()
    )
    
    print(f"📧 Payment failure notification sent to {user_email}")
