# 🗄️ Guide Complet Supabase - Configuration Vykso

## 📋 Vue d'ensemble

Ce guide vous accompagne étape par étape pour configurer correctement Supabase pour votre application Vykso, incluant la base de données, l'authentification, et le stockage.

---

## ✅ ÉTAPE 1 : Créer et configurer le projet Supabase

### 1.1 Créer un compte Supabase

1. Allez sur [https://supabase.com](https://supabase.com)
2. Cliquez sur **"Start your project"** ou **"Sign in"**
3. Connectez-vous avec GitHub, Google, ou email

### 1.2 Créer un nouveau projet

1. Cliquez sur **"New Project"**
2. Remplissez les informations :
   - **Name** : `vykso` (ou un nom de votre choix)
   - **Database Password** : Générez un mot de passe fort (⚠️ SAUVEZ-LE)
   - **Region** : Choisissez la région la plus proche (ex: `West Europe (Paris)`)
   - **Pricing Plan** : Free tier pour commencer

3. Cliquez sur **"Create new project"**
4. Attendez 2-3 minutes que le projet soit créé

### 1.3 Récupérer les clés d'API

1. Une fois le projet créé, allez dans **Settings** (icône d'engrenage) > **API**
2. Notez ces informations (⚠️ IMPORTANT - vous en aurez besoin) :

```
Project URL: https://xxxxx.supabase.co
anon/public key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**⚠️ SÉCURITÉ :**
- **anon key** : Sécurisée pour le frontend (utilisée dans `NEXT_PUBLIC_SUPABASE_ANON_KEY`)
- **service_role key** : ⚠️ TRÈS SENSIBLE - À utiliser UNIQUEMENT côté backend (jamais dans le frontend)

---

## ✅ ÉTAPE 2 : Créer les tables de base de données

### 2.1 Accéder à l'éditeur SQL

1. Dans le menu de gauche, cliquez sur **SQL Editor**
2. Cliquez sur **"New query"**

### 2.2 Créer la table `users`

Copiez et exécutez cette requête :

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

-- Index pour améliorer les performances
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_plan ON users(plan);
```

**Cliquez sur "Run"** (ou Ctrl+Enter) pour exécuter.

### 2.3 Créer la table `video_jobs`

```sql
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

-- Index pour améliorer les performances
CREATE INDEX IF NOT EXISTS idx_video_jobs_user_id ON video_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_jobs(status);
CREATE INDEX IF NOT EXISTS idx_video_jobs_created_at ON video_jobs(created_at DESC);
```

**Cliquez sur "Run"** pour exécuter.

### 2.4 Vérifier que les tables sont créées

1. Allez dans **Table Editor** (dans le menu de gauche)
2. Vous devriez voir les tables `users` et `video_jobs`
3. Vérifiez que les colonnes correspondent

---

## ✅ ÉTAPE 3 : Configurer Row Level Security (RLS)

### 3.1 Activer RLS sur la table `users`

Dans le **SQL Editor**, exécutez :

```sql
-- Activer RLS sur users
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy : Les utilisateurs peuvent voir leurs propres données
CREATE POLICY "Users can view their own data"
    ON users FOR SELECT
    USING (auth.uid() = id);

-- Policy : Les utilisateurs peuvent mettre à jour leurs propres données
CREATE POLICY "Users can update their own data"
    ON users FOR UPDATE
    USING (auth.uid() = id);

-- Policy : Le service role peut tout faire (pour le backend)
CREATE POLICY "Service role can do everything"
    ON users FOR ALL
    USING (auth.role() = 'service_role');
```

**⚠️ IMPORTANT :** La dernière policy permet au backend (avec service_role key) de faire toutes les opérations, ce qui est nécessaire pour synchroniser les utilisateurs.

### 3.2 Activer RLS sur la table `video_jobs`

```sql
-- Activer RLS sur video_jobs
ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY;

-- Policy : Les utilisateurs peuvent voir leurs propres jobs
CREATE POLICY "Users can view their own jobs"
    ON video_jobs FOR SELECT
    USING (auth.uid() = user_id);

-- Policy : Les utilisateurs peuvent créer leurs propres jobs
CREATE POLICY "Users can insert their own jobs"
    ON video_jobs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Policy : Le service role peut tout faire (pour le backend)
CREATE POLICY "Service role can do everything"
    ON video_jobs FOR ALL
    USING (auth.role() = 'service_role');
```

---

## ✅ ÉTAPE 4 : Créer la fonction `decrement_credits`

### 4.1 Exécuter la fonction SQL

Dans le **SQL Editor**, copiez et exécutez :

```sql
CREATE OR REPLACE FUNCTION decrement_credits(p_user_id UUID, p_amount INTEGER)
RETURNS INTEGER AS $$
DECLARE
    current_credits INTEGER;
BEGIN
    -- Récupérer les crédits actuels
    SELECT credits INTO current_credits 
    FROM users 
    WHERE id = p_user_id;
    
    -- Vérifier que l'utilisateur existe
    IF current_credits IS NULL THEN
        RAISE EXCEPTION 'User not found';
    END IF;
    
    -- Vérifier que l'utilisateur a assez de crédits
    IF current_credits < p_amount THEN
        RAISE EXCEPTION 'Insufficient credits';
    END IF;
    
    -- Décrementer les crédits
    UPDATE users 
    SET credits = credits - p_amount,
        updated_at = NOW()
    WHERE id = p_user_id;
    
    -- Retourner le nouveau nombre de crédits
    RETURN current_credits - p_amount;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

**Cliquez sur "Run"** pour exécuter.

### 4.2 Vérifier que la fonction est créée

1. Allez dans **Database** > **Functions** (dans le menu de gauche)
2. Vous devriez voir la fonction `decrement_credits`

---

## ✅ ÉTAPE 5 : Configurer l'authentification Google OAuth

### 5.1 Créer un projet Google Cloud Console

1. Allez sur [Google Cloud Console](https://console.cloud.google.com)
2. Créez un nouveau projet (ou utilisez un existant)
3. Nommez-le "Vykso" ou similaire

### 5.2 Configurer OAuth Consent Screen

1. Dans Google Cloud Console, allez dans **APIs & Services** > **OAuth consent screen**
2. Choisissez **External** (ou Internal si vous avez Google Workspace)
3. Remplissez les informations :
   - **App name** : Vykso
   - **User support email** : votre email
   - **Developer contact information** : votre email
4. Cliquez sur **Save and Continue**
5. Dans **Scopes**, cliquez sur **Add or Remove Scopes**
   - Sélectionnez : `.../auth/userinfo.email` et `.../auth/userinfo.profile`
6. Cliquez sur **Save and Continue**
7. Dans **Test users**, ajoutez votre email (pour le mode test)
8. Cliquez sur **Save and Continue**

### 5.3 Créer les credentials OAuth

1. Allez dans **APIs & Services** > **Credentials**
2. Cliquez sur **Create Credentials** > **OAuth client ID**
3. Choisissez **Web application**
4. Remplissez :
   - **Name** : Vykso Web Client
   - **Authorized JavaScript origins** :
     ```
     http://localhost:3000
     https://vykso.com
     https://www.vykso.com
     ```
   - **Authorized redirect URIs** :
     ```
     http://localhost:3000/auth/callback
     https://vykso.com/auth/callback
     https://www.vykso.com/auth/callback
     https://votre-projet.supabase.co/auth/v1/callback
     ```
5. Cliquez sur **Create**
6. **⚠️ IMPORTANT :** Copiez le **Client ID** et le **Client Secret** (vous en aurez besoin)

### 5.4 Configurer Google dans Supabase

1. Dans Supabase, allez dans **Authentication** > **Providers** (dans le menu de gauche)
2. Trouvez **Google** dans la liste
3. Activez le toggle **"Enable Google provider"**
4. Entrez :
   - **Client ID (for OAuth)** : Le Client ID de Google Cloud Console
   - **Client Secret (for OAuth)** : Le Client Secret de Google Cloud Console
5. Cliquez sur **Save**

### 5.5 Vérifier les redirect URLs dans Supabase

1. Toujours dans **Authentication** > **URL Configuration**
2. Vérifiez que **Site URL** est : `https://vykso.com`
3. Vérifiez que **Redirect URLs** contient :
   ```
   https://vykso.com/auth/callback
   https://www.vykso.com/auth/callback
   http://localhost:3000/auth/callback
   ```

---

## ✅ ÉTAPE 6 : Configurer Storage (Buckets)

### 6.1 Créer le bucket `vykso-videos`

1. Allez dans **Storage** (dans le menu de gauche)
2. Cliquez sur **"New bucket"**
3. Remplissez :
   - **Name** : `vykso-videos`
   - **Public bucket** : ✅ **OUI** (pour que les vidéos soient accessibles)
   - **File size limit** : 500 MB (ou selon vos besoins)
   - **Allowed MIME types** : `video/mp4,video/webm,video/quicktime`
4. Cliquez sur **"Create bucket"**

### 6.2 Configurer les policies pour `vykso-videos`

1. Cliquez sur le bucket `vykso-videos`
2. Allez dans l'onglet **Policies**
3. Cliquez sur **"New Policy"**

**Policy 1 : Lecture publique (pour que tout le monde puisse lire les vidéos)**

```sql
-- Policy name: Public read access
-- Policy definition:
(
  bucket_id = 'vykso-videos'::text
  AND (auth.role() = 'anon'::text)
)
-- Operations: SELECT
```

**Policy 2 : Upload autorisé pour les utilisateurs authentifiés**

```sql
-- Policy name: Authenticated users can upload
-- Policy definition:
(
  bucket_id = 'vykso-videos'::text
  AND (auth.role() = 'authenticated'::text)
)
-- Operations: INSERT, UPDATE
```

**Policy 3 : Service role peut tout faire (pour le backend)**

```sql
-- Policy name: Service role full access
-- Policy definition:
(
  bucket_id = 'vykso-videos'::text
  AND (auth.role() = 'service_role'::text)
)
-- Operations: SELECT, INSERT, UPDATE, DELETE
```

### 6.3 Créer le bucket `video-images` (pour les images uploadées)

1. Créez un nouveau bucket : **Name** : `video-images`
2. **Public bucket** : ✅ **OUI**
3. **File size limit** : 10 MB
4. **Allowed MIME types** : `image/jpeg,image/png,image/webp`

5. Configurez les mêmes policies que pour `vykso-videos`

---

## ✅ ÉTAPE 7 : Vérifier les variables d'environnement

### 7.1 Variables pour le Frontend (Next.js)

Dans votre fichier `.env.local` ou dans Railway/Vercel, configurez :

```env
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Où trouver ces valeurs :**
- Settings > API > Project URL
- Settings > API > anon public key

### 7.2 Variables pour le Backend (Railway)

Dans Railway, configurez :

```env
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
VIDEOS_BUCKET=vykso-videos
```

**⚠️ IMPORTANT :**
- `SUPABASE_SERVICE_KEY` et `SUPABASE_SERVICE_ROLE_KEY` doivent être identiques
- Utilisez la **service_role key** (pas l'anon key)
- Ne jamais exposer la service_role key dans le frontend

---

## ✅ ÉTAPE 8 : Tester la connexion

### 8.1 Test de connexion depuis le frontend

1. Allez sur `https://vykso.com/login`
2. Cliquez sur "Continuer avec Google"
3. Connectez-vous avec votre compte Google
4. Vérifiez que vous êtes redirigé vers `/dashboard`

### 8.2 Test de création d'utilisateur

1. Après connexion, vérifiez dans Supabase :
   - **Authentication** > **Users** : votre utilisateur doit apparaître
   - **Table Editor** > **users** : un enregistrement doit être créé

### 8.3 Test de génération de vidéo

1. Dans le dashboard, essayez de générer une vidéo
2. Vérifiez dans Supabase :
   - **Table Editor** > **video_jobs** : un nouveau job doit être créé
   - Le statut doit être `pending` puis `generating` puis `completed`

### 8.4 Test de stockage

1. Après génération d'une vidéo, vérifiez :
   - **Storage** > **vykso-videos** : la vidéo doit être présente
   - Cliquez sur la vidéo pour vérifier l'URL publique

---

## 🔧 PROBLÈMES COURANTS ET SOLUTIONS

### ❌ Problème 1 : Erreur "Invalid API key"

**Solutions :**

1. **Vérifier que vous utilisez la bonne clé :**
   - Frontend : `anon key` (commence souvent par `eyJhbG...`)
   - Backend : `service_role key` (différente de l'anon key)

2. **Vérifier que les variables d'environnement sont bien définies :**
   - Dans Railway : Settings > Variables
   - Dans Vercel : Settings > Environment Variables

3. **Vérifier qu'il n'y a pas d'espaces avant/après les clés**

### ❌ Problème 2 : Erreur "Row Level Security policy violation"

**Solutions :**

1. **Vérifier que RLS est correctement configuré :**
   - Les policies doivent permettre au service_role de tout faire
   - Les policies pour les utilisateurs doivent utiliser `auth.uid()`

2. **Vérifier que le backend utilise bien la service_role key :**
   - Dans `main.py`, vérifiez que `get_client()` utilise la service_role key

### ❌ Problème 3 : Google OAuth ne fonctionne pas

**Solutions :**

1. **Vérifier les redirect URLs :**
   - Dans Google Cloud Console, les redirect URIs doivent inclure :
     - `https://votre-projet.supabase.co/auth/v1/callback`
     - `https://vykso.com/auth/callback`

2. **Vérifier que Google est activé dans Supabase :**
   - Authentication > Providers > Google : doit être activé

3. **Vérifier les credentials :**
   - Client ID et Client Secret doivent être corrects
   - Pas d'espaces avant/après

### ❌ Problème 4 : Les vidéos ne s'uploadent pas dans Storage

**Solutions :**

1. **Vérifier que le bucket existe :**
   - Storage > Vérifiez que `vykso-videos` existe

2. **Vérifier les policies :**
   - Le service_role doit avoir les permissions INSERT et UPDATE

3. **Vérifier la variable d'environnement :**
   - `VIDEOS_BUCKET=vykso-videos` doit être défini dans Railway

4. **Vérifier les logs Railway :**
   - Dashboard > Service > Logs
   - Cherchez les erreurs liées à Supabase

---

## 📝 Checklist finale Supabase

Avant de dire que Supabase est prêt, vérifiez :

- [ ] Projet Supabase créé et actif
- [ ] Tables `users` et `video_jobs` créées
- [ ] RLS activé et policies configurées
- [ ] Fonction `decrement_credits` créée
- [ ] Google OAuth configuré (Client ID + Secret)
- [ ] Buckets `vykso-videos` et `video-images` créés
- [ ] Policies Storage configurées
- [ ] Variables d'environnement configurées (frontend + backend)
- [ ] Test de connexion Google : fonctionne
- [ ] Test de création d'utilisateur : fonctionne
- [ ] Test de génération de vidéo : fonctionne
- [ ] Test de stockage : vidéos uploadées correctement

---

## 🆘 Support

Si après avoir suivi ce guide vous avez toujours des problèmes :

1. **Vérifiez les logs Supabase :** Dashboard > Logs
2. **Vérifiez les logs Railway :** Pour les erreurs backend
3. **Vérifiez les DevTools du navigateur :** F12 > Console
4. **Testez en local :** Vérifiez que les variables d'environnement sont correctes

---

**Dernière mise à jour :** 2024-11-04
