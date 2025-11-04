# 🚀 Guide Complet Cloudflare - vykso.com

## 📋 Vue d'ensemble

Ce guide vous accompagne étape par étape pour configurer correctement votre domaine **vykso.com** sur Cloudflare et résoudre les problèmes de CSS et d'endpoints.

---

## ✅ ÉTAPE 1 : Vérifier que votre domaine est actif sur Cloudflare

### 1.1 Accéder à Cloudflare Dashboard

1. Allez sur [https://dash.cloudflare.com](https://dash.cloudflare.com)
2. Connectez-vous avec vos identifiants
3. Vérifiez que **vykso.com** apparaît dans la liste de vos domaines
4. Si le domaine n'est pas là :
   - Cliquez sur **"Add a Site"**
   - Entrez `vykso.com`
   - Suivez les instructions pour changer les nameservers

### 1.2 Vérifier le statut du domaine

- Le domaine doit être **"Active"** (nuage orange)
- Si le statut est "Pending" ou "DNS Only" (nuage gris), activez le proxy

---

## ✅ ÉTAPE 2 : Configuration DNS - Frontend (vykso.com)

### 2.1 Aller dans la section DNS

1. Cliquez sur votre domaine **vykso.com**
2. Allez dans l'onglet **DNS** (dans le menu de gauche)
3. Vérifiez les enregistrements existants

### 2.2 Configurer l'enregistrement pour le Frontend

**Si vous déployez sur Railway :**

1. Dans votre projet Railway, notez l'URL du service frontend (ex: `frontend-production.up.railway.app`)
2. Dans Cloudflare DNS, ajoutez/modifiez cet enregistrement :

```
Type: CNAME
Name: @
Target: frontend-production.up.railway.app
Proxy status: 🟠 Proxied (nuage ORANGE)
TTL: Auto
```

**Si vous déployez sur Vercel :**

1. Vercel vous donnera des instructions spécifiques
2. Généralement, ajoutez :

```
Type: CNAME
Name: @
Target: cname.vercel-dns.com
Proxy status: 🟠 Proxied
```

**⚠️ IMPORTANT :** Le proxy (nuage orange) DOIT être activé pour que Cloudflare fonctionne correctement.

### 2.3 Vérifier l'enregistrement www (optionnel mais recommandé)

```
Type: CNAME
Name: www
Target: vykso.com (ou votre URL Railway/Vercel)
Proxy status: 🟠 Proxied
```

---

## ✅ ÉTAPE 3 : Configuration DNS - Backend (api.vykso.com)

### 3.1 Créer le sous-domaine pour l'API

**⚠️ CRITIQUE :** Pour les webhooks Stripe et les appels API, le backend DOIT avoir le proxy **DÉSACTIVÉ** (nuage gris).

1. Dans Cloudflare DNS, ajoutez :

```
Type: CNAME
Name: api
Target: votre-backend-production.up.railway.app
Proxy status: ⚪ DNS Only (nuage GRIS - pas de proxy)
TTL: Auto
```

**Pourquoi DNS Only ?**
- Les webhooks Stripe nécessitent l'IP réelle du serveur
- Le proxy Cloudflare peut causer des problèmes avec les longues requêtes
- Les erreurs de duplication viennent souvent du proxy mal configuré

---

## ✅ ÉTAPE 4 : Configuration SSL/TLS

### 4.1 Vérifier le mode SSL

1. Allez dans **SSL/TLS** dans le menu de gauche
2. Assurez-vous que le mode est **"Full"** ou **"Full (strict)"**
3. **NE PAS** utiliser "Flexible" (cela peut causer des problèmes de sécurité)

### 4.2 Forcer HTTPS (recommandé)

1. Allez dans **SSL/TLS** > **Edge Certificates**
2. Activez **"Always Use HTTPS"** (basculez sur ON)
3. Activez **"Minimum TLS Version"** : TLS 1.2 (ou plus récent)

---

## ✅ ÉTAPE 5 : Configuration Page Rules (pour résoudre les problèmes CSS)

### 5.1 Créer une règle pour les assets statiques

**PROBLÈME :** Cloudflare peut cacher les fichiers CSS/JS avec un mauvais Content-Type.

**SOLUTION :**

1. Allez dans **Rules** > **Page Rules** (ou **Transform Rules** dans les nouvelles versions)
2. Créez une nouvelle règle :

**URL Pattern :**
```
*vykso.com/_next/static/*
```

**Settings :**
- **Cache Level**: Standard
- **Browser Cache TTL**: 1 month
- **Edge Cache TTL**: 1 month
- **Bypass Cache on Cookie**: OFF

### 5.2 Créer une règle pour désactiver le cache sur les routes API (frontend)

**URL Pattern :**
```
*vykso.com/api/*
```

**Settings :**
- **Cache Level**: Bypass
- **Disable Performance**

---

## ✅ ÉTAPE 6 : Configuration Cache (CRITIQUE pour le CSS)

### 6.1 Aller dans Caching

1. Allez dans **Caching** > **Configuration**
2. Vérifiez les paramètres suivants :

**Cache Level :**
- Standard (recommandé pour les sites Next.js)

**Browser Cache TTL :**
- Respect Existing Headers (recommandé)

### 6.2 Purger le cache après chaque déploiement

**IMPORTANT :** Après chaque déploiement du frontend, vous DEVEZ purger le cache :

1. Allez dans **Caching** > **Purge Cache**
2. Cliquez sur **"Purge Everything"**
3. Attendez 30 secondes à 2 minutes

**Alternative :** Configurez une purge automatique dans Railway/Vercel après chaque build.

---

## ✅ ÉTAPE 7 : Configuration Speed (Optimisation)

### 7.1 Optimisations recommandées

1. Allez dans **Speed** > **Optimization**

**Activez :**
- ✅ **Auto Minify** : HTML, CSS, JavaScript (tous les trois)
- ✅ **Brotli** (compression)
- ❌ **Rocket Loader** : DÉSACTIVÉ (peut causer des problèmes avec Next.js)
- ❌ **Mirage** : DÉSACTIVÉ (obsolète)
- ✅ **Polish** : Lossless (pour les images)

### 7.2 Mobile Optimization

- Activez **"Mobile Redirect"** si vous avez une version mobile séparée
- Sinon, laissez désactivé

---

## ✅ ÉTAPE 8 : Configuration Security (Sécurité)

### 8.1 Firewall Rules

1. Allez dans **Security** > **WAF**
2. Activez le **WAF** (Web Application Firewall)
3. Vérifiez que les règles par défaut ne bloquent pas vos requêtes légitimes

### 8.2 Rate Limiting (optionnel mais recommandé)

1. Allez dans **Security** > **Rate Limiting**
2. Créez une règle pour protéger vos endpoints API :

```
Rule name: Protect API
Match: (http.request.uri.path contains "/api/")
Threshold: 100 requests per minute
Action: Block
```

---

## ✅ ÉTAPE 9 : Configuration Workers (si nécessaire)

### 9.1 Vérifier les Workers actifs

1. Allez dans **Workers & Pages**
2. Vérifiez qu'aucun Worker n'interfère avec votre domaine
3. Si vous avez des Workers, vérifiez qu'ils n'interceptent pas les requêtes CSS/JS

---

## ✅ ÉTAPE 10 : Vérification finale

### 10.1 Checklist de vérification

Avant de tester, vérifiez que :

- [ ] Le domaine `vykso.com` pointe vers votre frontend (nuage orange)
- [ ] Le sous-domaine `api.vykso.com` pointe vers votre backend (nuage gris)
- [ ] SSL/TLS est en mode "Full" ou "Full (strict)"
- [ ] "Always Use HTTPS" est activé
- [ ] Le cache a été purgé récemment
- [ ] Auto Minify est activé pour CSS/JS
- [ ] Aucune Page Rule ne bloque les assets statiques

### 10.2 Tests à effectuer

1. **Test DNS :**
   ```bash
   dig vykso.com
   dig api.vykso.com
   ```
   - `vykso.com` doit pointer vers une IP Cloudflare
   - `api.vykso.com` doit pointer vers l'IP Railway

2. **Test SSL :**
   ```bash
   curl -I https://vykso.com
   ```
   - Doit retourner `200 OK`
   - Doit avoir `strict-transport-security` header

3. **Test CSS :**
   - Ouvrez `https://vykso.com` dans votre navigateur
   - Ouvrez les DevTools (F12)
   - Allez dans l'onglet **Network**
   - Rechargez la page (Ctrl+Shift+R pour bypass cache)
   - Vérifiez que les fichiers `/_next/static/` se chargent avec `200 OK`
   - Vérifiez le Content-Type : doit être `text/css` ou `application/javascript`

4. **Test API :**
   ```bash
   curl https://api.vykso.com/health
   ```
   - Doit retourner `{"status": "ok"}`

---

## 🔧 PROBLÈMES COURANTS ET SOLUTIONS

### ❌ Problème 1 : Le CSS ne se charge pas

**Symptômes :**
- Page sans style
- Erreur 404 ou 403 sur les fichiers CSS
- Content-Type incorrect dans les DevTools

**Solutions :**

1. **Purger le cache Cloudflare :**
   - Caching > Purge Cache > Purge Everything

2. **Vérifier les Content-Types :**
   - Dans DevTools > Network, vérifiez le header `Content-Type` des fichiers CSS
   - Doit être `text/css; charset=utf-8`
   - Si c'est `text/html`, c'est un problème de cache ou de configuration

3. **Vérifier les Page Rules :**
   - Assurez-vous qu'aucune règle ne transforme les fichiers CSS
   - Vérifiez que les routes `/_next/static/*` ne sont pas bloquées

4. **Désactiver temporairement le cache :**
   - Caching > Configuration > Cache Level : Bypass (temporaire)
   - Testez si le CSS se charge
   - Si oui, le problème vient du cache

5. **Vérifier Next.js build :**
   - Assurez-vous que `next.config.js` a `output: 'standalone'`
   - Vérifiez que le build génère bien les fichiers CSS dans `.next/static/`

### ❌ Problème 2 : Erreurs de duplication sur les endpoints

**Symptômes :**
- Erreur "duplicate" ou "conflict" lors des appels API
- Les requêtes échouent avec des erreurs 409

**Solutions :**

1. **Vérifier que le backend est en DNS Only (nuage gris) :**
   - Le proxy Cloudflare peut causer des problèmes avec les webhooks
   - DNS Only garantit que les requêtes atteignent directement Railway

2. **Vérifier les headers CORS :**
   - Dans `main.py`, vérifiez que `FRONTEND_URL` contient `https://vykso.com`
   - Vérifiez que les headers CORS sont corrects

3. **Vérifier les Rate Limits :**
   - Cloudflare peut limiter les requêtes si trop de requêtes sont faites
   - Vérifiez dans Security > Events si des requêtes sont bloquées

4. **Désactiver temporairement le WAF :**
   - Security > WAF > Temporairement désactiver
   - Testez si les requêtes passent
   - Si oui, ajustez les règles WAF

### ❌ Problème 3 : Le site ne se charge pas du tout

**Symptômes :**
- Erreur 502 Bad Gateway
- Erreur 524 Timeout
- Page blanche

**Solutions :**

1. **Vérifier que Railway est actif :**
   - Allez sur Railway dashboard
   - Vérifiez que le service est "Active" et "Healthy"
   - Vérifiez les logs pour des erreurs

2. **Vérifier les DNS :**
   - Le domaine doit pointer vers Railway
   - Utilisez `dig` ou `nslookup` pour vérifier

3. **Vérifier SSL/TLS :**
   - SSL/TLS doit être en mode "Full" ou "Full (strict)"
   - Railway doit avoir un certificat SSL valide

4. **Vérifier les Workers :**
   - Aucun Worker ne doit intercepter les requêtes
   - Désactivez temporairement les Workers pour tester

---

## 📝 Checklist finale avant le lancement

Avant de dire que tout est prêt, vérifiez :

- [ ] DNS configuré correctement (frontend orange, backend gris)
- [ ] SSL/TLS en mode Full
- [ ] Always Use HTTPS activé
- [ ] Cache purgé après le dernier déploiement
- [ ] Auto Minify activé
- [ ] Page Rules configurées pour les assets statiques
- [ ] WAF activé mais ne bloque pas les requêtes légitimes
- [ ] Test de `https://vykso.com` : page se charge avec CSS
- [ ] Test de `https://api.vykso.com/health` : retourne OK
- [ ] Test de connexion Google OAuth : fonctionne
- [ ] Test de génération de vidéo : fonctionne

---

## 🆘 Support

Si après avoir suivi ce guide vous avez toujours des problèmes :

1. **Vérifiez les logs Railway :** Dashboard > Service > Logs
2. **Vérifiez les logs Cloudflare :** Analytics > Logs
3. **Utilisez les DevTools du navigateur :** F12 > Console et Network
4. **Testez en local :** `npm run dev` pour vérifier que le code fonctionne

---

**Dernière mise à jour :** 2024-11-04
