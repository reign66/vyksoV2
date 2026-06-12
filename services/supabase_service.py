"""
Supabase Service Module
=======================
Handles all Supabase database operations for subscription management.

Uses SUPABASE_SERVICE_ROLE_KEY for server-side operations.

Functions:
- updateUserSubscription: Upsert subscription data
- addCreditsToUser: Increment user credits
- notifyPaymentFailed: Send payment failure notification
- getUserByStripeSubscription: Find user by subscription ID
- logWebhookEvent: Log webhook events for debugging
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
from supabase import create_client, Client


# =============================================
# SUPABASE CLIENT
# =============================================

_supabase_client: Optional[Client] = None


def get_supabase_service() -> Client:
    """
    Get Supabase client with service role key.
    
    Uses SUPABASE_SERVICE_ROLE_KEY for elevated permissions
    required for server-side operations.
    """
    global _supabase_client
    
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            raise ValueError("Missing Supabase credentials (SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        
        _supabase_client = create_client(url, key)
    
    return _supabase_client


# =============================================
# SUBSCRIPTION MANAGEMENT
# =============================================

def update_user_subscription(user_id: str, data: Dict[str, Any]) -> bool:
    """
    Update or create user subscription data.
    
    Args:
        user_id: The user's ID
        data: Dictionary containing subscription fields:
            - stripe_customer_id: Stripe customer ID
            - stripe_subscription_id: Stripe subscription ID
            - price_id: Stripe price ID
            - status: Subscription status ('active', 'canceled', etc.)
            - plan: Internal plan name
            - plan_tier: Plan tier ('basic', 'pro', 'max', etc.)
            - plan_interval: Billing interval ('monthly', 'yearly', 'annual')
            - plan_family: Plan family ('creator' or 'professional')
            - credits: Number of credits
            - current_period_end: ISO timestamp of period end
            - canceled_at: ISO timestamp of cancellation (optional)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_service()
        
        # Build update data with only provided fields
        update_data = {}
        
        field_mapping = {
            'stripe_customer_id': 'stripe_customer_id',
            'stripe_subscription_id': 'stripe_subscription_id',
            'price_id': 'price_id',
            'status': 'subscription_status',
            'plan': 'plan',
            'plan_tier': 'plan_tier',
            'plan_interval': 'plan_interval',
            'plan_family': 'plan_family',
            'credits': 'credits',
            'current_period_end': 'current_period_end',
            'canceled_at': 'canceled_at',
        }
        
        for key, db_field in field_mapping.items():
            if key in data:
                update_data[db_field] = data[key]
        
        # Add updated_at timestamp
        update_data['updated_at'] = datetime.utcnow().isoformat()
        
        # Update the profiles table
        result = supabase.table("profiles").update(update_data).eq("id", user_id).execute()

        if result.data:
            print(f"✅ Updated subscription for user {user_id}")
            print(f"   Fields updated: {list(update_data.keys())}")
            return True
        else:
            # CRITICAL: no profile row matched -> the caller MUST treat this
            # as a hard failure (webhook returns 500 so Stripe retries),
            # otherwise we get "paid but never credited".
            print(f"❌ update_user_subscription: no profile row found for user {user_id} — update NOT applied")
            return False

    except Exception as e:
        print(f"❌ Error updating subscription for user {user_id}: {e}")
        return False


def add_credits_to_user(user_id: str, credits: int) -> bool:
    """
    Add credits to a user's account ATOMICALLY via the `add_credits` RPC
    (no read-modify-write race). The RPC also logs the credit_transactions row.

    Args:
        user_id: The user's ID
        credits: Number of credits to add

    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_service()

        # Atomic increment in the database (SECURITY DEFINER function).
        # add_credits raises / returns NULL if the user does not exist.
        result = supabase.rpc("add_credits", {
            "p_user_id": user_id,
            "p_amount": credits,
        }).execute()

        new_total = result.data
        if new_total is None:
            print(f"❌ add_credits RPC: user {user_id} not found, no credits added")
            return False

        print(f"✅ Added {credits} credits to user {user_id} (total: {new_total})")
        return True

    except Exception as e:
        print(f"❌ Error adding credits to user {user_id}: {e}")
        return False


def log_credit_transaction(user_id: str, amount: int, transaction_type: str, description: str):
    """
    Log a credit transaction for audit purposes.

    NOTE: the credit_transactions column is `type` (NOT `transaction_type`).

    Args:
        user_id: The user's ID
        amount: Amount of credits (positive for add, negative for use)
        transaction_type: Type of transaction ('purchase', 'subscription', 'usage', 'refund')
        description: Human-readable description
    """
    try:
        supabase = get_supabase_service()

        supabase.table("credit_transactions").insert({
            "user_id": user_id,
            "amount": amount,
            "type": transaction_type,
            "description": description,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

    except Exception as e:
        # Table might not exist, just log the error
        print(f"ℹ️ Could not log credit transaction: {e}")


# =============================================
# USER LOOKUP
# =============================================

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a user's profile row by id.

    Args:
        user_id: The user's ID (profiles.id == auth.users.id)

    Returns:
        Profile dictionary or None if not found.
    """
    try:
        supabase = get_supabase_service()

        result = supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute()

        if result.data:
            return result.data[0]
        return None

    except Exception as e:
        print(f"❌ Error fetching profile for user {user_id}: {e}")
        return None


def get_user_by_stripe_subscription(subscription_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a user by their Stripe subscription ID.
    
    Args:
        subscription_id: The Stripe subscription ID
    
    Returns:
        User data dictionary or None if not found
    """
    try:
        supabase = get_supabase_service()
        
        result = supabase.table("profiles").select("*").eq(
            "stripe_subscription_id", subscription_id
        ).single().execute()
        
        return result.data if result.data else None
    
    except Exception as e:
        print(f"❌ Error finding user by subscription {subscription_id}: {e}")
        return None


def get_user_by_stripe_customer(customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a user by their Stripe customer ID.
    
    Args:
        customer_id: The Stripe customer ID
    
    Returns:
        User data dictionary or None if not found
    """
    try:
        supabase = get_supabase_service()
        
        result = supabase.table("profiles").select("*").eq(
            "stripe_customer_id", customer_id
        ).single().execute()
        
        return result.data if result.data else None
    
    except Exception as e:
        print(f"❌ Error finding user by customer {customer_id}: {e}")
        return None


# =============================================
# NOTIFICATIONS
# =============================================

def notify_payment_failed(
    user_id: str,
    email: Optional[str],
    invoice_url: Optional[str],
    amount: float,
    currency: str
):
    """
    Notify a user that their payment has failed.
    
    This function can be extended to:
    - Send an email via SendGrid, Resend, or other email service
    - Create an in-app notification
    - Send a Slack/Discord alert
    
    Args:
        user_id: The user's ID
        email: User's email address
        invoice_url: Stripe hosted invoice URL for payment retry
        amount: Amount that failed to charge
        currency: Currency code (e.g., 'EUR')
    """
    try:
        supabase = get_supabase_service()
        
        # Log the payment failure
        notification_data = {
            "user_id": user_id,
            "type": "payment_failed",
            "title": "Échec de paiement",
            "message": f"Votre paiement de {amount} {currency} a échoué. Veuillez mettre à jour vos informations de paiement.",
            "action_url": invoice_url,
            "read": False,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Try to insert into notifications table if it exists
        try:
            supabase.table("notifications").insert(notification_data).execute()
            print(f"📬 Payment failure notification created for user {user_id}")
        except Exception:
            # Table might not exist
            pass
        
        # Log for monitoring
        print(f"📧 Payment failed notification for user {user_id}")
        print(f"   Email: {email}")
        print(f"   Amount: {amount} {currency}")
        print(f"   Invoice URL: {invoice_url}")

        # External notification channel (best effort — never raises)
        try:
            from utils.notify import notify_event
            notify_event("payment_failed", {
                "user_id": user_id,
                "email": email,
                "amount": amount,
                "currency": currency,
                "invoice_url": invoice_url,
            })
        except ImportError:
            pass  # utils.notify not deployed yet — in-app notification above still works
        except Exception as notify_err:
            print(f"⚠️ notify_event failed (non-blocking): {notify_err}")

    except Exception as e:
        print(f"❌ Error sending payment failure notification: {e}")


# =============================================
# WEBHOOK LOGGING / IDEMPOTENCY
# =============================================

def claim_webhook_event(event_id: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> bool:
    """
    Idempotency claim for a Stripe webhook event (insert-first strategy).

    Inserts a row into webhook_logs, which has a UNIQUE index on event_id.
    - Insert succeeds  -> we own this event, process it (returns True)
    - Unique violation -> the event was already received, skip (returns False)

    Any other database error is re-raised so the webhook returns 500 and
    Stripe retries (we must NOT silently process without an idempotency claim).

    Args:
        event_id: Stripe event ID (evt_...)
        event_type: Stripe event type
        data: Optional event data object (summarized for the log)

    Returns:
        True if the event was claimed (process it), False if duplicate.
    """
    supabase = get_supabase_service()

    data = data or {}
    log_entry = {
        "event_type": event_type,
        "event_id": event_id,
        "timestamp": datetime.utcnow().isoformat(),
        "data_summary": json.dumps({
            "id": data.get("id"),
            "object": data.get("object"),
            "status": data.get("status"),
            "customer": data.get("customer"),
            "subscription": data.get("subscription"),
        }),
    }

    try:
        supabase.table("webhook_logs").insert(log_entry).execute()
        print(f"📝 Claimed webhook event: {event_type} ({event_id})")
        return True
    except Exception as e:
        # Detect PostgREST unique-violation (PostgreSQL error code 23505)
        err_code = getattr(e, "code", None)
        err_text = str(e)
        if err_code == "23505" or "23505" in err_text or "duplicate key" in err_text.lower():
            print(f"🔁 Duplicate webhook event, skipping: {event_type} ({event_id})")
            return False
        # Real DB error: re-raise so the webhook 500s and Stripe retries
        raise


def release_webhook_event(event_id: str):
    """
    Release an idempotency claim after a processing FAILURE so that
    Stripe's retry of the same event can be claimed and processed again.
    Best effort — never raises.
    """
    try:
        supabase = get_supabase_service()
        supabase.table("webhook_logs").delete().eq("event_id", event_id).execute()
        print(f"↩️ Released webhook claim for {event_id} (processing failed, retry allowed)")
    except Exception as e:
        print(f"⚠️ Could not release webhook claim {event_id}: {e}")


def set_cancel_at_period_end(user_id: str, value: bool) -> bool:
    """
    Best-effort persistence of Stripe's cancel_at_period_end flag.
    The profiles column may not exist yet — in that case we only log.
    Never raises.
    """
    try:
        supabase = get_supabase_service()
        supabase.table("profiles").update({
            "cancel_at_period_end": value,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", user_id).execute()
        print(f"📝 cancel_at_period_end={value} stored for user {user_id}")
        return True
    except Exception as e:
        print(f"ℹ️ Could not persist cancel_at_period_end for user {user_id} "
              f"(column may not exist): {e}")
        return False


def log_webhook_event(event_type: str, event_id: str, data: Dict[str, Any]):
    """
    Log a webhook event for debugging and audit purposes.
    
    Args:
        event_type: Type of Stripe event
        event_id: Stripe event ID
        data: Event data object
    """
    try:
        supabase = get_supabase_service()
        
        # Extract relevant info for logging
        log_entry = {
            "event_type": event_type,
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data_summary": json.dumps({
                "id": data.get("id"),
                "object": data.get("object"),
                "status": data.get("status"),
                "customer": data.get("customer"),
                "subscription": data.get("subscription"),
            })
        }
        
        # Try to insert into webhook_logs table if it exists
        try:
            supabase.table("webhook_logs").insert(log_entry).execute()
        except Exception:
            # Table might not exist, just print log
            pass
        
        print(f"📝 Logged webhook: {event_type} ({event_id})")
        
    except Exception as e:
        print(f"⚠️ Error logging webhook event: {e}")


# =============================================
# SUBSCRIPTION STATUS HELPERS
# =============================================

def cancel_subscription(user_id: str, immediate: bool = False) -> bool:
    """
    Mark a subscription as canceled in the database.
    
    Args:
        user_id: The user's ID
        immediate: If True, set credits to 0 immediately
    
    Returns:
        True if successful, False otherwise
    """
    try:
        update_data = {
            'status': 'canceled',
            'canceled_at': datetime.utcnow().isoformat(),
        }
        
        if immediate:
            update_data['credits'] = 0
            update_data['plan'] = 'free'
        
        return update_user_subscription(user_id, update_data)
    
    except Exception as e:
        print(f"❌ Error canceling subscription for user {user_id}: {e}")
        return False


def reactivate_subscription(user_id: str, plan: str, credits: int) -> bool:
    """
    Reactivate a subscription for a user.
    
    Args:
        user_id: The user's ID
        plan: New plan name
        credits: Credits to set
    
    Returns:
        True if successful, False otherwise
    """
    try:
        return update_user_subscription(user_id, {
            'status': 'active',
            'plan': plan,
            'credits': credits,
            'canceled_at': None,
        })
    
    except Exception as e:
        print(f"❌ Error reactivating subscription for user {user_id}: {e}")
        return False
