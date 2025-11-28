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
            print(f"⚠️ No user found with ID {user_id}")
            return False
    
    except Exception as e:
        print(f"❌ Error updating subscription for user {user_id}: {e}")
        return False


def add_credits_to_user(user_id: str, credits: int) -> bool:
    """
    Add credits to a user's account.
    
    Args:
        user_id: The user's ID
        credits: Number of credits to add
    
    Returns:
        True if successful, False otherwise
    """
    try:
        supabase = get_supabase_service()
        
        # First get current credits
        user = supabase.table("profiles").select("credits").eq("id", user_id).single().execute()
        
        if not user.data:
            print(f"❌ User {user_id} not found")
            return False
        
        current_credits = user.data.get('credits', 0)
        new_credits = current_credits + credits
        
        # Update credits
        result = supabase.table("profiles").update({
            "credits": new_credits,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
        
        if result.data:
            print(f"✅ Added {credits} credits to user {user_id} (total: {new_credits})")
            
            # Log the credit addition
            log_credit_transaction(user_id, credits, "purchase", f"Credit purchase: +{credits}")
            
            return True
        
        return False
    
    except Exception as e:
        print(f"❌ Error adding credits to user {user_id}: {e}")
        return False


def log_credit_transaction(user_id: str, amount: int, transaction_type: str, description: str):
    """
    Log a credit transaction for audit purposes.
    
    Args:
        user_id: The user's ID
        amount: Amount of credits (positive for add, negative for use)
        transaction_type: Type of transaction ('purchase', 'subscription', 'usage', 'refund')
        description: Human-readable description
    """
    try:
        supabase = get_supabase_service()
        
        # Try to insert into credit_transactions table if it exists
        supabase.table("credit_transactions").insert({
            "user_id": user_id,
            "amount": amount,
            "transaction_type": transaction_type,
            "description": description,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
    except Exception as e:
        # Table might not exist, just log the error
        print(f"ℹ️ Could not log credit transaction (table may not exist): {e}")


# =============================================
# USER LOOKUP
# =============================================

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
        
        # TODO: Integrate with email service
        # Example with SendGrid:
        # send_email(
        #     to=email,
        #     subject="Échec de paiement - Action requise",
        #     template="payment_failed",
        #     data={
        #         "amount": amount,
        #         "currency": currency,
        #         "invoice_url": invoice_url
        #     }
        # )
        
    except Exception as e:
        print(f"❌ Error sending payment failure notification: {e}")


# =============================================
# WEBHOOK LOGGING
# =============================================

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
