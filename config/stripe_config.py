"""
Stripe Configuration Module
============================
Manages all Stripe price IDs and plan configurations for both
PROFESSIONAL and CREATOR tier plans.

Plan taxonomy (profiles.plan) — unique names, identical for monthly/annual:
- creator_basic (100), creator_pro (200), creator_max (300)
- professional_starter (600), professional_pro (1200), professional_max (1800)

profiles.plan_family: 'creator' | 'professional'

Environment Variables (price IDs):
- PROFESSIONAL plans: STRIPE_PRICE_STARTER(_ANNUAL), STRIPE_PRICE_PRO(_ANNUAL),
  STRIPE_PRICE_MAX(_ANNUAL)
- CREATOR plans: STRIPE_PRICE_BASIC_MONTHLY/_YEARLY, STRIPE_PRICE_PRO_MONTHLY/_YEARLY,
  STRIPE_PRICE_MAX_MONTHLY/_YEARLY
"""

import os
import logging
from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass

logger = logging.getLogger("vykso.stripe_config")


# =============================================
# CREDIT PACKS (one-time purchases)
# Single source of truth: {credits: price_eur}
# =============================================
CREDIT_PACKS: Dict[int, int] = {
    60: 9,    # 60 credits  -> 9 EUR
    120: 15,  # 120 credits -> 15 EUR
    300: 29,  # 300 credits -> 29 EUR
}


# =============================================
# PLAN CREDITS (subscriptions)
# Keyed by the unique plan names (new taxonomy)
# =============================================
PLAN_CREDITS: Dict[str, int] = {
    "creator_basic": 100,
    "creator_pro": 200,
    "creator_max": 300,
    "professional_starter": 600,
    "professional_pro": 1200,
    "professional_max": 1800,
}


def get_stripe_mode() -> str:
    """
    Return the Stripe mode based on the secret key prefix.

    Returns:
        'live'    if STRIPE_SECRET_KEY starts with sk_live_ / rk_live_
        'test'    if it starts with sk_test_ / rk_test_
        'missing' if the key is absent or unrecognized
    """
    key = os.getenv("STRIPE_SECRET_KEY") or ""
    if key.startswith("sk_live_") or key.startswith("rk_live_"):
        return "live"
    if key.startswith("sk_test_") or key.startswith("rk_test_"):
        return "test"
    return "missing"


@dataclass
class PlanInfo:
    """Information about a subscription plan"""
    plan: str  # Unique plan name (new taxonomy), e.g. 'creator_pro', 'professional_max'
    interval: Literal['monthly', 'yearly', 'annual']
    credits: int
    plan_family: Literal['creator', 'professional']
    name: str
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None

    @property
    def tier(self) -> str:
        """Backward-compat alias: the tier IS the unique plan name now."""
        return self.plan


class StripeConfig:
    """
    Centralized Stripe configuration class.

    Manages all price IDs for both PROFESSIONAL and CREATOR tier plans.

    PROFESSIONAL Plans (for ads/commercials):
    - professional_starter: 199EUR/month or 179EUR/month yearly (600 credits)
    - professional_pro: 589EUR/month or 530EUR/month yearly (1200 credits)
    - professional_max: 1199EUR/month or 1079EUR/month yearly (1800 credits)

    CREATOR Plans (for TikTok/YouTube Shorts):
    - creator_basic: 34.99EUR/month or 31.49EUR/month yearly (100 credits)
    - creator_pro: 65.99EUR/month or 59.39EUR/month yearly (200 credits)
    - creator_max: 89.99EUR/month or 80.99EUR/month yearly (300 credits)
    """

    def __init__(self):
        # =============================================
        # PROFESSIONAL TIER PRICE IDs
        # =============================================
        self.PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER")              # professional_starter monthly
        self.PRICE_STARTER_ANNUAL = os.getenv("STRIPE_PRICE_STARTER_ANNUAL")  # professional_starter annual
        self.PRICE_PRO = os.getenv("STRIPE_PRICE_PRO")                      # professional_pro monthly
        self.PRICE_PRO_ANNUAL = os.getenv("STRIPE_PRICE_PRO_ANNUAL")        # professional_pro annual
        self.PRICE_MAX = os.getenv("STRIPE_PRICE_MAX")                      # professional_max monthly
        self.PRICE_MAX_ANNUAL = os.getenv("STRIPE_PRICE_MAX_ANNUAL")        # professional_max annual

        # =============================================
        # CREATOR TIER PRICE IDs
        # =============================================
        self.PRICE_BASIC_MONTHLY = os.getenv("STRIPE_PRICE_BASIC_MONTHLY")  # creator_basic monthly
        self.PRICE_BASIC_YEARLY = os.getenv("STRIPE_PRICE_BASIC_YEARLY")    # creator_basic yearly
        self.PRICE_PRO_MONTHLY = os.getenv("STRIPE_PRICE_PRO_MONTHLY")      # creator_pro monthly
        self.PRICE_PRO_YEARLY = os.getenv("STRIPE_PRICE_PRO_YEARLY")        # creator_pro yearly
        self.PRICE_MAX_MONTHLY = os.getenv("STRIPE_PRICE_MAX_MONTHLY")      # creator_max monthly
        self.PRICE_MAX_YEARLY = os.getenv("STRIPE_PRICE_MAX_YEARLY")        # creator_max yearly

        # =============================================
        # CREDITS MAPPING (unique plan names only)
        # =============================================
        self.ALL_CREDITS = dict(PLAN_CREDITS)

        # Credit packs (single source of truth, module-level constant)
        self.CREDIT_PACKS = CREDIT_PACKS

        # =============================================
        # PRICE ID TO PLAN MAPPING
        # =============================================
        self._build_price_mapping()

    def _build_price_mapping(self):
        """Build the price ID to plan info mapping"""
        self._price_to_plan: Dict[str, PlanInfo] = {}

        def register(price_id: Optional[str], plan: str, interval: str, name: str,
                     price_monthly: Optional[float] = None, price_yearly: Optional[float] = None):
            if not price_id:
                return
            family = 'creator' if plan.startswith('creator_') else 'professional'
            self._price_to_plan[price_id] = PlanInfo(
                plan=plan,
                interval=interval,  # type: ignore[arg-type]
                credits=PLAN_CREDITS[plan],
                plan_family=family,  # type: ignore[arg-type]
                name=name,
                price_monthly=price_monthly,
                price_yearly=price_yearly,
            )

        # Professional plans
        register(self.PRICE_STARTER, 'professional_starter', 'monthly',
                 'Professionnel Premium', price_monthly=199.00)
        register(self.PRICE_STARTER_ANNUAL, 'professional_starter', 'annual',
                 'Professionnel Premium Annuel', price_yearly=2148.00)
        register(self.PRICE_PRO, 'professional_pro', 'monthly',
                 'Professionnel Pro', price_monthly=589.00)
        register(self.PRICE_PRO_ANNUAL, 'professional_pro', 'annual',
                 'Professionnel Pro Annuel', price_yearly=6360.00)
        register(self.PRICE_MAX, 'professional_max', 'monthly',
                 'Professionnel Max', price_monthly=1199.00)
        register(self.PRICE_MAX_ANNUAL, 'professional_max', 'annual',
                 'Professionnel Max Annuel', price_yearly=12948.00)

        # Creator plans
        register(self.PRICE_BASIC_MONTHLY, 'creator_basic', 'monthly',
                 'Creator Basic', price_monthly=34.99)
        register(self.PRICE_BASIC_YEARLY, 'creator_basic', 'yearly',
                 'Creator Basic Annuel', price_yearly=377.89)
        register(self.PRICE_PRO_MONTHLY, 'creator_pro', 'monthly',
                 'Creator Pro', price_monthly=65.99)
        register(self.PRICE_PRO_YEARLY, 'creator_pro', 'yearly',
                 'Creator Pro Annuel', price_yearly=712.69)
        register(self.PRICE_MAX_MONTHLY, 'creator_max', 'monthly',
                 'Creator Max', price_monthly=89.99)
        register(self.PRICE_MAX_YEARLY, 'creator_max', 'yearly',
                 'Creator Max Annuel', price_yearly=971.89)

    def get_plan_type(self, price_id: str) -> Optional[PlanInfo]:
        """
        Get plan information from a Stripe price ID.

        Returns:
            PlanInfo object (plan, interval, credits, plan_family, name)
            or None if price_id not found.
        """
        if not price_id:
            return None
        return self._price_to_plan.get(price_id)

    def get_all_valid_price_ids(self) -> list:
        """Get list of all configured price IDs"""
        return [pid for pid in self._price_to_plan.keys() if pid]

    def get_creator_price_ids(self) -> Dict[str, Optional[str]]:
        """Get all Creator tier price IDs"""
        return {
            "basic_monthly": self.PRICE_BASIC_MONTHLY,
            "basic_yearly": self.PRICE_BASIC_YEARLY,
            "pro_monthly": self.PRICE_PRO_MONTHLY,
            "pro_yearly": self.PRICE_PRO_YEARLY,
            "max_monthly": self.PRICE_MAX_MONTHLY,
            "max_yearly": self.PRICE_MAX_YEARLY,
        }

    def get_professional_price_ids(self) -> Dict[str, Optional[str]]:
        """Get all Professional tier price IDs"""
        return {
            "starter_monthly": self.PRICE_STARTER,
            "starter_annual": self.PRICE_STARTER_ANNUAL,
            "pro_monthly": self.PRICE_PRO,
            "pro_annual": self.PRICE_PRO_ANNUAL,
            "max_monthly": self.PRICE_MAX,
            "max_annual": self.PRICE_MAX_ANNUAL,
        }

    def is_valid_price_id(self, price_id: str) -> bool:
        """Check if a price ID is valid and configured"""
        return bool(price_id) and price_id in self._price_to_plan

    def get_credits_for_plan(self, plan_name: str) -> int:
        """
        Get credits for a plan by its unique name (new taxonomy).

        Args:
            plan_name: e.g. 'creator_basic', 'professional_pro'

        Returns:
            Number of credits for the plan, or 0 if not found.
        """
        return self.ALL_CREDITS.get(plan_name, 0)

    def get_plan_name_from_price_id(self, price_id: str) -> Optional[str]:
        """
        Get the unique internal plan name (new taxonomy) from a price ID.
        Used for storing in profiles.plan. Monthly and annual variants of a
        tier return the SAME name.

        Returns one of: creator_basic, creator_pro, creator_max,
        professional_starter, professional_pro, professional_max — or None.
        """
        plan_info = self.get_plan_type(price_id)
        return plan_info.plan if plan_info else None

    def get_price_id_for_plan(self, plan: str, interval: str = "monthly") -> Optional[str]:
        """
        Resolve a Stripe price ID from a unique plan name + billing interval.

        Args:
            plan: unique plan name (new taxonomy)
            interval: 'monthly' or 'yearly'/'annual'

        Returns:
            The configured price ID or None.
        """
        yearly = interval in ("yearly", "annual")
        mapping = {
            "creator_basic": self.PRICE_BASIC_YEARLY if yearly else self.PRICE_BASIC_MONTHLY,
            "creator_pro": self.PRICE_PRO_YEARLY if yearly else self.PRICE_PRO_MONTHLY,
            "creator_max": self.PRICE_MAX_YEARLY if yearly else self.PRICE_MAX_MONTHLY,
            "professional_starter": self.PRICE_STARTER_ANNUAL if yearly else self.PRICE_STARTER,
            "professional_pro": self.PRICE_PRO_ANNUAL if yearly else self.PRICE_PRO,
            "professional_max": self.PRICE_MAX_ANNUAL if yearly else self.PRICE_MAX,
        }
        return mapping.get(plan)


# Singleton instance
_stripe_config: Optional[StripeConfig] = None


def get_stripe_config() -> StripeConfig:
    """Get or create StripeConfig singleton"""
    global _stripe_config
    if _stripe_config is None:
        _stripe_config = StripeConfig()
    return _stripe_config


def get_plan_type(price_id: str) -> Optional[Dict[str, Any]]:
    """
    Helper function to get plan info as a dictionary.

    Returns:
        Dictionary with:
        - plan: unique plan name (new taxonomy)
        - tier: alias of plan (backward compatibility)
        - interval: 'monthly' | 'yearly' | 'annual'
        - credits: number of credits
        - planFamily / plan_family: 'creator' | 'professional'
        - name: readable plan name
    """
    config = get_stripe_config()
    plan_info = config.get_plan_type(price_id)

    if not plan_info:
        return None

    return {
        'plan': plan_info.plan,
        'tier': plan_info.plan,  # backward-compat alias
        'interval': plan_info.interval,
        'credits': plan_info.credits,
        'planFamily': plan_info.plan_family,
        'plan_family': plan_info.plan_family,
        'name': plan_info.name,
        'price_monthly': plan_info.price_monthly,
        'price_yearly': plan_info.price_yearly,
    }


# Log the Stripe mode at import time (never the key itself)
_mode = get_stripe_mode()
logger.info("Stripe mode: %s", _mode)
print(f"[stripe_config] Stripe mode: {_mode}")
