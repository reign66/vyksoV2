# 🔧 Solution : Authentification Google sur Vercel

## ✅ Corrections apportées au code

J'ai corrigé plusieurs problèmes dans le code :

1. **Route de callback améliorée** (`/frontend/app/auth/callback/route.ts`) :
   - Gestion des erreurs OAuth
   - Vérification du code d'authentification
   - Redirection vers la page de login avec message d'erreur en cas d'échec
   - Logs d'erreur pour le débogage

2. **Page de login améliorée** (`/frontend/app/login/page.tsx`) :
   - Affichage des erreurs d'authentification
   - Meilleure gestion de l'URL de redirection
   - Messages d'erreur clairs pour l'utilisateur

## 🔑 Configuration requise dans Supabase

### 1. Configurer les Redirect URLs dans Supabase

1. Allez sur votre projet Supabase : [https://supabase.com/dashboard](https://supabase.com/dashboard)
2. Sélectionnez votre projet
3. Allez dans **Authentication** > **URL Configuration** (dans le menu de gauche)
4. Dans **Redirect URLs**, ajoutez **toutes** ces URLs (une par ligne) :

```
http://localhost:3000/auth/callback
https://votre-app.vercel.app/auth/callback
https://votre-domaine.com/auth/callback
```

**⚠️ IMPORTANT :** Remplacez :
- `votre-app.vercel.app` par votre URL Vercel réelle (ex: `vykso-xyz123.vercel.app`)
- `votre-domaine.com` par votre domaine personnalisé si vous en avez un

5. Dans **Site URL**, mettez votre URL Vercel principale :
   ```
   https://votre-app.vercel.app
   ```
   ou votre domaine personnalisé si vous en avez un.

6. Cliquez sur **Save**

### 2. Vérifier la configuration Google OAuth

1. Toujours dans Supabase, allez dans **Authentication** > **Providers**
2. Trouvez **Google** dans la liste
3. Vérifiez que :
   - ✅ Le toggle **"Enable Google provider"** est activé
   - ✅ Le **Client ID** est rempli
   - ✅ Le **Client Secret** est rempli
4. Si ce n'est pas le cas, suivez les étapes dans `GUIDE_SUPABASE.md` section 5

---

## 🔑 Configuration requise dans Google Cloud Console

### 1. Ajouter les Redirect URIs dans Google Cloud Console

1. Allez sur [Google Cloud Console](https://console.cloud.google.com)
2. Sélectionnez votre projet
3. Allez dans **APIs & Services** > **Credentials**
4. Cliquez sur votre **OAuth 2.0 Client ID** (celui utilisé pour Supabase)
5. Dans **Authorized redirect URIs**, ajoutez **toutes** ces URLs :

```
https://votre-projet.supabase.co/auth/v1/callback
http://localhost:3000/auth/callback
https://votre-app.vercel.app/auth/callback
https://votre-domaine.com/auth/callback
```

**⚠️ IMPORTANT :** 
- Remplacez `votre-projet.supabase.co` par votre URL Supabase réelle
- Remplacez `votre-app.vercel.app` par votre URL Vercel réelle
- Remplacez `votre-domaine.com` par votre domaine personnalisé si vous en avez un

6. Dans **Authorized JavaScript origins**, ajoutez :

```
http://localhost:3000
https://votre-app.vercel.app
https://votre-domaine.com
```

7. Cliquez sur **Save**

---

## 🔑 Configuration requise dans Vercel

### 1. Vérifier les variables d'environnement

1. Allez sur [Vercel Dashboard](https://vercel.com/dashboard)
2. Sélectionnez votre projet
3. Allez dans **Settings** > **Environment Variables**
4. Vérifiez que ces variables sont définies :

```
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**⚠️ IMPORTANT :**
- Remplacez les valeurs par vos vraies valeurs Supabase
- Les variables doivent être définies pour **Production**, **Preview**, et **Development**
- Vérifiez qu'il n'y a pas d'espaces avant/après les valeurs

### 2. Redéployer après configuration

Après avoir ajouté/modifié les variables d'environnement, vous devez redéployer :

1. Dans Vercel Dashboard, allez dans **Deployments**
2. Cliquez sur les **3 points** du dernier déploiement
3. Cliquez sur **Redeploy**
4. Ou faites un nouveau commit pour déclencher un nouveau déploiement

---

## 🧪 Tester l'authentification

### 1. Vérifier les logs

1. Allez sur votre application Vercel
2. Ouvrez les DevTools (F12) > **Console**
3. Essayez de vous connecter avec Google
4. Regardez les logs dans la console pour voir les erreurs éventuelles

### 2. Vérifier le flux d'authentification

Le flux devrait être :
1. Clic sur "Continuer avec Google" → Redirection vers Google
2. Connexion avec Google → Redirection vers Supabase
3. Supabase redirige vers `/auth/callback` sur Vercel
4. La route de callback échange le code pour une session
5. Redirection vers `/dashboard`

### 3. Erreurs courantes

#### ❌ Erreur : "redirect_uri_mismatch"

**Cause :** L'URL de redirection dans Google Cloud Console ne correspond pas à celle utilisée.

**Solution :**
1. Vérifiez que l'URL dans Google Cloud Console correspond exactement à `https://votre-app.vercel.app/auth/callback`
2. Vérifiez aussi que `https://votre-projet.supabase.co/auth/v1/callback` est présent

#### ❌ Erreur : "Invalid redirect URL"

**Cause :** L'URL de redirection n'est pas autorisée dans Supabase.

**Solution :**
1. Allez dans Supabase > Authentication > URL Configuration
2. Ajoutez `https://votre-app.vercel.app/auth/callback` dans Redirect URLs
3. Sauvegardez et réessayez

#### ❌ Erreur : "Missing code" ou "No code provided"

**Cause :** Le code d'authentification n'est pas passé correctement.

**Solution :**
1. Vérifiez que les Redirect URLs sont correctement configurées dans Supabase ET Google
2. Vérifiez que les variables d'environnement sont correctes dans Vercel
3. Redéployez l'application

#### ❌ Erreur : "Invalid API key" ou "Unauthorized"

**Cause :** Les variables d'environnement Supabase ne sont pas correctement configurées.

**Solution :**
1. Vérifiez `NEXT_PUBLIC_SUPABASE_URL` et `NEXT_PUBLIC_SUPABASE_ANON_KEY` dans Vercel
2. Vérifiez qu'il n'y a pas d'espaces avant/après
3. Redéployez après modification

---

## 📝 Checklist finale

Avant de tester, vérifiez que :

- [ ] Les Redirect URLs sont configurées dans Supabase (incluant votre URL Vercel)
- [ ] Les Redirect URIs sont configurées dans Google Cloud Console (incluant votre URL Vercel)
- [ ] Les variables d'environnement sont configurées dans Vercel
- [ ] Google OAuth est activé dans Supabase avec Client ID et Secret
- [ ] L'application a été redéployée sur Vercel après les modifications
- [ ] Vous avez testé avec les DevTools ouverts pour voir les erreurs

---

## 🆘 Si ça ne fonctionne toujours pas

### 1. Vérifier les logs Vercel

1. Allez dans Vercel Dashboard > Votre projet > **Deployments**
2. Cliquez sur le dernier déploiement
3. Allez dans **Functions** > Regardez les logs de `/auth/callback`

### 2. Vérifier les logs Supabase

1. Allez dans Supabase Dashboard > Votre projet
2. Allez dans **Logs** > **Auth Logs**
3. Regardez les erreurs d'authentification

### 3. Tester en local

1. Créez un fichier `.env.local` dans `/frontend` :
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=votre_anon_key
   ```
2. Lancez `npm run dev`
3. Testez l'authentification en local
4. Si ça fonctionne en local mais pas sur Vercel, c'est un problème de configuration Vercel/Supabase

---

## 📚 Ressources

- [Documentation Supabase Auth](https://supabase.com/docs/guides/auth)
- [Documentation Next.js avec Supabase](https://supabase.com/docs/guides/auth/auth-helpers/nextjs)
- [Documentation Vercel Environment Variables](https://vercel.com/docs/concepts/projects/environment-variables)

---

**Dernière mise à jour :** 2024-12-19
