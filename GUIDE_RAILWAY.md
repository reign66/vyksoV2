# 🚆 Guide Complet Railway - Backend FastAPI et Frontend Next.js

## 📋 Vue d'ensemble

Ce guide vous accompagne pour déployer votre backend FastAPI (racine du repo) et votre frontend Next.js (dossier `frontend/`) sur Railway, avec une checklist de vérification de la data existante.

---

## ✅ ÉTAPE 1 : Structure du projet

- Backend (FastAPI) à la racine:
  - `Dockerfile` (fourni)
  - `requirements.txt`
  - `main.py`
- Frontend (Next.js) dans `frontend/`:
  - `package.json`
  - `next.config.js`
  - `railway.json` spécifique frontend

---

## ✅ ÉTAPE 2 : Déployer le Backend

### 2.1 Créer un projet Railway

1. Allez sur `https://railway.app`
2. Créez un nouveau projet
3. Connectez votre repo GitHub ou utilisez la CLI Railway

### 2.2 Créer un service Backend

1. Dans le projet Railway, cliquez sur **New** > **Empty Service** > **Deploy from GitHub**
2. Sélectionnez votre repo
3. Railway détectera le `Dockerfile` à la racine (confirmé par `railway.json` global)

### 2.3 Variables d'environnement Backend

Ajoutez dans Settings > Variables :

```env
# Supabase
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
VIDEOS_BUCKET=vykso-videos

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_MAX=price_...

# AI APIs
OPENAI_API_KEY=sk-...
GOOGLE_GENAI_API_KEY=...

# CORS / Frontend
FRONTEND_URL=https://vykso.com
ENVIRONMENT=production
PORT=8080
```

- Healthcheck: `/health` (déjà configuré)
- Start command: `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}` (déjà configuré)

### 2.4 Lier un domaine (api.vykso.com)

- Dans Cloudflare, créez `api.vykso.com` en CNAME vers votre service Railway
- Proxy: désactivé (nuage gris)

---

## ✅ ÉTAPE 3 : Déployer le Frontend

### 3.1 Créer un service Frontend

1. Dans le même projet Railway, créez un **nouveau service** depuis le repo mais en pointant le dossier `frontend/`
2. Railway utilisera `NIXPACKS` (voir `frontend/railway.json`)

### 3.2 Variables d'environnement Frontend

Ajoutez dans Settings > Variables du service frontend :

```env
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_BACKEND_URL=https://api.vykso.com
```

- Healthcheck: `/api/health` (fichier `frontend/app/api/health/route.ts`)
- Start command: `node .next/standalone/server.js` (déjà configuré)

### 3.3 Lier le domaine principal (vykso.com)

- Dans Cloudflare, `vykso.com` CNAME vers le service frontend Railway
- Proxy: activé (nuage orange)

---

## ✅ ÉTAPE 4 : Vérifier la data existante (important)

Si vous avez déjà de la data sur Railway, vérifiez :

1. Les variables d'environnement n'ont pas changé de noms
2. Le `VIDEOS_BUCKET` correspond bien au bucket dans Supabase
3. Les URLs (Frontend/Backend) sont bien alignées partout
4. Les **services ont redémarré** après changement de variables

### 4.1 Check API rapidement

```bash
curl -s https://api.vykso.com/health
```
- Attendu: `{ "status": "ok" }`

### 4.2 Check Frontend rapidement

- Ouvrez `https://vykso.com`
- DevTools > Network, rechargez la page, vérifiez `/_next/static/*` avec `200` et bon Content-Type

---

## ✅ ÉTAPE 5 : Débogage Railway

### 5.1 Logs temps réel

- Railway > Service > **Logs**
- Filtrez par erreurs (`Error`, `Traceback`, `HTTPException`)

### 5.2 Redéploiement propre

1. Modifiez une variable d'environnement (ex: ajoutez `DEPLOY_TRIGGER=$(date +%s)`)
2. Sauvegardez => forcer un redeploy

### 5.3 Healthchecks

- Si `Unhealthy`, vérifiez `healthcheckPath` et les logs

---

## ✅ ÉTAPE 6 : Checklist finale Railway

- [ ] Backend déployé et healthy (`/health` OK)
- [ ] Frontend déployé et healthy (`/api/health` OK)
- [ ] Variables d'environnement correctes (frontend + backend)
- [ ] Domaines Cloudflare configurés (frontend orange, backend gris)
- [ ] CSS chargé sur `vykso.com`
- [ ] API accessible sur `api.vykso.com`

---

## 🔧 Annexes

### A. railway.json (racine - backend)

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "sh -c 'uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}'",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### B. frontend/railway.json (frontend)

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS", "buildCommand": "npm install && npm run build" },
  "deploy": {
    "startCommand": "sh -c 'HOSTNAME=0.0.0.0 PORT=${PORT:-3000} node .next/standalone/server.js'",
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

---

**Dernière mise à jour :** 2025-11-04
