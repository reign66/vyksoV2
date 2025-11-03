# ?? Solution pour les secrets d?tect?s par GitHub

GitHub bloque le push car il a d?tect? des secrets OAuth dans les commits pr?c?dents.

## Solution 1 : Autoriser temporairement (non recommand? mais rapide)

Si vous devez absolument pousser maintenant, vous pouvez autoriser temporairement via les liens fournis par GitHub :
- https://github.com/reign66/vyksoV2/security/secret-scanning/unblock-secret/34yrFGuTJ0t0tkZDai9WB2bjAsd
- https://github.com/reign66/vyksoV2/security/secret-scanning/unblock-secret/34yrFJQ9IxX9J9kql3YKpNrIJJ0

?? **Mais ensuite vous DEVEZ invalider et recr?er ces secrets car ils sont maintenant dans l'historique Git public !**

## Solution 2 : Nettoyer l'historique (recommand?)

Pour retirer compl?tement les secrets de l'historique Git :

```bash
# Option A : Utiliser git filter-repo (n?cessite installation)
pip install git-filter-repo
git filter-repo --invert-paths --path DEPLOYMENT.md --path REPONSES.md --path frontend/.env.example

# Ensuite force push (ATTENTION : cela r??crit l'historique)
git push origin cursor/rebuild-front-end-and-integrate-domain-8e0b --force
```

## Solution 3 : Cr?er une nouvelle branche propre (plus simple)

```bash
# Cr?er une nouvelle branche depuis main
git checkout main
git pull origin main
git checkout -b frontend-rebuild-clean

# Copier seulement les fichiers n?cessaires (sans les secrets)
# Ensuite commiter et pousser
git push origin frontend-rebuild-clean
```

## ?? Actions de s?curit? requises

**Quelle que soit la solution choisie, vous DEVEZ :**

1. **R?voquer les secrets expos?s** :
   - Allez sur Google Cloud Console
   - R?voquez le Client ID : `806484205365-aqqji9cc7dpbmq39ef1e84u9956aqdjj.apps.googleusercontent.com`
   - Cr?ez de nouveaux credentials OAuth

2. **Mettre ? jour Supabase** :
   - Remplacez les anciens credentials par les nouveaux dans Supabase Dashboard

3. **V?rifier** :
   - Assurez-vous qu'aucun secret n'est dans votre code
   - Utilisez `.env.local` pour les secrets locaux (d?j? dans `.gitignore`)

## ? Fichiers d?j? nettoy?s

Les secrets ont ?t? retir?s de :
- ? `DEPLOYMENT.md`
- ? `REPONSES.md`  
- ? `frontend/.env.example`

Mais ils restent dans l'historique Git des commits pr?c?dents, d'o? le blocage.
