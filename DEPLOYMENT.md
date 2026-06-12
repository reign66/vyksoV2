# Déploiement Vykso Backend

> ⚠️ Ce backend exige un **process long-running** (jobs vidéo de plusieurs minutes via BackgroundTasks, binaire ffmpeg, fichiers temporaires). Il est **incompatible avec du serverless** (Vercel Functions). Cibles : Railway, Render, Fly.io, VPS Docker.

## 1. Supabase

1. Créer (ou réutiliser) un projet sur [supabase.com](https://supabase.com).
2. SQL Editor :
   - **Projet vierge** → exécuter `database-schema.sql` (état final complet).
   - **Projet existant** → exécuter `migration-2026-06-audit-fixes.sql` (idempotente — colonnes `progress`/`credits_cost`/`cancel_at_period_end`, fonctions de crédits atomiques, index unique webhook, taxonomie de plans).
   - Ne **jamais** exécuter `migration-tier-update.sql` (obsolète).
3. Storage : créer les buckets `vykso-videos` (vidéos générées) et `video-images` (images de référence uploadées par le frontend). Recommandation : `vykso-videos` **privé** (le backend sert les vidéos via les endpoints proxy authentifiés `/download` et `/stream`).
4. Auth : activer Google OAuth (utilisé par le frontend Lovable).
5. Récupérer : `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.

## 2. Stripe

1. Créer les 12 prix (6 offres × mensuel/annuel) — montants dans `.env.example`.
2. Renseigner les 12 `STRIPE_PRICE_*` + `STRIPE_SECRET_KEY`.
3. Webhook : **une seule URL** → `https://<backend>/api/webhooks/stripe`, événements `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed` → récupérer `STRIPE_WEBHOOK_SECRET`.
4. (Optionnel) Configurer Stripe Tax dans le dashboard puis passer `STRIPE_AUTOMATIC_TAX=true`.

## 3. Google / OpenAI

- `GOOGLE_API_KEY` / `GEMINI_API_KEY` : clé Google AI Studio (Veo 3.1, Gemini, Imagen).
- `OPENAI_API_KEY` : clé OpenAI avec accès Sora 2.
- `GOOGLE_CLIENT_SECRETS_JSON` : OAuth client (type Web) pour l'upload YouTube ; redirect URI = `https://<backend>/api/auth/youtube/callback`.
  ⚠️ **L'ancien client secret a fuité dans l'historique git — le révoquer et en créer un nouveau.**

## 4. Hébergement du backend (Docker)

L'image installe ffmpeg, expose `$PORT` (défaut 8080), healthcheck `GET /health`.

### Railway (config fournie)
1. Nouveau projet → Deploy from GitHub repo `reign66/vyksoV2` (branche `main`).
2. `railway.json` est lu automatiquement (build Dockerfile, healthcheck `/health`).
3. Renseigner toutes les variables d'environnement (`.env.example` comme checklist).
4. Settings → Domains → custom domain `api.vykso.com` (le CNAME existe déjà chez Cloudflare, il pointait vers l'ancienne app `vyksov2-prod.up.railway.app` — le mettre à jour vers le nouveau domaine Railway).

### Render (alternative)
New → Web Service → repo GitHub → Runtime Docker → variables d'env → custom domain `api.vykso.com`.

## 5. DNS

`api.vykso.com` (Cloudflare) → CNAME vers le domaine fourni par l'hébergeur. Vérifier ensuite : `curl https://api.vykso.com/health` → `{"status":"ok"}`.

## 6. Frontend (Lovable → vykso.com)

Le frontend appelle l'API sur `api.vykso.com` et utilise Supabase Auth directement. Après redéploiement du backend, vérifier dans Lovable que la base URL de l'API est bien `https://api.vykso.com`.

## 7. Optionnel

- **Notifications WhatsApp** : déployer la passerelle [OpenWA](https://github.com/rmyndharis/OpenWA) (conteneur persistant, dashboard :2886, API :2785), créer une session, scanner le QR avec un numéro dédié, puis renseigner `OPENWA_URL`, `OPENWA_API_KEY`, `OPENWA_SESSION_ID`, `OPENWA_CHAT_ID`.
- **Provider Wan self-hosted** : héberger un micro-service GPU respectant le contrat documenté dans `wan_client.py`, puis renseigner `WAN_ENDPOINT` (+ `WAN_API_KEY`). ⚠️ Ne pas exposer l'app Wan2GP telle quelle pour un SaaS payant : sa licence l'interdit ; utiliser les poids Wan 2.x (Apache 2.0) via votre propre wrapper.

## 8. Vérification post-déploiement

1. `GET /health` → ok.
2. Créer un compte via le frontend → profil créé (10 crédits).
3. Checkout test (clé test Stripe) → webhook reçu → plan + crédits mis à jour.
4. Générer une vidéo courte (Veo basic) → job `completed`, vidéo lisible.
5. Logs : vérifier l'absence d'erreurs `PGRST` (colonnes manquantes = migration non exécutée).
