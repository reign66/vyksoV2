# Vykso Backend

API backend de génération automatique de vidéos IA (Sora 2 / Veo 3.1 / Wan self-hosted), avec abonnements Stripe (6 offres), upload YouTube et notifications WhatsApp.

## Stack

- **FastAPI** — API REST (process long-running requis : jobs vidéo de plusieurs minutes + ffmpeg)
- **Supabase** — Database + Auth + Storage
- **Stripe** — abonnements (3 offres Creator 9:16 + 3 offres Professional 16:9) + packs de crédits
- **Sora 2 (OpenAI) / Veo 3.1 (Google) / Wan (self-hosted, optionnel)** — génération vidéo
- **OpenWA** (optionnel) — notifications WhatsApp (nouvel abonné, paiement échoué, job échoué…)
- **Docker** — déploiement conteneur (Railway / Render / Fly.io / VPS). ⚠️ Incompatible serverless (Vercel) : jobs longs + ffmpeg.

## Offres / crédits (1 crédit = 1 seconde de vidéo)

| Plan (`profiles.plan`) | Prix | Crédits/mois | Format |
|---|---|---|---|
| creator_basic | 34,99 € | 100 | 9:16, durée fixe |
| creator_pro | 65,99 € | 200 | 9:16, durée fixe |
| creator_max | 89,99 € | 300 | 9:16, durée fixe |
| professional_starter | 199 € | 600 | 16:9, durée variable |
| professional_pro | 589 € | 1200 | 16:9, durée variable |
| professional_max | 1 199 € | 1800 | 16:9, durée variable |

`profiles.plan_family` (`creator` / `professional`) est la source de vérité du tier, dérivée du préfixe du plan.

## Setup local

```bash
git clone https://github.com/reign66/vyksoV2.git
cd vyksoV2
pip install -r requirements.txt
cp .env.example .env   # remplir les credentials
# ffmpeg requis dans le PATH (concat vidéo)
uvicorn main:app --reload --port 8080
```

## Base de données

- **Projet Supabase vierge** : exécuter `database-schema.sql` uniquement.
- **Projet existant** : exécuter `migration-2026-06-audit-fixes.sql` uniquement (idempotente).
- `migration-tier-update.sql` est **obsolète** — ne pas exécuter.

## Webhook Stripe

Une seule URL à configurer dans le dashboard Stripe : `POST /api/webhooks/stripe`.
Événements : `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed`.
Idempotent (index unique sur `webhook_logs.event_id`) ; les erreurs de traitement renvoient 500 pour déclencher le retry Stripe.

## Déploiement

Voir `DEPLOYMENT.md`. Résumé : image Docker (ffmpeg inclus), healthcheck `/health`, port `$PORT` (défaut 8080). Conçu pour Railway (`railway.json` fourni) ou tout hébergeur de conteneurs. Le frontend (Lovable → vykso.com) appelle l'API via `api.vykso.com` (CNAME vers l'hébergeur du backend).
