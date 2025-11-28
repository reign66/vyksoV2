"""
Stripe Configuration Module
============================
Manages all Stripe price IDs and plan configurations for both
PROFESSIONAL and CREATOR tier plans.

Environment Variables:
- PROFESSIONAL plans use: _ANNUAL suffix for yearly
- CREATOR plans use: _YEARLY suffix for yearly
"""

import os
from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass


@dataclass
class PlanInfo:
    """Information about a subscription plan"""
    tier: str
    interval: Literal['monthly', 'yearly', 'annual']
    credits: int
    plan_family: Literal['creator', 'professional']
    name: str
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None


class StripeConfig:
    """
    Centralized Stripe configuration class.
    
    Manages all price IDs for both PROFESSIONAL and CREATOR tier plans.
    
    PROFESSIONAL Plans (for ads/commercials):
    - Professionnel Premium (starter): 199€/month or 179€/month yearly
    - Professionnel Pro: 589€/month or 530€/month yearly
    - Professionnel Max: 1199€/month or 1079€/month yearly
    
    CREATOR Plans (for TikTok/YouTube Shorts):
    - Creator Basic: 34.99€/month or 31.49€/month yearly (100 credits)
    - Creator Pro: 65.99€/month or 59.39€/month yearly (200 credits)
    - Creator Max: 89.99€/month or 80.99€/month yearly (300 credits)
    """
    
    def __init__(self):
        # =============================================
        # PROFESSIONAL TIER PRICE IDs
        # =============================================
        
        # Pro plan (Professionnel Pro)
        self.PRICE_PRO = os.getenv("STRIPE_PRICE_PRO")  # 589€/month
        self.PRICE_PRO_ANNUAL = os.getenv("STRIPE_PRICE_PRO_ANNUAL")  # 530€/month yearly
        
        # Max plan (Professionnel Max)
        self.PRICE_MAX = os.getenv("STRIPE_PRICE_MAX")  # 1199€/month
        self.PRICE_MAX_ANNUAL = os.getenv("STRIPE_PRICE_MAX_ANNUAL")  # 1079€/month yearly
        
        # Starter plan (Professionnel Premium)
        self.PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER")  # 199€/month
        self.PRICE_STARTER_ANNUAL = os.getenv("STRIPE_PRICE_STARTER_ANNUAL")  # 179€/month yearly
        
        # =============================================
        # CREATOR TIER PRICE IDs
        # =============================================
        
        # Basic plan (Creator Basic)
        self.PRICE_BASIC_MONTHLY = os.getenv("STRIPE_PRICE_BASIC_MONTHLY")  # 34.99€/month
        self.PRICE_BASIC_YEARLY = os.getenv("STRIPE_PRICE_BASIC_YEARLY")  # 377.89€/year
        
        # Pro plan (Creator Pro) - Note: Different from PROFESSIONAL Pro!
        self.PRICE_PRO_MONTHLY = os.getenv("STRIPE_PRICE_PRO_MONTHLY")  # 65.99€/month
        self.PRICE_PRO_YEARLY = os.getenv("STRIPE_PRICE_PRO_YEARLY")  # 712.69€/year
        
        # Max plan (Creator Max) - Note: Different from PROFESSIONAL Max!
        self.PRICE_MAX_MONTHLY = os.getenv("STRIPE_PRICE_MAX_MONTHLY")  # 89.99€/month
        self.PRICE_MAX_YEARLY = os.getenv("STRIPE_PRICE_MAX_YEARLY")  # 971.89€/year
        
        # =============================================
        # CREDITS MAPPING
        # =============================================
        
        # Creator plan credits (1 credit = 1 video of ~10s)
        self.CREATOR_CREDITS = {
            "creator_basic": 100,
            "creator_basic_yearly": 100,
            "creator_pro": 200,
            "creator_pro_yearly": 200,
            "creator_max": 300,
            "creator_max_yearly": 300,
        }
        
        # Professional plan credits
        self.PROFESSIONAL_CREDITS = {
            "starter": 600,
            "starter_annual": 600,
            "pro": 1200,
            "pro_annual": 1200,
            "max": 1800,
            "max_annual": 1800,
        }
        
        # Combined credits mapping
        self.ALL_CREDITS = {**self.CREATOR_CREDITS, **self.PROFESSIONAL_CREDITS}
        
        # =============================================
        # PRICE ID TO PLAN MAPPING
        # =============================================
        self._build_price_mapping()
    
    def _build_price_mapping(self):
        """Build the price ID to plan info mapping"""
        self._price_to_plan: Dict[str, PlanInfo] = {}
        
        # Professional plans
        if self.PRICE_STARTER:
            self._price_to_plan[self.PRICE_STARTER] = PlanInfo(
                tier='starter',
                interval='monthly',
                credits=600,
                plan_family='professional',
                name='Professionnel Premium',
                price_monthly=199.00
            )
        
        if self.PRICE_STARTER_ANNUAL:
            self._price_to_plan[self.PRICE_STARTER_ANNUAL] = PlanInfo(
                tier='starter',
                interval='annual',
                credits=600,
                plan_family='professional',
                name='Professionnel Premium Annuel',
                price_yearly=2148.00
            )
        
        if self.PRICE_PRO:
            self._price_to_plan[self.PRICE_PRO] = PlanInfo(
                tier='pro-business',
                interval='monthly',
                credits=1200,
                plan_family='professional',
                name='Professionnel Pro',
                price_monthly=589.00
            )
        
        if self.PRICE_PRO_ANNUAL:
            self._price_to_plan[self.PRICE_PRO_ANNUAL] = PlanInfo(
                tier='pro-business',
                interval='annual',
                credits=1200,
                plan_family='professional',
                name='Professionnel Pro Annuel',
                price_yearly=6360.00
            )
        
        if self.PRICE_MAX:
            self._price_to_plan[self.PRICE_MAX] = PlanInfo(
                tier='max-business',
                interval='monthly',
                credits=1800,
                plan_family='professional',
                name='Professionnel Max',
                price_monthly=1199.00
            )
        
        if self.PRICE_MAX_ANNUAL:
            self._price_to_plan[self.PRICE_MAX_ANNUAL] = PlanInfo(
                tier='max-business',
                interval='annual',
                credits=1800,
                plan_family='professional',
                name='Professionnel Max Annuel',
                price_yearly=12948.00
            )
        
        # Creator plans
        if self.PRICE_BASIC_MONTHLY:
            self._price_to_plan[self.PRICE_BASIC_MONTHLY] = PlanInfo(
                tier='basic',
                interval='monthly',
                credits=100,
                plan_family='creator',
                name='Creator Basic',
                price_monthly=34.99
            )
        
        if self.PRICE_BASIC_YEARLY:
            self._price_to_plan[self.PRICE_BASIC_YEARLY] = PlanInfo(
                tier='basic',
                interval='yearly',
                credits=100,
                plan_family='creator',
                name='Creator Basic Annuel',
                price_yearly=377.89
            )
        
        if self.PRICE_PRO_MONTHLY:
            self._price_to_plan[self.PRICE_PRO_MONTHLY] = PlanInfo(
                tier='pro',
                interval='monthly',
                credits=200,
                plan_family='creator',
                name='Creator Pro',
                price_monthly=65.99
            )
        
        if self.PRICE_PRO_YEARLY:
            self._price_to_plan[self.PRICE_PRO_YEARLY] = PlanInfo(
                tier='pro',
                interval='yearly',
                credits=200,
                plan_family='creator',
                name='Creator Pro Annuel',
                price_yearly=712.69
            )
        
        if self.PRICE_MAX_MONTHLY:
            self._price_to_plan[self.PRICE_MAX_MONTHLY] = PlanInfo(
                tier='max',
                interval='monthly',
                credits=300,
                plan_family='creator',
                name='Creator Max',
                price_monthly=89.99
            )
        
        if self.PRICE_MAX_YEARLY:
            self._price_to_plan[self.PRICE_MAX_YEARLY] = PlanInfo(
                tier='max',
                interval='yearly',
                credits=300,
                plan_family='creator',
                name='Creator Max Annuel',
                price_yearly=971.89
            )
    
    def get_plan_type(self, price_id: str) -> Optional[PlanInfo]:
        """
        Get plan information from a Stripe price ID.
        
        Args:
            price_id: The Stripe price ID
            
        Returns:
            PlanInfo object with tier, interval, credits, planFamily, and name
            or None if price_id not found
        """
        return self._price_to_plan.get(price_id)
    
    def get_all_valid_price_ids(self) -> list:
        """Get list of all configured price IDs"""
        return [pid for pid in self._price_to_plan.keys() if pid]
    
    def get_creator_price_ids(self) -> Dict[str, str]:
        """Get all Creator tier price IDs"""
        return {
            "basic_monthly": self.PRICE_BASIC_MONTHLY,
            "basic_yearly": self.PRICE_BASIC_YEARLY,
            "pro_monthly": self.PRICE_PRO_MONTHLY,
            "pro_yearly": self.PRICE_PRO_YEARLY,
            "max_monthly": self.PRICE_MAX_MONTHLY,
            "max_yearly": self.PRICE_MAX_YEARLY,
        }
    
    def get_professional_price_ids(self) -> Dict[str, str]:
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
        return price_id in self._price_to_plan
    
    def get_credits_for_plan(self, plan_name: str) -> int:
        """
        Get credits for a plan by name.
        
        Args:
            plan_name: The plan name (e.g., 'creator_basic', 'pro', 'starter_annual')
            
        Returns:
            Number of credits for the plan, or 0 if not found
        """
        return self.ALL_CREDITS.get(plan_name, 0)
    
    def get_plan_name_from_price_id(self, price_id: str) -> Optional[str]:
        """
        Get the internal plan name from a price ID.
        Used for storing in database.
        
        Returns plan names like: 'creator_basic', 'creator_pro', 'starter', 'pro', etc.
        """
        plan_info = self.get_plan_type(price_id)
        if not plan_info:
            return None
        
        if plan_info.plan_family == 'creator':
            # Creator plans: creator_basic, creator_pro, creator_max
            base = f"creator_{plan_info.tier}"
            if plan_info.interval == 'yearly':
                return f"{base}_yearly"
            return base
        else:
            # Professional plans: starter, pro, max
            if plan_info.tier == 'pro-business':
                base = 'pro'
            elif plan_info.tier == 'max-business':
                base = 'max'
            else:
                base = plan_info.tier
            
            if plan_info.interval == 'annual':
                return f"{base}_annual"
            return base


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
    
    Args:
        price_id: The Stripe price ID
        
    Returns:
        Dictionary with:
        - tier: 'basic' | 'pro' | 'max' | 'starter' | 'pro-business' | 'max-business'
        - interval: 'monthly' | 'yearly' | 'annual'
        - credits: number of credits
        - planFamily: 'creator' | 'professional'
        - name: readable plan name
    """
    config = get_stripe_config()
    plan_info = config.get_plan_type(price_id)
    
    if not plan_info:
        return None
    
    return {
        'tier': plan_info.tier,
        'interval': plan_info.interval,
        'credits': plan_info.credits,
        'planFamily': plan_info.plan_family,
        'name': plan_info.name,
        'price_monthly': plan_info.price_monthly,
        'price_yearly': plan_info.price_yearly,
    }
