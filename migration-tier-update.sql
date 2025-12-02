-- ============================================
-- MIGRATION SCRIPT: Update Tier System
-- ============================================
-- 
-- This script updates the database to support the new tier logic:
-- - Plans WITHOUT "_pro" suffix → CREATOR tier (9:16 vertical)
-- - Plans WITH "_pro" suffix → PROFESSIONAL tier (16:9 horizontal)
--
-- Run this script in your Supabase SQL Editor
-- ============================================

-- ============================================
-- STEP 1: Add new columns if they don't exist
-- ============================================

DO $$
BEGIN
    -- Add plan_family column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'profiles' AND column_name = 'plan_family') THEN
        ALTER TABLE profiles ADD COLUMN plan_family TEXT DEFAULT 'creator';
        RAISE NOTICE 'Added plan_family column';
    END IF;
    
    -- Add aspect_ratio column for caching/display purposes (optional)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'profiles' AND column_name = 'preferred_aspect_ratio') THEN
        ALTER TABLE profiles ADD COLUMN preferred_aspect_ratio TEXT DEFAULT '9:16';
        RAISE NOTICE 'Added preferred_aspect_ratio column';
    END IF;
END $$;

-- ============================================
-- STEP 2: Create function to determine tier from plan
-- ============================================

CREATE OR REPLACE FUNCTION get_tier_from_plan(plan_name TEXT)
RETURNS TEXT AS $$
BEGIN
    -- NULL or empty plan defaults to creator
    IF plan_name IS NULL OR plan_name = '' THEN
        RETURN 'creator';
    END IF;
    
    -- Plans ending with "_pro" suffix are PROFESSIONAL tier
    -- Example: max_pro, pro_pro, premium_pro, starter_pro
    IF LOWER(plan_name) LIKE '%\_pro' ESCAPE '\' THEN
        RETURN 'professional';
    END IF;
    
    -- Explicit professional plans list
    IF LOWER(plan_name) IN ('premium_pro', 'pro_pro', 'max_pro', 'starter_pro') THEN
        RETURN 'professional';
    END IF;
    
    -- All other plans are CREATOR tier
    -- This includes: free, starter, premium, pro, max, creator_basic, creator_pro, creator_max
    RETURN 'creator';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- STEP 3: Create function to get aspect ratio from tier
-- ============================================

CREATE OR REPLACE FUNCTION get_aspect_ratio_from_tier(tier_name TEXT)
RETURNS TEXT AS $$
BEGIN
    IF tier_name = 'professional' THEN
        RETURN '16:9';  -- Horizontal widescreen for ads
    ELSE
        RETURN '9:16';  -- Vertical for TikTok/Shorts
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================
-- STEP 4: Update existing profiles with correct tier
-- ============================================

-- First, let's see what we have (preview - run this first to check)
-- SELECT id, full_name, plan, plan_family, 
--        get_tier_from_plan(plan) as calculated_tier,
--        get_aspect_ratio_from_tier(get_tier_from_plan(plan)) as calculated_aspect_ratio
-- FROM profiles
-- ORDER BY plan;

-- Update all profiles to have correct plan_family based on their plan
UPDATE profiles
SET 
    plan_family = get_tier_from_plan(plan),
    preferred_aspect_ratio = get_aspect_ratio_from_tier(get_tier_from_plan(plan)),
    updated_at = NOW()
WHERE plan_family IS DISTINCT FROM get_tier_from_plan(plan)
   OR preferred_aspect_ratio IS DISTINCT FROM get_aspect_ratio_from_tier(get_tier_from_plan(plan));

-- ============================================
-- STEP 5: Create trigger to auto-update tier on plan change
-- ============================================

CREATE OR REPLACE FUNCTION update_tier_on_plan_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Automatically update plan_family and aspect_ratio when plan changes
    NEW.plan_family := get_tier_from_plan(NEW.plan);
    NEW.preferred_aspect_ratio := get_aspect_ratio_from_tier(NEW.plan_family);
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop existing trigger if it exists
DROP TRIGGER IF EXISTS trigger_update_tier_on_plan_change ON profiles;

-- Create new trigger
CREATE TRIGGER trigger_update_tier_on_plan_change
    BEFORE INSERT OR UPDATE OF plan ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_tier_on_plan_change();

-- ============================================
-- STEP 6: Add comments for documentation
-- ============================================

COMMENT ON COLUMN profiles.plan IS 'User subscription plan. Plans without _pro suffix = Creator (9:16). Plans with _pro suffix = Professional (16:9).';
COMMENT ON COLUMN profiles.plan_family IS 'Tier type: "creator" for 9:16 vertical TikTok/Shorts or "professional" for 16:9 horizontal ads';
COMMENT ON COLUMN profiles.preferred_aspect_ratio IS 'Video aspect ratio based on tier: "9:16" for creator, "16:9" for professional';

COMMENT ON FUNCTION get_tier_from_plan(TEXT) IS 'Determines tier (creator/professional) from plan name. Plans ending with _pro are professional.';
COMMENT ON FUNCTION get_aspect_ratio_from_tier(TEXT) IS 'Returns aspect ratio for tier. Professional=16:9, Creator=9:16.';

-- ============================================
-- STEP 7: Verify the migration
-- ============================================

-- Run this query to verify the migration worked correctly:
SELECT 
    plan,
    plan_family,
    preferred_aspect_ratio,
    COUNT(*) as user_count
FROM profiles
GROUP BY plan, plan_family, preferred_aspect_ratio
ORDER BY plan;

-- ============================================
-- TIER SYSTEM REFERENCE
-- ============================================
-- 
-- CREATOR TIER (9:16 vertical - TikTok/YouTube Shorts):
--   Plans: free, starter, premium, pro, max
--   Yearly: starter_yearly, premium_yearly, pro_yearly, max_yearly
--   Legacy: creator_basic, creator_pro, creator_max
--   Features:
--     - Fixed duration (8s VEO, 10s Sora)
--     - Vertical 9:16 format
--     - Viral/trending prompts
--
-- PROFESSIONAL TIER (16:9 horizontal - Ads/Commercials):
--   Plans: starter_pro, premium_pro, pro_pro, max_pro
--   Yearly: starter_pro_yearly, premium_pro_yearly, pro_pro_yearly, max_pro_yearly
--   Features:
--     - Variable duration (6-60s)
--     - Horizontal 16:9 widescreen format
--     - Professional advertising prompts
--
-- ============================================
