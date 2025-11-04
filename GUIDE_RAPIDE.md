# 🚀 Guide Rapide - Déploiement Frontend Vykso

Guide condensé pour déployer rapidement votre frontend sur votre domaine.

---

## ✅ Checklist Rapide

### 1. Railway (Frontend)
- [ ] Service Railway créé pour le frontend
- [ ] Variables d'environnement configurées :
  ```
  NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
  NEXT_PUBLIC_SUPABASE_ANON_KEY=xxx
  NEXT_PUBLIC_BACKEND_URL=https://votre-backend.railway.app
  ```
- [ ] URL Railway générée et fonctionnelle (ex: `vykso-frontend.up.railway.app`)

### 2. Supabase
- [ ] URL de redirection ajoutée : `https://votre-domaine.com/auth/callback`
- [ ] Site URL configuré : `https://votre-domaine.com`

### 3. Cloudflare
- [ ] CNAME créé : `@` → `votre-frontend.railway.app` (☁️ Proxied)
- [ ] SSL/TLS : Mode **Full**
- [ ] Règle Transform : `Content-Type: text/html; charset=utf-8` pour `votre-domaine.com/*`

### 4. Tests
- [ ] Frontend Railway fonctionne
- [ ] Votre domaine affiche le frontend
- [ ] Caractères spéciaux OK (é, è, ê, ç)
- [ ] Authentification fonctionne

---

## 🔧 Commandes Rapides

### Vérifier les logs Railway
```
Railway Dashboard → Votre service → Deployments → View Logs
```

### Purger le cache Cloudflare
```
Cloudflare Dashboard → Caching → Configuration → Purge Everything
```

### Vérifier la propagation DNS
```bash
# Sur Mac/Linux
dig votre-domaine.com

# Sur Windows (PowerShell)
nslookup votre-domaine.com
```

---

## 🐛 Problèmes Fréquents

| Problème | Solution |
|----------|----------|
| Page Not Found | Vérifier CNAME Cloudflare + Proxy activé |
| Caractères "?" | Ajouter règle Transform Cloudflare + Purger cache |
| Redirection Lovable | Vérifier variables Railway + URL utilisée |
| Auth ne fonctionne pas | Vérifier URLs Supabase + Variables d'env |

---

## 📞 URLs à Garder

- Frontend Railway : `https://votre-frontend.up.railway.app`
- Votre domaine : `https://votre-domaine.com`
- Supabase : `https://app.supabase.com`
- Cloudflare : `https://dash.cloudflare.com`

---

**Pour plus de détails, voir `GUIDE_DEPLOIEMENT.md`**
