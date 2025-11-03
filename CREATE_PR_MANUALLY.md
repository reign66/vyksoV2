# ?? Comment cr?er la PR manuellement

## Le probl?me

Cursor a un bug avec la cr?ation de PR, et GitHub bloque le push ? cause de secrets d?tect?s dans l'historique.

## ? Solution rapide (recommand?e)

### Option 1 : Autoriser via GitHub (rapide)

1. **Cliquez sur ces liens pour autoriser temporairement** :
   - Client ID : https://github.com/reign66/vyksoV2/security/secret-scanning/unblock-secret/34yrFGuTJ0t0tkZDai9WB2bjAsd
   - Client Secret : https://github.com/reign66/vyksoV2/security/secret-scanning/unblock-secret/34yrFJQ9IxX9J9kql3YKpNrIJJ0

2. **Ensuite poussez** :
   ```bash
   git push origin cursor/rebuild-front-end-and-integrate-domain-8e0b
   ```

3. **Cr?ez la PR sur GitHub** :
   - Allez sur https://github.com/reign66/vyksoV2
   - Cliquez sur "Pull requests"
   - Cliquez sur "New pull request"
   - S?lectionnez `cursor/rebuild-front-end-and-integrate-domain-8e0b` comme source
   - S?lectionnez `main` comme destination
   - Ajoutez un titre : "Rebuild frontend and integrate domain"
   - Ajoutez une description
   - Cr?ez la PR

### Option 2 : Utiliser GitHub CLI

```bash
# Installer GitHub CLI si pas d?j? fait
# Mac: brew install gh
# Windows: choco install gh

# Login
gh auth login

# Cr?er la PR
gh pr create \
  --title "Rebuild frontend and integrate domain" \
  --body "New Next.js frontend to replace Lovable. Includes Google OAuth, video generation UI, and complete deployment documentation." \
  --base main \
  --head cursor/rebuild-front-end-and-integrate-domain-8e0b
```

## ?? IMPORTANT : S?curit?

**Apr?s avoir cr?? la PR, vous DEVEZ :**

1. **R?voquer les secrets expos?s** :
   - Allez sur [Google Cloud Console](https://console.cloud.google.com/)
   - R?voquez le Client ID expos?
   - Cr?ez de nouveaux credentials OAuth

2. **Mettre ? jour Supabase** :
   - Remplacez les anciens credentials par les nouveaux

3. **V?rifier** :
   - Les secrets ont ?t? retir?s des fichiers actuels
   - Mais ils sont toujours dans l'historique Git (commit 8977f0e)
   - C'est pourquoi GitHub les bloque

## ?? Contenu de la PR

Cette PR inclut :
- ? Frontend Next.js complet
- ? Authentification Google OAuth
- ? Interface de g?n?ration de vid?os
- ? Galerie de vid?os
- ? Gestion des cr?dits
- ? Documentation de d?ploiement
- ? Configuration du domaine vykso.com

## ?? Prochaines ?tapes apr?s merge

1. D?ployer le backend sur Railway
2. D?ployer le frontend sur Railway/Vercel
3. Configurer le domaine sur Cloudflare
4. Configurer Supabase (tables, OAuth, buckets)
5. Tester l'application compl?te
