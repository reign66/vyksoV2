# 🧪 Guide de Debug Complet (CSS + Endpoints)

Ce guide vous permet de vérifier point par point pourquoi le CSS ne s'affiche pas et pourquoi vos endpoints ne répondent pas correctement. Suivez les étapes dans l'ordre.

---

## 🎯 Symptômes décrits

- « Je n'ai toujours pas de CSS »
- « Je n'ai toujours pas de résultat sur mon endpoint »
- « Doublons quand j'essaye d'utiliser mon endpoint ou celui du front Lovable »
- « Jamais réussi à ouvrir une page basée sur Cloudflare »

---

## 🚦 Étape 0 — Pré-requis rapides

- Frontend déployé avec `NEXT_PUBLIC_BACKEND_URL` correct
- Backend accessible publiquement via `https://api.vykso.com`
- Cloudflare correctement configuré (voir `GUIDE_CLOUDFLARE.md`)
- Supabase configuré (voir `GUIDE_SUPABASE.md`)
- Railway OK (voir `GUIDE_RAILWAY.md`)

---

## 1) Debug CSS (Next.js + Cloudflare)

### 1.1 Vérifier la compilation et l'import du CSS

- Fichier `frontend/app/layout.tsx` importe `./globals.css` (OK dans votre code)
- `tailwind.config.ts` contient bien `./app/**/*` dans `content` (OK)
- `postcss.config.mjs` contient `tailwindcss` et `autoprefixer` (OK)

Si en local vous avez le style, le problème est côté déploiement/CDN.

### 1.2 Vérifier les assets statiques en prod

- Ouvrez `https://vykso.com`
- DevTools (F12) > onglet Network
- Filtrez par `/_next/static/`
- Contrôlez :
  - Status = 200
  - Content-Type = `text/css` pour les `.css`, `application/javascript` pour les `.js`
  - Pas de 404/403

Si Content-Type = `text/html`: c'est un mauvais cache Cloudflare.

➡️ Action: Purgez le cache Cloudflare (Caching > Purge > Purge Everything) et rechargez avec Ctrl+Shift+R.

### 1.3 Vérifier les headers côté Next.js

- `frontend/next.config.js` n'impose pas d'en-têtes sur `/_next/static/*` (OK)
- Header `X-Content-Type-Options: nosniff` est ajouté (OK)

Optionnel: Ajouter une Page Rule Cloudflare pour `/_next/static/*` (voir guide Cloudflare) si besoin.

### 1.4 Vérifier l'URL du frontend

- Votre domaine `vykso.com` doit pointer sur le service frontend Railway
- Le proxy Cloudflare doit être activé (nuage orange)

---

## 2) Debug endpoints (CORS + DNS + variables)

### 2.1 Testez la santé du backend

```bash
curl -i https://api.vykso.com/health
```
- Attendu: `HTTP/2 200` + body `{"status":"ok"}`
- Si échec: problème DNS/SSL/Service Railway down

### 2.2 Vérifiez les CORS sur le backend

Dans `main.py`, CORS autorise :
- `https://vykso.com`
- `https://www.vykso.com`
- `FRONTEND_URL` (variable Railway)

➡️ Action: Dans Railway (backend), définissez `FRONTEND_URL=https://vykso.com` puis redeploy.

### 2.3 Vérifiez la variable côté frontend

Dans Railway (frontend) ou Vercel :
- `NEXT_PUBLIC_BACKEND_URL=https://api.vykso.com`

➡️ Évitez d'utiliser l'URL Lovable; ne mélangez pas plusieurs backends.

### 2.4 Évitez les "doublons" de services

Problème possible: vous avez plusieurs services (ou domaines) pointant vers le même code avec des caches différents.

- Un SEUL backend: `api.vykso.com -> Railway backend`
- Un SEUL frontend: `vykso.com -> Railway frontend`
- Purgez le cache Cloudflare

### 2.5 Test d'un flux complet via le frontend

1. Ouvrez `https://vykso.com`
2. Connectez-vous via Google
3. Ouvrez DevTools > Network
4. Lancez une génération de vidéo
5. Surveillez les requêtes vers `https://api.vykso.com/api/...`
6. Vérifiez les codes HTTP et les messages d'erreur (CORS? 4xx? 5xx?)

---

## 3) Debug Supabase (users, jobs, storage)

### 3.1 Vérifier l'accès Supabase côté backend

- Railway backend: `SUPABASE_URL` et `SUPABASE_SERVICE_KEY`/`_ROLE_KEY` définis
- Le bucket `vykso-videos` existe

### 3.2 Vérifier la base et RLS

- Tables `users`, `video_jobs` existent (voir `database-schema.sql` et guides)
- Fonction `decrement_credits` existe

### 3.3 Vérifier l'auth Google

- Provider Google activé dans Supabase
- Redirect URL dans Supabase: `https://vykso.com/auth/callback`
- Origins: `https://vykso.com` et `https://www.vykso.com`

---

## 4) Debug Railway

### 4.1 Logs

- Backend: vérifiez les erreurs Stripe, Supabase, génération vidéo
- Frontend: vérifiez les erreurs de build Next.js

### 4.2 Healthchecks

- Backend `/health` doit être OK
- Frontend `/api/health` doit être OK

### 4.3 Redeploy propre

- Après tout changement de variables, forcez un redeploy
- Purgez le cache Cloudflare ensuite

---

## 5) Checklists express

### Frontend (vykso.com)
- [ ] CNAME vers Railway (nuage orange)
- [ ] `NEXT_PUBLIC_BACKEND_URL=https://api.vykso.com`
- [ ] Cache Cloudflare purgé
- [ ] CSS/JS chargés (`/_next/static/*` 200 OK)

### Backend (api.vykso.com)
- [ ] CNAME vers Railway (nuage gris)
- [ ] `/health` renvoie 200 OK
- [ ] CORS autorise `https://vykso.com`
- [ ] SUPABASE_* et STRIPE_* configurés

### Supabase
- [ ] Tables + RLS + fonction `decrement_credits`
- [ ] Buckets `vykso-videos` et `video-images`
- [ ] Google OAuth activé

### Cloudflare
- [ ] SSL/TLS en Full (strict)
- [ ] Always Use HTTPS activé
- [ ] Page Rule pour `/_next/static/*` (optionnel)
- [ ] Aucune règle bloquante sur `/api/*`

---

## 6) Commandes utiles

```bash
# Tester la santé API
curl -i https://api.vykso.com/health

# Tester une route backend
curl -i -X POST https://api.vykso.com/api/videos/generate \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"00000000-0000-0000-0000-000000000000","niche":"tech","duration":10,"quality":"basic"}'

# Vérifier les DNS
dig +noall +answer vykso.com
 dig +noall +answer api.vykso.com
```

---

## 7) Notes spécifiques à votre repo

- `frontend/next.config.js` : OK (headers de sécurité, standalone)
- `frontend/app/layout.tsx` : import `./globals.css` OK
- `frontend/tailwind.config.ts` : includes `./app/**/*` OK
- `frontend/app/api/health/route.ts` : healthcheck pour Railway OK
- `frontend/lib/api.ts` : baseURL dépend de `NEXT_PUBLIC_BACKEND_URL`
- `main.py` : CORS inclut `https://vykso.com` et `FRONTEND_URL`

---

Si vous bloquez à une étape, dites-moi précisément ce qui échoue (capture d'écran de Network/Console + message d'erreur), je vous dirai exactement quoi changer.
