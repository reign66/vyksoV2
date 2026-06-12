-- ============================================================================
-- MIGRATION AUDIT 2026-06 — CORRECTIFS SQL VYKSO
-- ============================================================================
--
-- ORDRE D'EXÉCUTION :
--   * Nouveau projet Supabase (vierge)  → exécuter UNIQUEMENT database-schema.sql
--     (il contient déjà l'état final : colonnes, fonctions atomiques, index unique,
--     trigger de tier, nouvelle taxonomie de plans).
--   * Projet EXISTANT (production)      → exécuter UNIQUEMENT cette migration.
--     Elle est idempotente : elle peut être rejouée sans danger.
--
-- NE PLUS EXÉCUTER : migration-tier-update.sql (obsolète, remplacé par ce fichier).
--
-- Contenu :
--   1. video_jobs : colonnes manquantes `progress` (écrite par le code → chaque
--      job Veo échouait) et `credits_cost` (remboursement basé sur le coût stocké).
--   2. Fonctions de crédits ATOMIQUES (decrement_credits / refund_credits /
--      add_credits) — corrige la race TOCTOU (SELECT puis UPDATE) qui permettait
--      un solde négatif.
--   3. Idempotence des webhooks Stripe : index UNIQUE sur webhook_logs(event_id)
--      (après dédoublonnage des lignes existantes, on garde la plus ancienne).
--   4. Trigger de tier corrigé : plan_family dérivé du PRÉFIXE du plan
--      (plan LIKE 'professional_%' → 'professional', sinon 'creator').
--      L'ancienne convention par suffixe `_pro` n'était jamais produite par le
--      code et écrasait la valeur écrite par le webhook.
--   5. Migration des données : anciens noms de plans → nouvelle taxonomie :
--      'free', 'creator_basic', 'creator_pro', 'creator_max',
--      'professional_starter', 'professional_pro', 'professional_max'.
--      Crédits : creator_basic=100, creator_pro=200, creator_max=300,
--      professional_starter=600, professional_pro=1200, professional_max=1800.
--      (1 crédit = 1 seconde de vidéo)
-- ============================================================================


-- ============================================================================
-- 1. COLONNES MANQUANTES SUR video_jobs
-- ============================================================================

ALTER TABLE video_jobs ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0;
ALTER TABLE video_jobs ADD COLUMN IF NOT EXISTS credits_cost INTEGER;

-- Annulation programmée (cancel_at_period_end Stripe) — écrite par le webhook
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN DEFAULT FALSE;

-- updated_at sur video_jobs : dernière activité du job (base du watchdog anti-jobs-bloqués)
ALTER TABLE video_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS update_video_jobs_updated_at ON video_jobs;
CREATE TRIGGER update_video_jobs_updated_at
    BEFORE UPDATE ON video_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON COLUMN video_jobs.progress IS 'Progression de la génération (0-100), écrite par le backend pendant le job';
COMMENT ON COLUMN video_jobs.credits_cost IS 'Coût en crédits débité à la création du job ; utilisé tel quel pour le remboursement (pas de recalcul)';


-- ============================================================================
-- 2. FONCTIONS DE CRÉDITS ATOMIQUES (anti-race TOCTOU)
-- ============================================================================

-- decrement_credits : UPDATE conditionnel unique, pas de SELECT préalable.
-- Retourne le solde restant en INTEGER (0 est une valeur légitime — le code
-- Python teste `is None`, pas la falsiness).
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

-- refund_credits : UPDATE atomique unique, journalise type='refund'.
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

-- add_credits : UPDATE atomique unique, journalise type='purchase' par défaut
-- (ou 'subscription' si passé explicitement par l'appelant).
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


-- ============================================================================
-- 3. IDEMPOTENCE DES WEBHOOKS : INDEX UNIQUE SUR webhook_logs(event_id)
-- ============================================================================
-- Le webhook Python INSÈRE event_id AVANT le traitement et interprète un
-- conflit d'unicité comme "événement déjà traité".

-- 3a. Dédoublonner les lignes existantes (on garde la plus ancienne par event_id).
DELETE FROM webhook_logs w
USING (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY event_id
               ORDER BY created_at ASC, id ASC
           ) AS rn
    FROM webhook_logs
) d
WHERE w.id = d.id
  AND d.rn > 1;

-- 3b. Remplacer l'ancien index non-unique par un index UNIQUE.
DROP INDEX IF EXISTS idx_webhook_logs_event_id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_webhook_logs_event_id ON webhook_logs(event_id);


-- ============================================================================
-- 4. TRIGGER DE TIER CORRIGÉ (dérivation par PRÉFIXE, auto-réparant)
-- ============================================================================

-- get_tier_from_plan : nouvelle convention par préfixe.
-- plan LIKE 'professional_%' → 'professional' ; tout le reste (y compris
-- 'free' et les plans creator_*) → 'creator'.
CREATE OR REPLACE FUNCTION get_tier_from_plan(plan_name TEXT)
RETURNS TEXT AS $$
BEGIN
    IF plan_name IS NOT NULL AND plan_name LIKE 'professional\_%' ESCAPE '\' THEN
        RETURN 'professional';
    END IF;
    RETURN 'creator';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- get_aspect_ratio_from_tier : inchangé fonctionnellement, recréé pour cohérence.
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

-- Trigger : dérive plan_family + preferred_aspect_ratio du préfixe du plan.
-- Auto-réparant : même si le webhook écrit une valeur incohérente, le trigger
-- la recalcule depuis le plan (source de vérité unique).
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


-- ============================================================================
-- 5. MIGRATION DES DONNÉES : ANCIENS PLANS → NOUVELLE TAXONOMIE
-- ============================================================================
-- Valeurs cibles : 'free', 'creator_basic', 'creator_pro', 'creator_max',
-- 'professional_starter', 'professional_pro', 'professional_max'.
-- Idempotent : les valeurs cibles ne figurent jamais dans les clauses WHERE.
-- Le trigger ci-dessus recalcule plan_family/aspect_ratio à chaque UPDATE de plan.

-- 'starter' → 'professional_starter'
UPDATE profiles SET plan = 'professional_starter' WHERE plan = 'starter';

-- 'pro' : 'professional_pro' UNIQUEMENT si plan_family='professional',
--         sinon ('creator' ou NULL) → 'creator_pro'
UPDATE profiles SET plan = 'professional_pro'
WHERE plan = 'pro' AND plan_family = 'professional';
UPDATE profiles SET plan = 'creator_pro'
WHERE plan = 'pro' AND plan_family IS DISTINCT FROM 'professional';

-- 'max' : même logique
UPDATE profiles SET plan = 'professional_max'
WHERE plan = 'max' AND plan_family = 'professional';
UPDATE profiles SET plan = 'creator_max'
WHERE plan = 'max' AND plan_family IS DISTINCT FROM 'professional';

-- 'basic' → 'creator_basic'
UPDATE profiles SET plan = 'creator_basic' WHERE plan = 'basic';

-- 'pro-business' → 'professional_pro' ; 'max-business' → 'professional_max'
UPDATE profiles SET plan = 'professional_pro'  WHERE plan = 'pro-business';
UPDATE profiles SET plan = 'professional_max'  WHERE plan = 'max-business';

-- Anciens plans à suffixe '_pro' (écrits par migration-tier-update.sql /
-- migration-check-and-update-users.sql), mappés par équivalence de crédits :
--   starter_pro, premium_pro (600) → professional_starter
--   pro_pro (1200)                 → professional_pro
--   max_pro (1800)                 → professional_max
UPDATE profiles SET plan = 'professional_starter' WHERE plan IN ('starter_pro', 'premium_pro');
UPDATE profiles SET plan = 'professional_pro'     WHERE plan = 'pro_pro';
UPDATE profiles SET plan = 'professional_max'     WHERE plan = 'max_pro';

-- 'free' : conservé tel quel (aucune action).

-- Recalcul final de plan_family / preferred_aspect_ratio depuis le préfixe,
-- pour les lignes dont le plan n'a pas changé ci-dessus (ex. 'free' ou
-- 'creator_basic' avec un plan_family incohérent hérité de l'ancien trigger).
UPDATE profiles
SET plan_family = get_tier_from_plan(plan),
    preferred_aspect_ratio = get_aspect_ratio_from_tier(get_tier_from_plan(plan)),
    updated_at = NOW()
WHERE plan_family IS DISTINCT FROM get_tier_from_plan(plan)
   OR preferred_aspect_ratio IS DISTINCT FROM get_aspect_ratio_from_tier(get_tier_from_plan(plan));


-- ============================================================================
-- 6. DOCUMENTATION
-- ============================================================================

COMMENT ON COLUMN profiles.plan IS
    'Plan d''abonnement. Valeurs : free, creator_basic (100), creator_pro (200), creator_max (300), professional_starter (600), professional_pro (1200), professional_max (1800). 1 crédit = 1 seconde de vidéo.';
COMMENT ON COLUMN profiles.plan_family IS
    'Famille de plan dérivée du préfixe : plan LIKE ''professional_%'' → professional (16:9), sinon creator (9:16, free inclus).';
COMMENT ON FUNCTION get_tier_from_plan(TEXT) IS
    'Dérive la famille (creator/professional) du PRÉFIXE du plan : professional_% → professional, sinon creator.';

-- ============================================================================
-- VÉRIFICATION (lecture seule, optionnelle)
-- ============================================================================
-- SELECT plan, plan_family, preferred_aspect_ratio, COUNT(*)
-- FROM profiles GROUP BY 1, 2, 3 ORDER BY 1;
