# Instructions d'Intégration Stripe - Mise à Jour Complète

## 📋 Résumé des Changements

Le backend a été mis à jour pour supporter **12 abonnements Stripe** répartis en deux familles de plans :

### Plans Professionnels (pour publicités/commercials)
- **Professionnel Premium (starter)** : 199€/mois ou 179€/mois en annuel
- **Professionnel Pro** : 589€/mois ou 530€/mois en annuel
- **Professionnel Max** : 1199€/mois ou 1079€/mois en annuel

### Plans Creator (pour TikTok/YouTube Shorts)
- **Creator Basic** : 34,99€/mois ou 31,49€/mois en annuel (100 crédits)
- **Creator Pro** : 65,99€/mois ou 59,39€/mois en annuel (200 crédits)
- **Creator Max** : 89,99€/mois ou 80,99€/mois en annuel (300 crédits)

---

## 🎨 Instructions pour Lovable (Frontend)

### 1. Page de Pricing - Affichage des Plans

**Ce qui change :**
- La page pricing doit maintenant afficher **deux sections distinctes** : "Creator" et "Professionnel"
- Chaque plan doit avoir un **toggle mensuel/annuel** pour afficher les deux prix
- Les plans Creator affichent le nombre de crédits (100, 200, 300)
- Les plans Professionnels affichent les minutes de vidéo (10, 20, 30 minutes)

**Comportement attendu :**
- Quand l'utilisateur sélectionne un plan Creator avec l'option annuelle, le frontend doit envoyer le plan avec le suffixe `_yearly` (exemple : `creator_basic_yearly`)
- Quand l'utilisateur sélectionne un plan Professionnel avec l'option annuelle, le frontend doit envoyer le plan avec le suffixe `_annual` (exemple : `starter_annual`)

**Plans à afficher :**

| Famille | Plan | Mensuel | Annuel (par mois) | Crédits |
|---------|------|---------|-------------------|---------|
| Creator | Basic | 34,99€ | 31,49€ | 100 |
| Creator | Pro | 65,99€ | 59,39€ | 200 |
| Creator | Max | 89,99€ | 80,99€ | 300 |
| Pro | Premium | 199€ | 179€ | 600 |
| Pro | Pro | 589€ | 530€ | 1200 |
| Pro | Max | 1199€ | 1079€ | 1800 |

---

### 2. Appel API pour le Checkout

**Ce qui change :**
- L'endpoint `/api/stripe/create-checkout` accepte maintenant un paramètre `plan` qui peut inclure l'intervalle de facturation

**Format du paramètre `plan` :**

Pour les plans **mensuels** :
- `creator_basic`, `creator_pro`, `creator_max`
- `starter`, `pro`, `max`

Pour les plans **annuels** :
- `creator_basic_yearly`, `creator_pro_yearly`, `creator_max_yearly`
- `starter_annual`, `pro_annual`, `max_annual`

**Exemple de requête :**
```
POST /api/stripe/create-checkout
{
  "plan": "creator_pro_yearly",
  "user_id": "uuid-de-lutilisateur"
}
```

**Réponse :**
```
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

---

### 3. Nouvel Endpoint pour Lister les Prix

**Ce qui est nouveau :**
- Un nouvel endpoint `GET /api/stripe/prices` retourne tous les plans disponibles avec leurs informations

**Utilisation recommandée :**
- Appeler cet endpoint au chargement de la page pricing pour récupérer dynamiquement les informations des plans
- Cela permet de ne pas hardcoder les prix dans le frontend

**Réponse de l'endpoint :**
```
{
  "creator": [
    { "key": "basic_monthly", "name": "Creator Basic", "credits": 100, "interval": "monthly", ... },
    { "key": "basic_yearly", "name": "Creator Basic Annuel", "credits": 100, "interval": "yearly", ... },
    ...
  ],
  "professional": [
    { "key": "starter_monthly", "name": "Professionnel Premium", "credits": 600, "interval": "monthly", ... },
    ...
  ],
  "credit_packs": [
    { "credits": 60, "price": 9, "currency": "EUR" },
    { "credits": 120, "price": 15, "currency": "EUR" },
    { "credits": 300, "price": 29, "currency": "EUR" }
  ]
}
```

---

### 4. Gestion du Profil Utilisateur

**Ce qui change :**
- Le profil utilisateur contient maintenant des informations supplémentaires sur l'abonnement
- Ces informations peuvent être utilisées pour afficher le statut de l'abonnement dans le dashboard

**Nouveaux champs disponibles dans le profil :**
- `plan` : Nom du plan actuel (ex: "creator_pro", "starter_annual")
- `plan_family` : Famille du plan ("creator" ou "professional")
- `plan_tier` : Niveau du plan ("basic", "pro", "max", "starter")
- `plan_interval` : Intervalle de facturation ("monthly", "yearly", "annual")
- `subscription_status` : Statut de l'abonnement ("active", "canceled", "past_due")
- `current_period_end` : Date de fin de la période actuelle (pour afficher "Renouvellement le...")
- `canceled_at` : Date d'annulation si l'abonnement a été annulé

**Affichage recommandé dans le dashboard :**
- Afficher le nom du plan actuel
- Afficher le nombre de crédits restants
- Afficher la date de renouvellement
- Si `subscription_status` est "canceled", afficher "Votre abonnement se termine le [current_period_end]"

---

### 5. Page de Succès après Paiement

**Ce qui change :**
- Après un paiement réussi, l'utilisateur est redirigé vers `/payment-success?session_id={CHECKOUT_SESSION_ID}`
- La page doit récupérer les informations de la session pour afficher un message de confirmation

**Comportement attendu :**
- Afficher un message de bienvenue personnalisé selon le plan souscrit
- Rediriger vers le dashboard après quelques secondes ou sur clic d'un bouton
- Rafraîchir les informations du profil pour mettre à jour les crédits

---

### 6. Notifications de Paiement Échoué

**Ce qui est nouveau :**
- Le backend crée maintenant des notifications dans la table `notifications` quand un paiement échoue
- Le frontend peut afficher ces notifications à l'utilisateur

**Comportement recommandé :**
- Vérifier la table `notifications` pour les notifications non lues (`read = false`)
- Afficher une alerte/banner si une notification de type `payment_failed` existe
- Inclure un lien vers la page Stripe pour mettre à jour le moyen de paiement (disponible dans `action_url`)

---

### 7. Différenciation Creator vs Professionnel

**Ce qui change :**
- Les utilisateurs Creator ont une durée de vidéo **fixe** (8s pour VEO, 10s pour Sora)
- Les utilisateurs Professionnels peuvent **choisir** la durée (6-60 secondes)

**Dans l'interface de génération de vidéo :**
- Si `plan_family` est "creator" : Masquer le sélecteur de durée
- Si `plan_family` est "professional" : Afficher le sélecteur de durée (6-60s)

**L'endpoint `/api/users/{user_id}/tier` retourne ces informations :**
```
{
  "plan": "creator_pro",
  "tier": "creator",
  "is_creator": true,
  "credits": 200,
  "max_images": 18,
  "features": {
    "duration_selection": false,
    "fixed_duration_veo": 8,
    "fixed_duration_sora": 10,
    "prompt_style": "viral_tiktok_shorts",
    ...
  }
}
```

---

## 🗄️ Instructions SQL pour Supabase

### Contexte

Les modifications SQL ajoutent :
1. De nouveaux champs dans la table `profiles` pour stocker les informations d'abonnement détaillées
2. Une table `webhook_logs` pour le debugging des webhooks Stripe
3. Une table `notifications` pour les alertes utilisateur (paiement échoué, etc.)
4. Des index supplémentaires pour les performances

### SQL à Exécuter

Copiez et exécutez ce SQL dans l'éditeur SQL de Supabase (SQL Editor) :

```sql
-- ============================================
-- MISE À JOUR TABLE PROFILES
-- Ajout des nouveaux champs pour la gestion des abonnements
-- ============================================

-- Ajouter les nouveaux champs si ils n'existent pas déjà
DO $$
BEGIN
    -- Champ email
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'email') THEN
        ALTER TABLE profiles ADD COLUMN email TEXT;
    END IF;
    
    -- Champ first_name
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'first_name') THEN
        ALTER TABLE profiles ADD COLUMN first_name TEXT;
    END IF;
    
    -- Champ last_name
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'last_name') THEN
        ALTER TABLE profiles ADD COLUMN last_name TEXT;
    END IF;
    
    -- Champ price_id (ID du prix Stripe actuel)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'price_id') THEN
        ALTER TABLE profiles ADD COLUMN price_id TEXT;
    END IF;
    
    -- Champ subscription_status (active, canceled, past_due, etc.)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'subscription_status') THEN
        ALTER TABLE profiles ADD COLUMN subscription_status TEXT DEFAULT 'inactive';
    END IF;
    
    -- Champ plan_tier (basic, pro, max, starter)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'plan_tier') THEN
        ALTER TABLE profiles ADD COLUMN plan_tier TEXT;
    END IF;
    
    -- Champ plan_interval (monthly, yearly, annual)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'plan_interval') THEN
        ALTER TABLE profiles ADD COLUMN plan_interval TEXT;
    END IF;
    
    -- Champ plan_family (creator ou professional)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'plan_family') THEN
        ALTER TABLE profiles ADD COLUMN plan_family TEXT DEFAULT 'professional';
    END IF;
    
    -- Champ current_period_end (date de fin de période)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'current_period_end') THEN
        ALTER TABLE profiles ADD COLUMN current_period_end TIMESTAMP WITH TIME ZONE;
    END IF;
    
    -- Champ canceled_at (date d'annulation)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profiles' AND column_name = 'canceled_at') THEN
        ALTER TABLE profiles ADD COLUMN canceled_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- ============================================
-- TABLE WEBHOOK_LOGS
-- Pour le debugging des webhooks Stripe
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
-- TABLE NOTIFICATIONS
-- Pour les alertes utilisateur (paiement échoué, etc.)
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    action_url TEXT,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- INDEX POUR PERFORMANCE
-- ============================================
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_customer ON profiles(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_profiles_plan ON profiles(plan);
CREATE INDEX IF NOT EXISTS idx_profiles_plan_family ON profiles(plan_family);
CREATE INDEX IF NOT EXISTS idx_webhook_logs_event_type ON webhook_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_logs_event_id ON webhook_logs(event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, read);

-- ============================================
-- RLS (Row Level Security) POUR LES NOUVELLES TABLES
-- ============================================
ALTER TABLE webhook_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Webhook logs : accès service role uniquement (backend)
DROP POLICY IF EXISTS "Service role full access webhook_logs" ON webhook_logs;
CREATE POLICY "Service role full access webhook_logs"
    ON webhook_logs FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Notifications : les utilisateurs peuvent voir les leurs
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
```

---

## ⚙️ Configuration Railway (Variables d'Environnement)

Ces variables doivent être configurées dans Railway avec les Price IDs de votre dashboard Stripe :

### Plans Professionnels
```
STRIPE_PRICE_STARTER=price_xxxxx          # Premium 199€/mois
STRIPE_PRICE_STARTER_ANNUAL=price_xxxxx   # Premium 179€/mois annuel
STRIPE_PRICE_PRO=price_xxxxx              # Pro 589€/mois
STRIPE_PRICE_PRO_ANNUAL=price_xxxxx       # Pro 530€/mois annuel
STRIPE_PRICE_MAX=price_xxxxx              # Max 1199€/mois
STRIPE_PRICE_MAX_ANNUAL=price_xxxxx       # Max 1079€/mois annuel
```

### Plans Creator
```
STRIPE_PRICE_BASIC_MONTHLY=price_xxxxx    # Basic 34,99€/mois
STRIPE_PRICE_BASIC_YEARLY=price_xxxxx     # Basic 31,49€/mois annuel
STRIPE_PRICE_PRO_MONTHLY=price_xxxxx      # Pro 65,99€/mois
STRIPE_PRICE_PRO_YEARLY=price_xxxxx       # Pro 59,39€/mois annuel
STRIPE_PRICE_MAX_MONTHLY=price_xxxxx      # Max 89,99€/mois
STRIPE_PRICE_MAX_YEARLY=price_xxxxx       # Max 80,99€/mois annuel
```

---

## ⚠️ Points d'Attention

### Convention de Nommage
- **Plans Professionnels** utilisent le suffixe `_ANNUAL` pour l'annuel
- **Plans Creator** utilisent le suffixe `_YEARLY` pour l'annuel
- Attention aux conflits de noms :
  - `STRIPE_PRICE_PRO` = Professionnel Pro mensuel
  - `STRIPE_PRICE_PRO_MONTHLY` = Creator Pro mensuel

### Webhook Stripe
- L'URL du webhook dans Stripe doit pointer vers : `https://votre-domaine/api/webhooks/stripe`
- Les événements à activer dans Stripe :
  - `checkout.session.completed`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

### Migration des Utilisateurs Existants
- Les utilisateurs existants avec un plan "free" ne sont pas affectés
- Les utilisateurs avec des plans Creator/Professionnel existants garderont leur plan
- Le nouveau champ `plan_family` sera automatiquement rempli lors du prochain webhook
