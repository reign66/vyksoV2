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
    credits INTEGER DEFAULT 10,
    plan TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    youtube_tokens JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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
-- INDEXES pour performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_video_jobs_user_id ON video_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_jobs(status);
CREATE INDEX IF NOT EXISTS idx_video_jobs_created_at ON video_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_subscription ON profiles(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON credit_transactions(user_id);

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
-- CREDITS MAPPING - TWO TIER SYSTEM
-- ============================================

-- ============================================
-- PROFESSIONAL TIER (for ads/commercials)
-- ============================================
-- Variable duration (6-60s), multiple sequences, ad-optimized prompts
-- Plan Starter (Premium): 600 crédits = 10 minutes
-- Plan Pro: 1200 crédits = 20 minutes
-- Plan Max: 1800 crédits = 30 minutes

-- ============================================
-- CREATOR TIER (for TikTok/YouTube Shorts)
-- ============================================
-- Fixed duration (10s Sora, 8s VEO), no duration selection, viral prompts
-- Plan creator_basic: 34.99€/month = 100 crédits = 10 videos de 10s
-- Plan creator_pro: 65.99€/month = 200 crédits = 20 videos de 10s  
-- Plan creator_max: 89.99€/month = 300 crédits = 30 videos de 10s

-- Free: 10 crédits par défaut (pour tester)

-- ============================================
-- PLAN VALUES FOR profiles.plan COLUMN
-- ============================================
-- Professional tier plans:
--   'free', 'starter', 'pro', 'max'
-- Creator tier plans:
--   'creator_basic', 'creator_pro', 'creator_max'
