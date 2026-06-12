"""
Stripe Checkout Routes
======================
Handles creation of Stripe Checkout sessions for subscriptions and
one-time credit purchases.

SECURITY:
- ALL session-creating endpoints require a valid Supabase JWT
  (Authorization: Bearer). The user_id is ALWAYS taken from the token,
  never from the request body.
- Credit pack prices are defined server-side (config.stripe_config.CREDIT_PACKS).
  The client can only pick a pack, never a price.

Endpoints:
- POST /api/stripe/create-checkout     (auth) canonical subscription checkout
- POST /api/create-checkout-session    (auth) alias to the same logic
- POST /api/stripe/buy-credits         (auth) one-time credit pack purchase
- GET  /api/stripe/prices              (public) price list
"""

import os
import stripe
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.stripe_config import get_stripe_config, get_plan_type, CREDIT_PACKS
from services.supabase_service import get_user_profile
from utils.auth import get_authenticated_user_id


router = APIRouter(prefix="/api", tags=["checkout"])

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Frontend URL (canonical domain)
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://vykso.com")

# Stripe Tax: only enabled when explicitly configured in the dashboard
STRIPE_AUTOMATIC_TAX = os.getenv("STRIPE_AUTOMATIC_TAX", "false").strip().lower() == "true"

# Legacy plan aliases accepted in the request body -> new taxonomy.
# 'pro' et 'max' étaient des plans CREATOR dans l'ancienne taxonomie (65,99/89,99 €)
# — même mapping que la migration SQL. Les plans professionnels legacy passaient
# par 'starter' ou par price_id direct.
_PLAN_ALIASES = {
    "starter": "professional_starter",
    "basic": "creator_basic",
    "pro": "creator_pro",
    "max": "creator_max",
}


class CheckoutRequest(BaseModel):
    """Request model for creating a subscription checkout session.

    Provide either `price_id` (a configured Stripe price) or `plan`
    (a plan name from the taxonomy) + optional `interval`.
    user_id/user_email in the body are IGNORED — identity comes from the JWT.
    """
    price_id: Optional[str] = None
    plan: Optional[str] = None
    interval: Optional[str] = "monthly"


class CheckoutResponse(BaseModel):
    """Response model for checkout session"""
    url: str
    session_id: str
    checkout_url: str  # alias of url, kept for frontend compatibility


class BuyCreditsRequest(BaseModel):
    """Request model for one-time credit purchase.

    `pack` is the ONLY accepted field: 60, 120 or 300 credits.
    The price is determined server-side from CREDIT_PACKS.
    """
    pack: Literal[60, 120, 300]


def _apply_tax_settings(session_params: dict):
    """Add billing address collection and (optionally) Stripe Tax settings."""
    session_params["billing_address_collection"] = "required"
    if STRIPE_AUTOMATIC_TAX:
        session_params["automatic_tax"] = {"enabled": True}
        session_params["tax_id_collection"] = {"enabled": True}


def _resolve_price_id(req: CheckoutRequest) -> str:
    """Resolve and validate the Stripe price ID from the request body."""
    config = get_stripe_config()

    price_id: Optional[str] = None

    if req.price_id:
        price_id = req.price_id
    elif req.plan:
        plan = _PLAN_ALIASES.get(req.plan, req.plan)
        interval = req.interval or "monthly"
        price_id = config.get_price_id_for_plan(plan, interval)
        if not price_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid plan: {req.plan}. Valid plans: creator_basic, creator_pro, "
                    f"creator_max, professional_starter, professional_pro, professional_max"
                ),
            )
    else:
        raise HTTPException(status_code=400, detail="Either 'plan' or 'price_id' is required")

    # Validate against the configured price IDs (never trust the client)
    if not config.is_valid_price_id(price_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid price ID. Must be one of the configured Stripe prices.",
        )

    return price_id


async def _create_subscription_checkout(request: Request, req: CheckoutRequest) -> CheckoutResponse:
    """Shared subscription checkout logic (authenticated)."""
    # 1. Authentication — the user_id ALWAYS comes from the JWT
    user_id = await get_authenticated_user_id(request)

    # 2. The user's profile must exist before we sell them anything
    profile = get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    # 3. Resolve and validate the price
    price_id = _resolve_price_id(req)

    config = get_stripe_config()
    plan_info = get_plan_type(price_id)
    if not plan_info:
        raise HTTPException(status_code=400, detail="Could not determine plan type from price ID")

    plan_name = config.get_plan_name_from_price_id(price_id)

    metadata = {
        "user_id": user_id,
        "plan": plan_name,
        "plan_family": plan_info["plan_family"],
        "interval": plan_info["interval"],
        "credits": str(plan_info["credits"]),
        "type": "subscription",
    }

    try:
        session_params = {
            "mode": "subscription",
            "line_items": [{
                "price": price_id,
                "quantity": 1,
            }],
            "success_url": f"{FRONTEND_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{FRONTEND_URL}/payment-cancelled",
            "allow_promotion_codes": True,
            "client_reference_id": user_id,
            "metadata": metadata,
            "subscription_data": {
                "metadata": metadata,
            },
        }

        # Pre-fill the email from the verified profile (never from the body)
        if profile.get("email"):
            session_params["customer_email"] = profile["email"]

        _apply_tax_settings(session_params)

        session = stripe.checkout.Session.create(**session_params)

        print(f"✅ Checkout session created: {session.id}")
        print(f"   User: {user_id}")
        print(f"   Plan: {plan_info['name']} ({plan_info['plan_family']}, {plan_info['interval']})")
        print(f"   Credits: {plan_info['credits']}")

        return CheckoutResponse(
            url=session.url,
            session_id=session.id,
            checkout_url=session.url,
        )

    except stripe.error.StripeError as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=502, detail="Stripe error while creating checkout session")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating checkout session: {e}")
        raise HTTPException(status_code=500, detail="Error creating checkout session")


@router.post("/stripe/create-checkout", response_model=CheckoutResponse)
async def create_checkout(req: CheckoutRequest, request: Request):
    """
    Canonical subscription checkout endpoint (used by the frontend).

    Requires Authorization: Bearer <supabase JWT>.
    Body: {plan} (new taxonomy or legacy alias) or {price_id}, optional {interval}.
    """
    return await _create_subscription_checkout(request, req)


@router.post("/create-checkout-session", response_model=CheckoutResponse)
async def create_checkout_session(req: CheckoutRequest, request: Request):
    """
    Alias of /api/stripe/create-checkout, kept for frontend compatibility.
    Same auth, same logic.
    """
    return await _create_subscription_checkout(request, req)


@router.post("/stripe/buy-credits")
async def buy_credits(req: BuyCreditsRequest, request: Request):
    """
    Buy credits as a one-time purchase (no subscription).

    Requires Authorization: Bearer <supabase JWT>.
    Body: {"pack": 60 | 120 | 300}. Any other value -> 422.
    The price is taken from CREDIT_PACKS server-side — the client can
    NEVER set the amount.
    """
    # 1. Authentication — the user_id ALWAYS comes from the JWT
    user_id = await get_authenticated_user_id(request)

    # 2. The user's profile must exist
    profile = get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    # 3. Server-side price (pack already validated by the Literal type -> 422)
    credits = req.pack
    amount_eur = CREDIT_PACKS[credits]

    try:
        session_params = {
            "mode": "payment",
            "line_items": [{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"{credits} Vykso Credits",
                        "description": f"{credits // 6} videos of 60s",
                    },
                    "unit_amount": amount_eur * 100,  # cents
                },
                "quantity": 1,
            }],
            "success_url": f"{FRONTEND_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{FRONTEND_URL}/payment-cancelled",
            "client_reference_id": user_id,
            "metadata": {
                "user_id": user_id,
                "credits": str(credits),
                "type": "credit_purchase",
            },
        }

        if profile.get("email"):
            session_params["customer_email"] = profile["email"]

        _apply_tax_settings(session_params)

        session = stripe.checkout.Session.create(**session_params)

        print(f"✅ Credit purchase session created: {session.id}")
        print(f"   User: {user_id} — pack: {credits} credits / {amount_eur} EUR")

        return {"checkout_url": session.url, "url": session.url, "session_id": session.id}

    except stripe.error.StripeError as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=502, detail="Stripe error while creating checkout session")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating buy-credits session: {e}")
        raise HTTPException(status_code=500, detail="Error creating checkout session")


@router.get("/stripe/prices")
async def get_available_prices():
    """
    Get all available subscription prices (PUBLIC — it's a price list).
    Exposes only price IDs, plan names, intervals, credits and prices —
    nothing sensitive.
    """
    config = get_stripe_config()

    def public_plan_entry(key: str, price_id: str) -> Optional[dict]:
        plan_info = get_plan_type(price_id)
        if not plan_info:
            return None
        return {
            "priceId": price_id,
            "key": key,
            "plan": plan_info["plan"],
            "interval": plan_info["interval"],
            "credits": plan_info["credits"],
            "planFamily": plan_info["plan_family"],
            "name": plan_info["name"],
            "price_monthly": plan_info["price_monthly"],
            "price_yearly": plan_info["price_yearly"],
        }

    creator_prices = []
    for key, price_id in config.get_creator_price_ids().items():
        if price_id:
            entry = public_plan_entry(key, price_id)
            if entry:
                creator_prices.append(entry)

    professional_prices = []
    for key, price_id in config.get_professional_price_ids().items():
        if price_id:
            entry = public_plan_entry(key, price_id)
            if entry:
                professional_prices.append(entry)

    return {
        "creator": creator_prices,
        "professional": professional_prices,
        "credit_packs": [
            {"credits": credits, "price": price, "currency": "EUR"}
            for credits, price in CREDIT_PACKS.items()
        ],
    }
