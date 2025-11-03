# Guide de D?ploiement - Vykso

## ?? Vue d'ensemble

Ce guide explique comment d?ployer votre application Vykso avec :
- **Backend FastAPI** sur Railway
- **Frontend Next.js** sur Railway (ou Vercel)
- **Domaine personnalis?** vykso.com via Cloudflare

---

## ?? Pr?requis

1. Compte Railway
2. Compte Cloudflare avec le domaine vykso.com configur?
3. Compte Supabase
4. Compte Stripe (pour les paiements)

---

## ?? ?tape 1 : Configuration Supabase

### 1.1 Cr?er les tables

Ex?cutez ces commandes SQL dans l'?diteur SQL de Supabase :

```sql
-- Table users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    credits INTEGER DEFAULT 10,
    plan TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table video_jobs
CREATE TABLE IF NOT EXISTS video_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
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

-- Index pour am?liorer les performances
CREATE INDEX IF NOT EXISTS idx_video_jobs_user_id ON video_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_jobs(status);
CREATE INDEX IF NOT EXISTS idx_video_jobs_created_at ON video_jobs(created_at DESC);
```

### 1.2 Configurer Google OAuth

1. Allez dans **Authentication > Providers** dans Supabase
2. Activez **Google**
3. Entrez vos credentials Google OAuth :
   - **Client ID** : (? r?cup?rer depuis Google Cloud Console)
   - **Client Secret** : (? r?cup?rer depuis Google Cloud Console)
4. Ajoutez l'URL de callback : `https://vykso.com/auth/callback`

**Note** : Vos credentials Google OAuth doivent ?tre configur?s dans votre projet Google Cloud Console et ajout?s dans Supabase. Ne commitez jamais ces secrets dans Git.

### 1.3 Cr?er les buckets Storage

1. Allez dans **Storage**
2. Cr?ez deux buckets :
   - `vykso-videos` (pour les vid?os finales)
   - `video-images` (pour les images upload?es)

### 1.4 Configurer Row Level Security (RLS)

```sql
-- RLS pour users
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own data"
    ON users FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update their own data"
    ON users FOR UPDATE
    USING (auth.uid() = id);

-- RLS pour video_jobs
ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own jobs"
    ON video_jobs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own jobs"
    ON video_jobs FOR INSERT
    WITH CHECK (auth.uid() = user_id);
```

### 1.5 Cr?er la fonction decrement_credits

```sql
CREATE OR REPLACE FUNCTION decrement_credits(p_user_id UUID, p_amount INTEGER)
RETURNS INTEGER AS $$
DECLARE
    current_credits INTEGER;
BEGIN
    SELECT credits INTO current_credits FROM users WHERE id = p_user_id;
    
    IF current_credits IS NULL THEN
        RAISE EXCEPTION 'User not found';
    END IF;
    
    IF current_credits < p_amount THEN
        RAISE EXCEPTION 'Insufficient credits';
    END IF;
    
    UPDATE users 
    SET credits = credits - p_amount 
    WHERE id = p_user_id;
    
    RETURN current_credits - p_amount;
END;
$$ LANGUAGE plpgsql;
```

---

## ?? ?tape 2 : D?ployer le Backend sur Railway

### 2.1 Cr?er un nouveau projet Railway

1. Allez sur [Railway](https://railway.app)
2. Cr?er un nouveau projet
3. S?lectionnez **Deploy from GitHub repo** (ou utilisez Railway CLI)

### 2.2 Configurer les variables d'environnement

Ajoutez ces variables dans les settings du projet Railway :

```
# Supabase
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_SERVICE_KEY=votre_service_role_key
SUPABASE_SERVICE_ROLE_KEY=votre_service_role_key
VIDEOS_BUCKET=vykso-videos

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_MAX=price_...

# API Keys
OPENAI_API_KEY=sk-...
GOOGLE_GENAI_API_KEY=...

# Frontend URL
FRONTEND_URL=https://vykso.com
ENVIRONMENT=production
PORT=8080
```

### 2.3 D?ployer

Railway d?tectera automatiquement le `Dockerfile` et d?ploiera.

Une fois d?ploy?, notez l'URL du backend (ex: `https://backend-production.up.railway.app`)

---

## ?? ?tape 3 : D?ployer le Frontend

### Option A : Railway (recommand? pour tout en un)

1. Cr?ez un nouveau service dans le m?me projet Railway
2. Connectez le dossier `frontend/`
3. Railway d?tectera automatiquement Next.js
4. Configurez les variables d'environnement :

```
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=votre_anon_key
NEXT_PUBLIC_BACKEND_URL=https://backend-production.up.railway.app
```

### Option B : Vercel (alternative)

1. Allez sur [Vercel](https://vercel.com)
2. Importez votre repo GitHub
3. Configurez le dossier racine : `frontend`
4. Ajoutez les m?mes variables d'environnement

---

## ?? ?tape 4 : Configurer le domaine vykso.com

### 4.1 Sur Cloudflare

1. Allez dans votre dashboard Cloudflare
2. S?lectionnez le domaine `vykso.com`
3. Allez dans **DNS**

### 4.2 Ajouter les enregistrements DNS

#### Pour le Frontend (vykso.com) :

**Si sur Railway :**
```
Type: CNAME
Name: @
Target: votre-service-frontend.railway.app
Proxy: ? (orange cloud activ?)
```

**Si sur Vercel :**
- Vercel vous donnera des instructions sp?cifiques
- G?n?ralement : CNAME vers `cname.vercel-dns.com`

#### Pour le Backend (api.vykso.com) :

```
Type: CNAME
Name: api
Target: votre-service-backend.railway.app
Proxy: ? (gris - pas de proxy pour ?viter les probl?mes avec les webhooks)
```

### 4.3 Mettre ? jour les URLs de callback

1. **Supabase** : Mettez ? jour l'URL de callback Google OAuth :
   - `https://vykso.com/auth/callback`

2. **Stripe** : Mettez ? jour les URLs de webhook :
   - URL : `https://api.vykso.com/api/webhooks/stripe`

3. **Backend** : Mettez ? jour `FRONTEND_URL` :
   - `FRONTEND_URL=https://vykso.com`

4. **Frontend** : Mettez ? jour `NEXT_PUBLIC_BACKEND_URL` :
   - `NEXT_PUBLIC_BACKEND_URL=https://api.vykso.com`

---

## ? ?tape 5 : V?rification

1. Visitez `https://vykso.com`
2. Testez la connexion Google
3. G?n?rez une vid?o test
4. V?rifiez que les paiements Stripe fonctionnent

---

## ?? Troubleshooting

### Le domaine ne fonctionne pas
- V?rifiez que les DNS sont propag?s (peut prendre jusqu'? 48h)
- D?sactivez le proxy Cloudflare pour tester

### Erreur CORS
- V?rifiez que `FRONTEND_URL` contient `https://vykso.com`
- Ajoutez `https://www.vykso.com` si n?cessaire

### OAuth ne fonctionne pas
- V?rifiez l'URL de callback dans Supabase
- V?rifiez que les credentials Google sont corrects

### Les vid?os ne se chargent pas
- V?rifiez que les buckets Supabase existent
- V?rifiez les permissions RLS sur les buckets

---

## ?? Monitoring

- **Railway** : Dashboard avec logs en temps r?el
- **Supabase** : Dashboard avec m?triques de la base
- **Cloudflare** : Analytics de trafic

---

## ?? S?curit?

- ? Ne jamais exposer `SUPABASE_SERVICE_KEY` c?t? frontend
- ? Utiliser RLS sur toutes les tables
- ? Valider tous les inputs c?t? backend
- ? Utiliser HTTPS partout (Cloudflare le force)

---

## ?? Notes importantes

### Concernant Supabase

**Vous pouvez garder Supabase** pour :
- ? Auth (Google OAuth) - tr?s pratique
- ? Database - PostgreSQL manag?, scalable
- ? Storage - pour les vid?os/images

**Alternatives si vous voulez vraiment vous en passer :**
- Auth : Auth0, Clerk, ou custom JWT
- Database : PostgreSQL sur Railway/Vercel
- Storage : Cloudflare R2 (vous avez d?j? les buckets)

**Recommandation** : Gardez Supabase pour l'instant. C'est la solution la plus simple et scalable pour votre cas d'usage.

---

## ?? Prochaines ?tapes

1. Ajouter un logo personnalis? dans `/frontend/public/logo.png`
2. Personnaliser les couleurs dans `tailwind.config.ts`
3. Ajouter des analytics (Plausible, Google Analytics)
4. Configurer un monitoring (Sentry)

---

**Besoin d'aide ?** Ouvrez une issue sur GitHub ou contactez le support.
