"""
Stripe Checkout Routes
======================
Handles creation of Stripe Checkout sessions for subscriptions.

Supports both PROFESSIONAL and CREATOR tier plans with monthly and yearly billing.
"""

import os
import stripe
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.stripe_config import get_stripe_config, get_plan_type


router = APIRouter(prefix="/api", tags=["checkout"])

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Frontend URL
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://vykso.lovable.app")


class CheckoutRequest(BaseModel):
    """Request model for creating a checkout session"""
    price_id: str
    user_id: str
    user_email: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Response model for checkout session"""
    url: str
    session_id: str


class BuyCreditsRequest(BaseModel):
    """Request model for one-time credit purchase"""
    user_id: str
    credits: int
    amount: int  # Amount in EUR


@router.post("/create-checkout-session", response_model=CheckoutResponse)
async def create_checkout_session(req: CheckoutRequest, request: Request):
    """
    Create a Stripe Checkout Session for subscription.
    
    Supports all plan types:
    - PROFESSIONAL: starter, pro, max (monthly and annual)
    - CREATOR: basic, pro, max (monthly and yearly)
    
    Input:
    - priceId: Stripe price ID
    - userId: User ID for metadata
    - userEmail: Optional email for customer
    
    Returns:
    - url: Checkout session URL
    - sessionId: Session ID for reference
    """
    config = get_stripe_config()
    
    # Validate that the priceId exists in our configuration
    if not config.is_valid_price_id(req.price_id):
        valid_ids = config.get_all_valid_price_ids()
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid price ID. Must be one of the configured Stripe prices."
        )
    
    # Get plan information
    plan_info = get_plan_type(req.price_id)
    if not plan_info:
        raise HTTPException(status_code=400, detail="Could not determine plan type from price ID")
    
    plan_name = config.get_plan_name_from_price_id(req.price_id)
    
    try:
        # Build checkout session parameters
        session_params = {
            "mode": "subscription",
            "line_items": [{
                "price": req.price_id,
                "quantity": 1,
            }],
            "success_url": f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{FRONTEND_URL}/pricing",
            "allow_promotion_codes": True,
            "metadata": {
                "userId": req.user_id,
                "plan": plan_name,
                "tier": plan_info['tier'],
                "planFamily": plan_info['planFamily'],
                "interval": plan_info['interval'],
                "credits": str(plan_info['credits']),
            },
            "subscription_data": {
                "metadata": {
                    "userId": req.user_id,
                    "plan": plan_name,
                    "tier": plan_info['tier'],
                    "planFamily": plan_info['planFamily'],
                    "interval": plan_info['interval'],
                    "credits": str(plan_info['credits']),
                }
            },
        }
        
        # Add customer email if provided
        if req.user_email:
            session_params["customer_email"] = req.user_email
        
        # Create the checkout session
        session = stripe.checkout.Session.create(**session_params)
        
        print(f"✅ Checkout session created: {session.id}")
        print(f"   Plan: {plan_info['name']} ({plan_info['planFamily']})")
        print(f"   Interval: {plan_info['interval']}")
        print(f"   Credits: {plan_info['credits']}")
        
        return CheckoutResponse(
            url=session.url,
            session_id=session.id
        )
    
    except stripe.error.StripeError as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"❌ Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stripe/create-checkout")
async def create_checkout_legacy(req: dict, request: Request):
    """
    Legacy endpoint for backward compatibility.
    Converts plan name to price ID and creates checkout session.
    
    Input:
    - plan: Plan name (e.g., 'creator_basic', 'pro', 'starter')
    - user_id: User ID
    - interval: Optional, 'monthly' or 'yearly'/'annual'
    """
    config = get_stripe_config()
    
    plan = req.get("plan")
    user_id = req.get("user_id")
    interval = req.get("interval", "monthly")
    
    if not plan or not user_id:
        raise HTTPException(status_code=400, detail="plan and user_id are required")
    
    # Determine price ID from plan name
    price_id = None
    
    # Creator plans
    if plan == "creator_basic":
        price_id = config.PRICE_BASIC_YEARLY if interval in ["yearly", "annual"] else config.PRICE_BASIC_MONTHLY
    elif plan == "creator_pro":
        price_id = config.PRICE_PRO_YEARLY if interval in ["yearly", "annual"] else config.PRICE_PRO_MONTHLY
    elif plan == "creator_max":
        price_id = config.PRICE_MAX_YEARLY if interval in ["yearly", "annual"] else config.PRICE_MAX_MONTHLY
    # Professional plans
    elif plan == "starter":
        price_id = config.PRICE_STARTER_ANNUAL if interval in ["yearly", "annual"] else config.PRICE_STARTER
    elif plan == "pro":
        price_id = config.PRICE_PRO_ANNUAL if interval in ["yearly", "annual"] else config.PRICE_PRO
    elif plan == "max":
        price_id = config.PRICE_MAX_ANNUAL if interval in ["yearly", "annual"] else config.PRICE_MAX
    
    if not price_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid plan: {plan}. Valid plans: creator_basic, creator_pro, creator_max, starter, pro, max"
        )
    
    # Get plan info for metadata
    plan_info = get_plan_type(price_id)
    plan_name = config.get_plan_name_from_price_id(price_id)
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{FRONTEND_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/pricing",
            allow_promotion_codes=True,
            client_reference_id=user_id,
            metadata={
                'user_id': user_id,
                'plan': plan_name,
                'tier_type': plan_info['planFamily'] if plan_info else 'unknown',
                'type': 'subscription'
            }
        )
        
        return {"checkout_url": session.url}
    
    except Exception as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stripe/buy-credits")
async def buy_credits(req: BuyCreditsRequest, request: Request):
    """
    Buy credits as a one-time purchase (no subscription).
    
    Available packs:
    - 60 credits: 9 EUR
    - 120 credits: 15 EUR
    - 300 credits: 29 EUR
    """
    # Basic validation
    if req.credits <= 0 or req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid credits or amount")
    
    # Define valid credit packs
    packs = {
        60: 9,    # 60 credits -> 9 EUR
        120: 15,  # 120 credits -> 15 EUR
        300: 29,  # 300 credits -> 29 EUR
    }
    
    # Validate pack
    if req.credits in packs and packs[req.credits] != req.amount:
        raise HTTPException(status_code=400, detail="Invalid amount for selected credits pack")
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f'{req.credits} Vykso Credits',
                        'description': f'{req.credits // 6} videos of 60s'
                    },
                    'unit_amount': req.amount * 100  # Convert to cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{FRONTEND_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/credits",
            client_reference_id=req.user_id,
            metadata={
                'user_id': req.user_id,
                'credits': str(req.credits),
                'type': 'credit_purchase'
            }
        )
        
        return {"checkout_url": session.url}
    
    except Exception as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stripe/prices")
async def get_available_prices():
    """
    Get all available subscription prices.
    Useful for frontend to display pricing options.
    """
    config = get_stripe_config()
    
    creator_prices = []
    professional_prices = []
    
    # Build creator prices
    creator_ids = config.get_creator_price_ids()
    for key, price_id in creator_ids.items():
        if price_id:
            plan_info = get_plan_type(price_id)
            if plan_info:
                creator_prices.append({
                    "priceId": price_id,
                    "key": key,
                    **plan_info
                })
    
    # Build professional prices
    professional_ids = config.get_professional_price_ids()
    for key, price_id in professional_ids.items():
        if price_id:
            plan_info = get_plan_type(price_id)
            if plan_info:
                professional_prices.append({
                    "priceId": price_id,
                    "key": key,
                    **plan_info
                })
    
    return {
        "creator": creator_prices,
        "professional": professional_prices,
        "credit_packs": [
            {"credits": 60, "price": 9, "currency": "EUR"},
            {"credits": 120, "price": 15, "currency": "EUR"},
            {"credits": 300, "price": 29, "currency": "EUR"},
        ]
    }
