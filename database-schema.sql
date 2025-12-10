-- Schema SQL pour Vykso
-- À exécuter dans l'éditeur SQL de Supabase
-- NOUVELLE ARCHITECTURE: auth.users (Supabase Auth) + public.profiles (données métier)

-- ============================================
-- TABLE: profiles (remplace l'ancienne table users)
-- Le id fait référence à auth.users.id
-- ============================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    credits INTEGER DEFAULT 10,
    plan TEXT DEFAULT 'free',
    -- Stripe subscription fields
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    price_id TEXT,                              -- Current Stripe price ID
    subscription_status TEXT DEFAULT 'inactive', -- active, canceled, past_due, etc.
    plan_tier TEXT,                              -- basic, pro, max, starter, etc.
    plan_interval TEXT,                          -- monthly, yearly, annual
    plan_family TEXT DEFAULT 'creator',          -- 'creator' (9:16) or 'professional' (16:9)
    preferred_aspect_ratio TEXT DEFAULT '9:16',  -- '9:16' for creator, '16:9' for professional
    current_period_end TIMESTAMP WITH TIME ZONE, -- When subscription renews
    canceled_at TIMESTAMP WITH TIME ZONE,        -- When subscription was canceled
    -- YouTube integration
    youtube_tokens JSONB,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- TIER LOGIC:
-- plan_family is derived from plan name:
--   - Plans WITHOUT '_pro' suffix → 'creator' (9:16 vertical)
--   - Plans WITH '_pro' suffix → 'professional' (16:9 horizontal)
-- Example:
--   plan = 'max'     → plan_family = 'creator', preferred_aspect_ratio = '9:16'
--   plan = 'max_pro' → plan_family = 'professional', preferred_aspect_ratio = '16:9'

-- Add new columns to existing profiles table (run if table already exists)
-- Run these ALTER statements only if the columns don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'email') THEN
        ALTER TABLE profiles ADD COLUMN email TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'first_name') THEN
        ALTER TABLE profiles ADD COLUMN first_name TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'last_name') THEN
        ALTER TABLE profiles ADD COLUMN last_name TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'price_id') THEN
        ALTER TABLE profiles ADD COLUMN price_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'subscription_status') THEN
        ALTER TABLE profiles ADD COLUMN subscription_status TEXT DEFAULT 'inactive';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'plan_tier') THEN
        ALTER TABLE profiles ADD COLUMN plan_tier TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'plan_interval') THEN
        ALTER TABLE profiles ADD COLUMN plan_interval TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'plan_family') THEN
        ALTER TABLE profiles ADD COLUMN plan_family TEXT DEFAULT 'creator';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'preferred_aspect_ratio') THEN
        ALTER TABLE profiles ADD COLUMN preferred_aspect_ratio TEXT DEFAULT '9:16';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'current_period_end') THEN
        ALTER TABLE profiles ADD COLUMN current_period_end TIMESTAMP WITH TIME ZONE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'canceled_at') THEN
        ALTER TABLE profiles ADD COLUMN canceled_at TIMESTAMP WITH TIME ZONE;
    END IF;
    
    -- Update existing plan_family default from 'professional' to 'creator'
    -- (since most plans without _pro suffix should be creator)
    ALTER TABLE profiles ALTER COLUMN plan_family SET DEFAULT 'creator';
END $$;

-- ============================================
-- TABLE: video_jobs
-- Note: user_id pointe maintenant vers auth.users.id (et par extension profiles.id)
-- ============================================
CREATE TABLE IF NOT EXISTS video_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,  -- Pourcentage de progression (0-100)
    video_url TEXT,
    niche TEXT,
    duration INTEGER,
    quality TEXT,
    prompt TEXT,
    metadata JSONB,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Migration: Add progress column if it doesn't exist (run on existing databases)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'video_jobs' AND column_name = 'progress') THEN
        ALTER TABLE video_jobs ADD COLUMN progress INTEGER DEFAULT 0;
    END IF;
END $$;

-- ============================================
-- TABLE: credit_transactions (optionnel - pour historique)
-- ============================================
CREATE TABLE IF NOT EXISTS credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    type TEXT NOT NULL, -- 'debit', 'credit', 'refund', 'subscription'
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- TABLE: webhook_logs (for Stripe webhook debugging)
-- ============================================
CREATE TABLE IF NOT EXISTS webhook_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    event_id TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    data_summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- TABLE: notifications (for in-app notifications)
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,         -- 'payment_failed', 'subscription_renewed', etc.
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    action_url TEXT,            -- Optional link for user action
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- INDEXES pour performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_video_jobs_user_id ON video_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_jobs(status);
CREATE INDEX IF NOT EXISTS idx_video_jobs_created_at ON video_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_subscription ON profiles(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_customer ON profiles(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_profiles_plan ON profiles(plan);
CREATE INDEX IF NOT EXISTS idx_profiles_plan_family ON profiles(plan_family);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON credit_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_webhook_logs_event_type ON webhook_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_logs_event_id ON webhook_logs(event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, read);

-- ============================================
-- TRIGGER: handle_new_user
-- Crée automatiquement un profil quand un utilisateur s'inscrit via auth.users
-- ============================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, credits, plan)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
        10, -- Crédits initiaux pour le plan free
        'free'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Créer le trigger sur auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

-- Enable RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_transactions ENABLE ROW LEVEL SECURITY;

-- Profiles policies
DROP POLICY IF EXISTS "Users can view their own profile" ON profiles;
CREATE POLICY "Users can view their own profile"
    ON profiles FOR SELECT
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update their own profile" ON profiles;
CREATE POLICY "Users can update their own profile"
    ON profiles FOR UPDATE
    USING (auth.uid() = id);

-- Video jobs policies
DROP POLICY IF EXISTS "Users can view their own jobs" ON video_jobs;
CREATE POLICY "Users can view their own jobs"
    ON video_jobs FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own jobs" ON video_jobs;
CREATE POLICY "Users can insert their own jobs"
    ON video_jobs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Credit transactions policies
DROP POLICY IF EXISTS "Users can view their own transactions" ON credit_transactions;
CREATE POLICY "Users can view their own transactions"
    ON credit_transactions FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can do everything (for backend avec SUPABASE_SERVICE_KEY)
DROP POLICY IF EXISTS "Service role full access profiles" ON profiles;
CREATE POLICY "Service role full access profiles"
    ON profiles FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access video_jobs" ON video_jobs;
CREATE POLICY "Service role full access video_jobs"
    ON video_jobs FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access credit_transactions" ON credit_transactions;
CREATE POLICY "Service role full access credit_transactions"
    ON credit_transactions FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- ============================================
-- FUNCTION: decrement_credits
-- 1 crédit = 1 seconde de vidéo
-- ============================================
CREATE OR REPLACE FUNCTION decrement_credits(p_user_id UUID, p_amount INTEGER)
RETURNS INTEGER AS $$
DECLARE
    current_credits INTEGER;
BEGIN
    SELECT credits INTO current_credits FROM profiles WHERE id = p_user_id;
    
    IF current_credits IS NULL THEN
        RAISE EXCEPTION 'User not found';
    END IF;
    
    IF current_credits < p_amount THEN
        RAISE EXCEPTION 'Insufficient credits';
    END IF;
    
    UPDATE profiles 
    SET credits = credits - p_amount,
        updated_at = NOW()
    WHERE id = p_user_id;
    
    -- Enregistrer la transaction (optionnel)
    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, -p_amount, 'debit', 'Video generation');
    
    RETURN current_credits - p_amount;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- FUNCTION: refund_credits
-- ============================================
CREATE OR REPLACE FUNCTION refund_credits(p_user_id UUID, p_amount INTEGER)
RETURNS INTEGER AS $$
DECLARE
    current_credits INTEGER;
BEGIN
    UPDATE profiles 
    SET credits = credits + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING credits INTO current_credits;
    
    -- Enregistrer la transaction (optionnel)
    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, p_amount, 'refund', 'Video generation refund');
    
    RETURN current_credits;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- FUNCTION: add_credits (pour achats et abonnements)
-- ============================================
CREATE OR REPLACE FUNCTION add_credits(p_user_id UUID, p_amount INTEGER, p_type TEXT DEFAULT 'credit')
RETURNS INTEGER AS $$
DECLARE
    current_credits INTEGER;
BEGIN
    UPDATE profiles 
    SET credits = credits + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING credits INTO current_credits;
    
    -- Enregistrer la transaction
    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, p_amount, p_type, 
        CASE 
            WHEN p_type = 'subscription' THEN 'Monthly subscription credits'
            ELSE 'Credit purchase'
        END
    );
    
    RETURN current_credits;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- FUNCTION: auto-update updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for profiles
DROP TRIGGER IF EXISTS update_profiles_updated_at ON profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- STORAGE BUCKETS
-- ============================================
-- Note: Les buckets doivent être créés manuellement dans l'interface Supabase
-- Storage > Create Bucket

-- Buckets à créer:
-- 1. vykso-videos (public ou private selon vos besoins)
-- 2. video-images (public)

-- Permissions pour les buckets (à configurer dans l'interface ou via API):
-- - Authenticated users can upload to video-images
-- - Authenticated users can read/download from vykso-videos

-- ============================================
-- RLS for webhook_logs and notifications
-- ============================================
ALTER TABLE webhook_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Webhook logs - service role only (backend operations)
DROP POLICY IF EXISTS "Service role full access webhook_logs" ON webhook_logs;
CREATE POLICY "Service role full access webhook_logs"
    ON webhook_logs FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Notifications - users can view their own
DROP POLICY IF EXISTS "Users can view their own notifications" ON notifications;
CREATE POLICY "Users can view their own notifications"
    ON notifications FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own notifications" ON notifications;
CREATE POLICY "Users can update their own notifications"
    ON notifications FOR UPDATE
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service role full access notifications" ON notifications;
CREATE POLICY "Service role full access notifications"
    ON notifications FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- ============================================
-- TIER SYSTEM - BASED ON PLAN NAME
-- ============================================
-- 
-- IMPORTANT: The tier is determined by the plan name suffix:
-- 
-- CREATOR TIER (9:16 VERTICAL - TikTok/YouTube Shorts):
--   - Plans WITHOUT "_pro" suffix: free, starter, premium, pro, max
--   - Yearly variants: starter_yearly, pro_yearly, max_yearly
--   - Legacy naming: creator_basic, creator_pro, creator_max
--   - Fixed duration: 8s (VEO) or 10s (Sora)
--   - Aspect ratio: 9:16 VERTICAL
--   - Prompts: Viral, attention-grabbing, TikTok optimized
-- 
-- PROFESSIONAL TIER (16:9 HORIZONTAL - Ads/Commercials):
--   - Plans WITH "_pro" suffix: premium_pro, pro_pro, max_pro, starter_pro
--   - Variable duration: 6-60s
--   - Aspect ratio: 16:9 HORIZONTAL (widescreen)
--   - Prompts: Professional, brand-safe, conversion-focused
-- 
-- Example tier detection:
--   plan = "max"      → CREATOR (9:16 vertical)
--   plan = "max_pro"  → PROFESSIONAL (16:9 horizontal)
--   plan = "pro"      → CREATOR (9:16 vertical) 
--   plan = "pro_pro"  → PROFESSIONAL (16:9 horizontal)
-- 

-- ============================================
-- CREATOR TIER PRICING (9:16 vertical)
-- ============================================

-- Free: 10 crédits par défaut (pour tester)

-- Starter:
--   Monthly: → STRIPE_PRICE_STARTER
--   Annual: → STRIPE_PRICE_STARTER_ANNUAL
--   Credits: Variable

-- Premium:
--   Monthly: → STRIPE_PRICE_PREMIUM
--   Annual: → STRIPE_PRICE_PREMIUM_ANNUAL

-- Pro:
--   Monthly: → STRIPE_PRICE_PRO
--   Annual: → STRIPE_PRICE_PRO_ANNUAL

-- Max:
--   Monthly: → STRIPE_PRICE_MAX
--   Annual: → STRIPE_PRICE_MAX_ANNUAL

-- Legacy Creator naming:
-- Creator Basic: 34,99 €/mois → STRIPE_PRICE_BASIC_MONTHLY
-- Creator Pro: 65,99 €/mois → STRIPE_PRICE_PRO_MONTHLY
-- Creator Max: 89,99 €/mois → STRIPE_PRICE_MAX_MONTHLY

-- ============================================
-- PROFESSIONAL TIER PRICING (16:9 horizontal)
-- ============================================

-- Premium Pro:
--   Monthly: 199,00 €/mois
--   Annual: 179,00 €/mois
--   Credits: 600 crédits

-- Pro Pro:
--   Monthly: 589,00 €/mois
--   Annual: 530,00 €/mois
--   Credits: 1200 crédits

-- Max Pro:
--   Monthly: 1 199,00 €/mois
--   Annual: 1 079,00 €/mois
--   Credits: 1800 crédits

-- ============================================
-- PLAN VALUES FOR profiles.plan COLUMN
-- ============================================
-- Creator tier plans (9:16 vertical):
--   'free', 'starter', 'premium', 'pro', 'max'
--   'starter_yearly', 'premium_yearly', 'pro_yearly', 'max_yearly'
--   'creator_basic', 'creator_pro', 'creator_max' (legacy)
--
-- Professional tier plans (16:9 horizontal):
--   'starter_pro', 'premium_pro', 'pro_pro', 'max_pro'
--   'starter_pro_yearly', 'premium_pro_yearly', 'pro_pro_yearly', 'max_pro_yearly'
