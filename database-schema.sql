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
    cancel_at_period_end BOOLEAN DEFAULT FALSE,  -- Scheduled cancellation (Stripe)
    -- YouTube integration
    youtube_tokens JSONB,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- TIER LOGIC:
-- plan_family is derived from the plan name PREFIX:
--   - plan LIKE 'professional_%' → 'professional' (16:9 horizontal)
--   - everything else (incl. 'free') → 'creator' (9:16 vertical)
-- Example:
--   plan = 'creator_max'      → plan_family = 'creator', preferred_aspect_ratio = '9:16'
--   plan = 'professional_max' → plan_family = 'professional', preferred_aspect_ratio = '16:9'

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
    progress INTEGER DEFAULT 0,   -- 0-100, mis à jour par le backend pendant la génération
    credits_cost INTEGER,         -- coût en crédits débité à la création (utilisé pour le remboursement)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),  -- bump à chaque update (trigger) ; base du watchdog
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
-- UNIQUE: garantit l'idempotence des webhooks Stripe (le backend insère
-- event_id AVANT traitement ; un conflit = événement déjà traité)
CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_logs_event_id ON webhook_logs(event_id);
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
-- ATOMIQUE : un seul UPDATE conditionnel (pas de SELECT préalable),
-- donc pas de race TOCTOU ni de solde négatif possible.
-- Retourne le solde restant en INTEGER (0 est une valeur légitime —
-- le code appelant teste `is None`, pas la falsiness).
-- ============================================
CREATE OR REPLACE FUNCTION decrement_credits(p_user_id UUID, p_amount INTEGER)
RETURNS INTEGER AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    UPDATE profiles
    SET credits = credits - p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
      AND credits >= p_amount
    RETURNING credits INTO v_remaining;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'INSUFFICIENT_CREDITS';
    END IF;

    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, -p_amount, 'debit', 'Video generation');

    RETURN v_remaining;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- ============================================
-- FUNCTION: refund_credits (atomique, type='refund')
-- ============================================
CREATE OR REPLACE FUNCTION refund_credits(p_user_id UUID, p_amount INTEGER)
RETURNS INTEGER AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    UPDATE profiles
    SET credits = credits + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING credits INTO v_remaining;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'USER_NOT_FOUND';
    END IF;

    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, p_amount, 'refund', 'Video generation refund');

    RETURN v_remaining;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- ============================================
-- FUNCTION: add_credits (atomique, type='purchase' par défaut,
-- 'subscription' si passé explicitement)
-- ============================================
CREATE OR REPLACE FUNCTION add_credits(p_user_id UUID, p_amount INTEGER, p_type TEXT DEFAULT 'purchase')
RETURNS INTEGER AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    UPDATE profiles
    SET credits = credits + p_amount,
        updated_at = NOW()
    WHERE id = p_user_id
    RETURNING credits INTO v_remaining;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'USER_NOT_FOUND';
    END IF;

    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, p_amount, p_type,
        CASE
            WHEN p_type = 'subscription' THEN 'Monthly subscription credits'
            ELSE 'Credit purchase'
        END
    );

    RETURN v_remaining;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

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

-- Trigger for video_jobs (base du watchdog : updated_at = dernière activité du job)
DROP TRIGGER IF EXISTS update_video_jobs_updated_at ON video_jobs;
CREATE TRIGGER update_video_jobs_updated_at
    BEFORE UPDATE ON video_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- TIER: plan_family dérivé du PRÉFIXE du plan
-- plan LIKE 'professional_%' → 'professional' (16:9), sinon 'creator' (9:16)
-- ============================================
CREATE OR REPLACE FUNCTION get_tier_from_plan(plan_name TEXT)
RETURNS TEXT AS $$
BEGIN
    IF plan_name IS NOT NULL AND plan_name LIKE 'professional\_%' ESCAPE '\' THEN
        RETURN 'professional';
    END IF;
    RETURN 'creator';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION get_aspect_ratio_from_tier(tier_name TEXT)
RETURNS TEXT AS $$
BEGIN
    IF tier_name = 'professional' THEN
        RETURN '16:9';  -- horizontal (pubs / commercials)
    ELSE
        RETURN '9:16';  -- vertical (TikTok / Shorts)
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION update_tier_on_plan_change()
RETURNS TRIGGER AS $$
BEGIN
    NEW.plan_family := get_tier_from_plan(NEW.plan);
    NEW.preferred_aspect_ratio := get_aspect_ratio_from_tier(NEW.plan_family);
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_tier_on_plan_change ON profiles;
CREATE TRIGGER trigger_update_tier_on_plan_change
    BEFORE INSERT OR UPDATE OF plan ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_tier_on_plan_change();

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
-- TIER SYSTEM - BASED ON PLAN NAME PREFIX
-- ============================================
--
-- IMPORTANT: plan_family is derived from the plan name PREFIX:
--   plan LIKE 'professional_%' → 'professional' (16:9 horizontal)
--   everything else (incl. 'free') → 'creator' (9:16 vertical)
--
-- CREATOR TIER (9:16 VERTICAL - TikTok/YouTube Shorts):
--   - Plans: free, creator_basic, creator_pro, creator_max
--   - Fixed duration: 8s (VEO) or 10s (Sora)
--   - Prompts: Viral, attention-grabbing, TikTok optimized
--
-- PROFESSIONAL TIER (16:9 HORIZONTAL - Ads/Commercials):
--   - Plans: professional_starter, professional_pro, professional_max
--   - Variable duration: 6-60s
--   - Prompts: Professional, brand-safe, conversion-focused
--
-- Example tier detection:
--   plan = "creator_max"      → CREATOR (9:16 vertical)
--   plan = "professional_max" → PROFESSIONAL (16:9 horizontal)
--

-- ============================================
-- PLAN VALUES FOR profiles.plan COLUMN + CREDITS
-- (1 credit = 1 second of video)
-- ============================================
-- Creator tier (9:16 vertical):
--   'free'          → 10 crédits initiaux (pour tester)
--   'creator_basic' → 100 crédits/mois
--   'creator_pro'   → 200 crédits/mois
--   'creator_max'   → 300 crédits/mois
--
-- Professional tier (16:9 horizontal):
--   'professional_starter' → 600 crédits/mois
--   'professional_pro'     → 1200 crédits/mois
--   'professional_max'     → 1800 crédits/mois
