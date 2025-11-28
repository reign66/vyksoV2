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
    plan_family TEXT DEFAULT 'professional',     -- creator or professional
    current_period_end TIMESTAMP WITH TIME ZONE, -- When subscription renews
    canceled_at TIMESTAMP WITH TIME ZONE,        -- When subscription was canceled
    -- YouTube integration
    youtube_tokens JSONB,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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
        ALTER TABLE profiles ADD COLUMN plan_family TEXT DEFAULT 'professional';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'current_period_end') THEN
        ALTER TABLE profiles ADD COLUMN current_period_end TIMESTAMP WITH TIME ZONE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'canceled_at') THEN
        ALTER TABLE profiles ADD COLUMN canceled_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- ============================================
-- TABLE: video_jobs
-- Note: user_id pointe maintenant vers auth.users.id (et par extension profiles.id)
-- ============================================
CREATE TABLE IF NOT EXISTS video_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
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
-- PRICING STRUCTURE - COMPLETE MAPPING
-- ============================================

-- ============================================
-- PROFESSIONAL TIER (for ads/commercials)
-- Variable duration (6-60s), multiple sequences, ad-optimized prompts
-- ============================================

-- Professionnel Premium (starter):
--   Monthly: 199,00 €/mois → STRIPE_PRICE_STARTER
--   Annual: 179,00 €/mois (2 148,00 €/an total) → STRIPE_PRICE_STARTER_ANNUAL
--   Credits: 600 crédits = 10 minutes

-- Professionnel Pro:
--   Monthly: 589,00 €/mois → STRIPE_PRICE_PRO
--   Annual: 530,00 €/mois (6 360,00 €/an total) → STRIPE_PRICE_PRO_ANNUAL
--   Credits: 1200 crédits = 20 minutes

-- Professionnel Max:
--   Monthly: 1 199,00 €/mois → STRIPE_PRICE_MAX
--   Annual: 1 079,00 €/mois (12 948,00 €/an total) → STRIPE_PRICE_MAX_ANNUAL
--   Credits: 1800 crédits = 30 minutes

-- ============================================
-- CREATOR TIER (for TikTok/YouTube Shorts)
-- Fixed duration (10s Sora, 8s VEO), no duration selection, viral prompts
-- ============================================

-- Creator Basic:
--   Monthly: 34,99 €/mois → STRIPE_PRICE_BASIC_MONTHLY
--   Yearly: 377,89 €/an (31,49 €/mois équivalent) → STRIPE_PRICE_BASIC_YEARLY
--   Credits: 100 crédits = 10 videos de 10s

-- Creator Pro:
--   Monthly: 65,99 €/mois → STRIPE_PRICE_PRO_MONTHLY
--   Yearly: 712,69 €/an (59,39 €/mois équivalent) → STRIPE_PRICE_PRO_YEARLY
--   Credits: 200 crédits = 20 videos de 10s

-- Creator Max:
--   Monthly: 89,99 €/mois → STRIPE_PRICE_MAX_MONTHLY
--   Yearly: 971,89 €/an (80,99 €/mois équivalent) → STRIPE_PRICE_MAX_YEARLY
--   Credits: 300 crédits = 30 videos de 10s

-- Free: 10 crédits par défaut (pour tester)

-- ============================================
-- PLAN VALUES FOR profiles.plan COLUMN
-- ============================================
-- Professional tier plans (monthly):
--   'free', 'starter', 'pro', 'max'
-- Professional tier plans (annual):
--   'starter_annual', 'pro_annual', 'max_annual'
-- Creator tier plans (monthly):
--   'creator_basic', 'creator_pro', 'creator_max'
-- Creator tier plans (yearly):
--   'creator_basic_yearly', 'creator_pro_yearly', 'creator_max_yearly'

-- ============================================
-- ENVIRONMENT VARIABLES NAMING CONVENTION
-- ============================================
-- PROFESSIONAL plans use: _ANNUAL suffix for yearly (e.g., STRIPE_PRICE_PRO_ANNUAL)
-- CREATOR plans use: _YEARLY suffix for yearly (e.g., STRIPE_PRICE_PRO_YEARLY)
-- 
-- Be careful with naming conflicts:
-- - STRIPE_PRICE_PRO = Professional Pro monthly
-- - STRIPE_PRICE_PRO_MONTHLY = Creator Pro monthly
-- - STRIPE_PRICE_MAX = Professional Max monthly
-- - STRIPE_PRICE_MAX_MONTHLY = Creator Max monthly
