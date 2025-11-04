# 🚀 Guide de Déploiement Complet - Vykso

Ce guide vous accompagne étape par étape pour déployer votre frontend Vykso sur votre domaine personnalisé via Cloudflare, avec Supabase et Railway.

---

## 📋 Prérequis

- ✅ Un compte Cloudflare avec votre domaine configuré
- ✅ Un projet Supabase configuré
- ✅ Un projet Railway avec le backend déployé
- ✅ Un projet Railway pour le frontend (ou prêt à en créer un)

---

## 🔧 ÉTAPE 1 : Configuration Supabase

### 1.1 Vérifier les URLs de redirection

1. Allez sur [Supabase Dashboard](https://app.supabase.com)
2. Sélectionnez votre projet
3. Allez dans **Authentication** → **URL Configuration**
4. Ajoutez ces URLs dans **Redirect URLs** :
   ```
   https://votre-domaine.com/auth/callback
   https://www.votre-domaine.com/auth/callback
   http://localhost:3000/auth/callback (pour le développement)
   ```
5. Ajoutez dans **Site URL** :
   ```
   https://votre-domaine.com
   ```

### 1.2 Vérifier les variables d'environnement

Dans Supabase, allez dans **Settings** → **API** et notez :
- `Project URL` → `NEXT_PUBLIC_SUPABASE_URL`
- `anon public` key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`

---

## 🚂 ÉTAPE 2 : Configuration Railway (Frontend)

### 2.1 Créer un nouveau service Railway

1. Allez sur [Railway Dashboard](https://railway.app)
2. Créez un **New Project** ou sélectionnez votre projet existant
3. Cliquez sur **+ New** → **GitHub Repo** (ou **GitHub**)
4. Sélectionnez votre repository
5. Railway détectera automatiquement le dossier `frontend/`

### 2.2 Configurer les variables d'environnement

Dans Railway, allez dans votre service frontend → **Variables** et ajoutez :

```bash
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=votre_anon_key_supabase
NEXT_PUBLIC_BACKEND_URL=https://votre-backend.railway.app
NODE_ENV=production
PORT=3000
```

⚠️ **IMPORTANT** : Remplacez `votre-backend.railway.app` par l'URL réelle de votre backend Railway.

### 2.3 Configurer le build

Railway devrait détecter automatiquement le `railway.json` dans `frontend/`. Si ce n'est pas le cas :

1. Dans **Settings** → **Build Command** : `npm install && npm run build`
2. Dans **Settings** → **Start Command** : `npm start`
3. Dans **Settings** → **Root Directory** : `/frontend`

### 2.4 Générer le domaine Railway

1. Dans votre service Railway → **Settings** → **Networking**
2. Cliquez sur **Generate Domain**
3. Notez l'URL générée (ex: `vykso-frontend-production.up.railway.app`)
4. Cette URL doit fonctionner et afficher votre frontend

---

## ☁️ ÉTAPE 3 : Configuration Cloudflare

### 3.1 Ajouter un enregistrement DNS

1. Allez sur [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Sélectionnez votre domaine
3. Allez dans **DNS** → **Records**
4. Cliquez sur **Add record**
5. Configurez :
   - **Type** : `CNAME`
   - **Name** : `@` (pour le domaine racine) ou `www` (pour www.votre-domaine.com)
   - **Target** : `votre-projet.railway.app` (l'URL Railway de votre frontend)
   - **Proxy status** : ☁️ **Proxied** (orange cloud activé)
   - **TTL** : Auto
6. Cliquez sur **Save**

⚠️ **Note** : Si vous voulez les deux (avec et sans www), créez deux CNAME :
- `@` → `votre-projet.railway.app`
- `www` → `votre-projet.railway.app`

### 3.2 Configurer SSL/TLS

1. Dans Cloudflare → **SSL/TLS**
2. Vérifiez que le mode est **Full** ou **Full (strict)**
3. Attendez quelques minutes que le certificat SSL soit généré automatiquement

### 3.3 Configurer les paramètres de page

1. Allez dans **Rules** → **Page Rules**
2. Créez une nouvelle règle pour `https://votre-domaine.com/*`
3. Ajoutez ces paramètres :
   - **Cache Level** : Standard
   - **Browser Cache TTL** : Respect Existing Headers
   - **Always Use HTTPS** : On

### 3.4 Configurer les en-têtes (Optionnel - Déjà géré par Next.js)

⚠️ **IMPORTANT** : Next.js configure déjà automatiquement les en-têtes UTF-8 dans `next.config.js`. 
**NE créez PAS de règle Cloudflare pour `Content-Type`** car cela créera un doublon et peut causer des problèmes.

Si vous avez déjà créé une règle Cloudflare pour `Content-Type`, **SUPPRIMEZ-LA** :
1. Allez dans **Rules** → **Transform Rules** → **Modify Response Header**
2. Trouvez la règle `UTF-8 Content-Type` ou similaire
3. Cliquez sur **Delete** ou **Remove**

Les en-têtes de sécurité (X-Frame-Options, X-XSS-Protection, etc.) sont déjà gérés par Next.js.

### 3.5 Désactiver le cache pour le développement (Optionnel)

Si vous avez des problèmes de cache lors du développement :

1. **Rules** → **Page Rules**
2. Créez une règle pour `votre-domaine.com/*`
3. Ajoutez :
   - **Cache Level** : Bypass
   - **Disable Performance** : On

---

## 🔄 ÉTAPE 4 : Mise à jour des URLs dans le code

### 4.1 Vérifier les URLs de redirection Supabase

Dans `frontend/app/auth/callback/route.ts`, vérifiez que l'URL de redirection est correcte.

### 4.2 Vérifier les variables d'environnement

Assurez-vous que toutes les variables d'environnement sont correctement configurées dans Railway.

---

## ✅ ÉTAPE 5 : Vérification et Tests

### 5.1 Vérifier que le frontend Railway fonctionne

1. Ouvrez l'URL Railway de votre frontend (ex: `vykso-frontend-production.up.railway.app`)
2. Vous devriez voir votre page d'accueil
3. Vérifiez que les caractères spéciaux s'affichent correctement (é, è, ê, ç, etc.)

### 5.2 Vérifier que votre domaine fonctionne

1. Attendez 5-10 minutes pour la propagation DNS
2. Ouvrez `https://votre-domaine.com`
3. Vous devriez voir votre frontend
4. Vérifiez que les caractères spéciaux s'affichent correctement

### 5.3 Tester l'authentification

1. Cliquez sur "Se connecter"
2. Connectez-vous avec Google
3. Vérifiez que vous êtes redirigé vers `/auth/callback` puis `/dashboard`
4. Vérifiez que l'URL dans la barre d'adresse est votre domaine (pas Railway)

### 5.4 Tester les fonctionnalités

- ✅ Génération de vidéo
- ✅ Galerie de vidéos
- ✅ Achat de crédits
- ✅ Déconnexion

---

## 🐛 Dépannage

### Problème : Page "Not Found" sur votre domaine

**Solutions :**
1. Vérifiez que le CNAME dans Cloudflare pointe vers la bonne URL Railway
2. Vérifiez que le proxy Cloudflare est activé (☁️ orange)
3. Attendez 10-15 minutes pour la propagation DNS
4. Vérifiez dans Railway que le frontend est bien déployé et en ligne

### Problème : Caractères spéciaux affichés comme "?"

**Solutions :**
1. ⚠️ **SUPPRIMEZ** toute règle Cloudflare pour `Content-Type` si vous en avez créé une (cela crée un conflit)
2. Vérifiez que `next.config.js` contient bien la configuration UTF-8 (c'est déjà le cas)
3. Videz le cache Cloudflare : **Caching** → **Configuration** → **Purge Everything**
4. Vérifiez que les fichiers sont bien encodés en UTF-8

### Problème : Redirection vers Lovable preview

**Solutions :**
1. Vérifiez que vous utilisez bien l'URL Railway de votre frontend, pas une URL Lovable
2. Vérifiez que les variables d'environnement dans Railway sont correctes
3. Vérifiez que le build Railway utilise bien votre code, pas celui de Lovable
4. Si vous avez plusieurs services Railway, assurez-vous d'utiliser le bon

### Problème : Erreur d'authentification

**Solutions :**
1. Vérifiez que les URLs de redirection dans Supabase incluent votre domaine
2. Vérifiez que `NEXT_PUBLIC_SUPABASE_URL` et `NEXT_PUBLIC_SUPABASE_ANON_KEY` sont corrects
3. Vérifiez que l'URL dans la barre d'adresse est votre domaine (pas localhost ou Railway)

### Problème : Le frontend ne se connecte pas au backend

**Solutions :**
1. Vérifiez que `NEXT_PUBLIC_BACKEND_URL` pointe vers votre backend Railway
2. Vérifiez que le backend Railway est accessible publiquement
3. Testez l'URL du backend directement dans le navigateur

---

## 📝 Checklist Finale

Avant votre présentation, vérifiez :

- [ ] Le frontend Railway fonctionne sur l'URL Railway
- [ ] Votre domaine Cloudflare fonctionne et affiche le frontend
- [ ] Les caractères spéciaux s'affichent correctement (é, è, ê, ç, etc.)
- [ ] L'authentification Google fonctionne
- [ ] La redirection après connexion fonctionne correctement
- [ ] Le frontend se connecte au backend
- [ ] La génération de vidéo fonctionne
- [ ] La galerie de vidéos fonctionne
- [ ] L'achat de crédits fonctionne
- [ ] Le SSL est activé (https://)

---

## 🎯 URLs à vérifier

1. **Frontend Railway** : `https://votre-projet-frontend.up.railway.app`
2. **Votre domaine** : `https://votre-domaine.com`
3. **Backend Railway** : `https://votre-projet-backend.up.railway.app`
4. **Supabase Dashboard** : `https://app.supabase.com/project/votre-projet`

---

## 💡 Conseils pour la présentation

1. **Testez tout avant** : Testez toutes les fonctionnalités la veille
2. **Ayez un plan B** : Gardez l'URL Railway sous la main au cas où
3. **Vérifiez votre connexion** : Assurez-vous d'avoir une bonne connexion internet
4. **Préparez des captures d'écran** : En cas de problème technique, vous pouvez montrer des screenshots

---

## 📞 Support

Si vous rencontrez des problèmes :

1. Vérifiez les logs Railway : **Deployments** → Sélectionnez un déploiement → **View Logs**
2. Vérifiez les logs Cloudflare : **Analytics** → **Web Traffic**
3. Vérifiez la console du navigateur (F12) pour les erreurs JavaScript

---

**Bonne chance pour votre présentation ! 🚀**
