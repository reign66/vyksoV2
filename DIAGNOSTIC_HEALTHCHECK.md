# 🔍 Diagnostic Healthcheck - Frontend

## ✅ Corrections appliquées

1. **Script de démarrage personnalisé** créé (`frontend/start-server.js`)
   - Force le serveur à écouter sur `0.0.0.0` (toutes les interfaces réseau)
   - Vérifie que le fichier serveur existe avant de démarrer
   - Gère correctement les signaux de terminaison
   - Fichiers créés/modifiés : `frontend/start-server.js`, `frontend/package.json`

2. **Timeout augmenté** de 500ms à 1000ms dans `railway.json`
   - Donne plus de temps au serveur pour démarrer

3. **Configuration Railway** simplifiée
   - Utilise maintenant `npm start` qui lance le script personnalisé

---

## 🔍 Vérifications à faire sur Railway

### 1. Vérifier les logs du déploiement

Dans Railway Dashboard → Votre service frontend → **Logs** :

1. **Vérifiez que le build s'est bien passé** :
   - Vous devriez voir `npm install` et `npm run build` réussir
   - Pas d'erreurs de compilation

2. **Vérifiez que le serveur démarre** :
   - Cherchez des lignes comme :
     - `Ready in XXXms`
     - `- Local: http://0.0.0.0:XXXX`
   - **⚠️ Important** : Le serveur doit écouter sur `0.0.0.0` (pas `127.0.0.1` ou `localhost`)

3. **Vérifiez les erreurs** :
   - Pas d'erreur "EADDRINUSE" (port déjà utilisé)
   - Pas d'erreur "Cannot find module"
   - Pas d'erreur liée à `.next/standalone/server.js`

### 2. Vérifier la configuration Railway

Dans Railway Dashboard → Votre service frontend → **Settings** → **Healthcheck** :

1. **Path** : Doit être `/api/health`
2. **Timeout** : Devrait être 1000ms (ou plus)
3. **Interval** : Peut être 30s ou plus

### 3. Tester le healthcheck manuellement

Dans Railway Dashboard → Votre service frontend → **Deployments** :

1. Cliquez sur le dernier déploiement
2. Copiez l'URL du service (ex: `https://votre-service.up.railway.app`)
3. Testez depuis votre terminal :

```bash
# Test simple
curl https://votre-service.up.railway.app/api/health

# Devrait retourner : ok
```

**Si ça ne fonctionne pas** :
- Vérifiez que le service est bien déployé
- Vérifiez les logs pour voir si le serveur a démarré

### 4. Vérifier les variables d'environnement

Dans Railway Dashboard → Votre service frontend → **Variables** :

1. **PORT** : Ne doit PAS être défini (Railway l'injecte automatiquement)
   - Si vous avez défini `PORT=3000`, supprimez-le
   - Railway fournit automatiquement le port via `$PORT`

2. **Autres variables** :
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_BACKEND_URL`

### 5. Vérifier le dossier .next/standalone

Le build Next.js doit créer le dossier `.next/standalone`. Vérifiez dans les logs :

```
Creating standalone build
Copying public assets
Copying static files
...
```

Si le dossier n'est pas créé :
- Le build Next.js a peut-être échoué
- Vérifiez les logs de build

---

## 🐛 Problèmes courants et solutions

### Problème 1 : "Service unavailable" persistant

**Causes possibles** :
- Le serveur ne démarre pas
- Le serveur écoute sur le mauvais port/interface
- Le healthcheck arrive avant que le serveur soit prêt

**Solutions** :
1. Augmentez encore le `healthcheckTimeout` dans `railway.json` (essayez 2000ms)
2. Vérifiez les logs pour voir si le serveur démarre
3. Ajoutez un délai de démarrage dans la commande :

```json
"startCommand": "sh -c 'sleep 2 && HOSTNAME=0.0.0.0 PORT=${PORT:-3000} node .next/standalone/server.js'"
```

### Problème 2 : Le serveur écoute sur localhost

**Symptôme** : Dans les logs, vous voyez `Local: http://localhost:3000` au lieu de `http://0.0.0.0:3000`

**Solution** : Vérifiez que `HOSTNAME=0.0.0.0` est bien dans la commande de démarrage

### Problème 3 : Port déjà utilisé

**Symptôme** : Erreur `EADDRINUSE` dans les logs

**Solution** : 
- Ne définissez PAS `PORT` dans les variables d'environnement Railway
- Laissez Railway injecter automatiquement le port via `$PORT`

### Problème 4 : Module .next/standalone/server.js introuvable

**Symptôme** : Erreur `Cannot find module '.next/standalone/server.js'`

**Solution** :
- Le build Next.js n'a pas créé le dossier standalone
- Vérifiez que `output: 'standalone'` est dans `next.config.js`
- Relancez le build

---

## 📝 Checklist de vérification

- [ ] Build Next.js réussi (pas d'erreurs dans les logs)
- [ ] Dossier `.next/standalone` créé
- [ ] Serveur démarre (logs montrent "Ready")
- [ ] Serveur écoute sur `0.0.0.0` (pas `localhost`)
- [ ] Variable `PORT` NON définie dans Railway (Railway l'injecte)
- [ ] Healthcheck path = `/api/health`
- [ ] Healthcheck timeout >= 1000ms
- [ ] Test manuel de `/api/health` fonctionne
- [ ] Pas d'erreurs dans les logs après le démarrage

---

## 🆘 Si rien ne fonctionne

1. **Redéployez** le service (Railway → Deployments → Redeploy)
2. **Attendez** 2-3 minutes après le déploiement
3. **Vérifiez les logs** en temps réel pendant le démarrage
4. **Testez manuellement** l'endpoint healthcheck

Si le problème persiste, partagez :
- Les logs complets du démarrage (dernières 50-100 lignes)
- La configuration Railway (Settings → Healthcheck)
- Le résultat du test manuel `curl`
