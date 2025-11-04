# 🔧 Corrections pour le Déploiement - Frontend

## ✅ Problèmes corrigés

### 1. Script start corrigé
- **Avant** : `next start` (ne fonctionne pas avec `output: standalone`)
- **Après** : `node .next/standalone/server.js`
- **Fichiers modifiés** : `package.json`, `railway.json`

### 2. Configuration CSS/fichiers statiques corrigée
- Les headers `Content-Type` sont maintenant correctement appliqués uniquement aux fichiers HTML
- Les fichiers CSS/JS/images ne sont plus affectés par le header UTF-8

### 3. Configuration Cloudflare clarifiée
- ⚠️ **IMPORTANT** : Supprimez toute règle Cloudflare pour `Content-Type` si vous en avez créé une

---

## 🚀 Actions à faire maintenant

### 1. Sur Cloudflare (URGENT)

**Supprimez la règle de doublon :**

1. Allez sur [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Sélectionnez votre domaine `vykso.com`
3. Allez dans **Rules** → **Transform Rules** → **Modify Response Header**
4. Cherchez une règle nommée `UTF-8 Content-Type` ou similaire
5. **Supprimez cette règle** (cliquez sur Delete/Remove)

❌ **Pourquoi ?** Next.js gère déjà les headers dans `next.config.js`. Une règle Cloudflare crée un conflit.

### 2. Vider le cache Cloudflare

1. Dans Cloudflare Dashboard → **Caching** → **Configuration**
2. Cliquez sur **Purge Everything**
3. Attendez quelques minutes

### 3. Redéployer sur Railway

1. Allez sur [Railway Dashboard](https://railway.app)
2. Sélectionnez votre service frontend
3. Allez dans **Settings** → **Deployments**
4. Cliquez sur **Redeploy** (ou faites un nouveau commit)

Le nouveau déploiement utilisera automatiquement :
- ✅ `node .next/standalone/server.js` au lieu de `next start`
- ✅ La configuration corrigée pour les fichiers statiques

### 4. Vérifier les logs Railway

Après le redéploiement, vérifiez les logs :
- Vous ne devriez **plus** voir le warning : `"next start" does not work with "output: standalone"`
- Vous devriez voir : `Ready in XXXms` sans warning

### 5. Tester votre site

1. Ouvrez `https://vykso.com`
2. Vérifiez que le CSS s'affiche correctement
3. Ouvrez les DevTools (F12) → **Network**
4. Vérifiez que les fichiers CSS se chargent avec le bon `Content-Type` (devrait être `text/css`)

---

## 🐛 Si le CSS ne s'affiche toujours pas

### Vérifications à faire :

1. **Vérifiez les fichiers CSS dans les DevTools** :
   - Ouvrez DevTools (F12) → **Network**
   - Rechargez la page
   - Cherchez les fichiers `.css`
   - Vérifiez le **Status Code** : devrait être `200`
   - Vérifiez le **Content-Type** : devrait être `text/css` (pas `text/html`)

2. **Vérifiez les logs Railway** :
   - Les logs doivent montrer que le serveur démarre correctement
   - Pas d'erreurs 404 pour les fichiers CSS

3. **Vérifiez que le build Next.js s'est bien passé** :
   - Dans Railway → **Deployments** → Sélectionnez le dernier déploiement
   - Vérifiez que le build s'est terminé sans erreur
   - Le dossier `.next/standalone` doit être créé

### Solution alternative si ça ne marche toujours pas :

Si après toutes ces étapes le CSS ne s'affiche toujours pas, essayez de désactiver temporairement le mode standalone :

1. Dans `frontend/next.config.js`, commentez la ligne :
   ```js
   // output: 'standalone',
   ```

2. Remettez dans `package.json` :
   ```json
   "start": "next start"
   ```

3. Redéployez

⚠️ **Note** : Le mode standalone est recommandé pour la production, mais cette solution alternative peut aider à diagnostiquer le problème.

---

## 📝 Checklist finale

- [ ] Règle Cloudflare `Content-Type` supprimée
- [ ] Cache Cloudflare vidé
- [ ] Frontend redéployé sur Railway
- [ ] Logs Railway sans warning
- [ ] CSS visible sur le site
- [ ] Fichiers CSS chargés avec le bon Content-Type dans DevTools

---

## 🆘 Besoin d'aide ?

Si après toutes ces étapes le problème persiste :
1. Vérifiez les logs Railway complets
2. Vérifiez la console du navigateur (F12) pour les erreurs
3. Vérifiez les fichiers CSS dans l'onglet Network des DevTools
