-- ============================================
-- CHECK AND UPDATE EXISTING USERS
-- ============================================
-- Run these queries in order in your Supabase SQL Editor
-- ============================================

-- ============================================
-- QUERY 1: Check current state of all users
-- ============================================

SELECT 
    id,
    full_name,
    email,
    credits,
    plan,
    plan_family,
    CASE 
        WHEN plan IS NULL OR plan = '' THEN 'creator'
        WHEN LOWER(plan) LIKE '%\_pro' ESCAPE '\' THEN 'professional'
        WHEN LOWER(plan) IN ('premium_pro', 'pro_pro', 'max_pro', 'starter_pro') THEN 'professional'
        ELSE 'creator'
    END as calculated_tier,
    CASE 
        WHEN plan IS NULL OR plan = '' THEN '9:16'
        WHEN LOWER(plan) LIKE '%\_pro' ESCAPE '\' THEN '16:9'
        WHEN LOWER(plan) IN ('premium_pro', 'pro_pro', 'max_pro', 'starter_pro') THEN '16:9'
        ELSE '9:16'
    END as calculated_aspect_ratio,
    created_at
FROM profiles
ORDER BY created_at DESC;

-- ============================================
-- QUERY 2: Summary of users by plan and tier
-- ============================================

SELECT 
    plan,
    CASE 
        WHEN plan IS NULL OR plan = '' THEN 'creator'
        WHEN LOWER(plan) LIKE '%\_pro' ESCAPE '\' THEN 'professional'
        ELSE 'creator'
    END as tier,
    CASE 
        WHEN plan IS NULL OR plan = '' THEN '9:16 (vertical)'
        WHEN LOWER(plan) LIKE '%\_pro' ESCAPE '\' THEN '16:9 (horizontal)'
        ELSE '9:16 (vertical)'
    END as aspect_ratio,
    COUNT(*) as user_count,
    SUM(credits) as total_credits
FROM profiles
GROUP BY plan
ORDER BY user_count DESC;

-- ============================================
-- QUERY 3: Update a specific user to professional tier
-- Replace 'USER_ID_HERE' with the actual user UUID
-- ============================================

-- Example: Upgrade user "Nicolas Reig" (id: e4719ae5-029c-4b0a-b57e-966aa3bcdcc8) to max_pro
-- This will give them 16:9 horizontal format for professional ads

-- UPDATE profiles
-- SET 
--     plan = 'max_pro',
--     plan_family = 'professional',
--     preferred_aspect_ratio = '16:9',
--     updated_at = NOW()
-- WHERE id = 'e4719ae5-029c-4b0a-b57e-966aa3bcdcc8';

-- ============================================
-- QUERY 4: Batch update - Convert all "max" users to "max_pro" (professional)
-- CAUTION: Only run if you want ALL max users to become professional
-- ============================================

-- UPDATE profiles
-- SET 
--     plan = 'max_pro',
--     plan_family = 'professional',
--     preferred_aspect_ratio = '16:9',
--     updated_at = NOW()
-- WHERE plan = 'max';

-- ============================================
-- QUERY 5: Specific update for user Nicolas Reig (based on your screenshot)
-- This converts from 'max' (creator/9:16) to 'max_pro' (professional/16:9)
-- ============================================

UPDATE profiles
SET 
    plan = 'max_pro',
    plan_family = 'professional',
    preferred_aspect_ratio = '16:9',
    updated_at = NOW()
WHERE id = 'e4719ae5-029c-4b0a-b57e-966aa3bcdcc8'
RETURNING id, full_name, plan, plan_family, preferred_aspect_ratio, credits;

-- ============================================
-- QUERY 6: Verify the update
-- ============================================

SELECT 
    id,
    full_name,
    plan,
    plan_family,
    preferred_aspect_ratio,
    credits
FROM profiles
WHERE id = 'e4719ae5-029c-4b0a-b57e-966aa3bcdcc8';

-- ============================================
-- PLAN CONVERSION REFERENCE
-- ============================================
--
-- To convert a user from Creator to Professional tier:
--   starter → starter_pro
--   premium → premium_pro  
--   pro     → pro_pro
--   max     → max_pro
--
-- To keep a user on Creator tier (vertical 9:16):
--   Keep their plan as: free, starter, premium, pro, max
--
-- ============================================
