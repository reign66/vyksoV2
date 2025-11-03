# ?? Fix pour l'erreur "Create PR" dans Cursor

## Erreur rencontr?e

```
Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'toUrl')
```

Cette erreur se produit lors du clic sur "Create PR" dans Cursor.

## ?? Cause probable

C'est un bug connu de Cursor qui peut se produire quand :
1. Il y a trop de changements dans le commit
2. La connexion GitHub n'est pas correctement configur?e
3. Il y a un probl?me de cache dans Cursor

## ? Solutions

### Solution 1 : Vider le cache de Cursor (recommand?)

1. Fermez compl?tement Cursor
2. Supprimez le cache :
   - **Mac** : `~/Library/Application Support/Cursor/Cache`
   - **Windows** : `%APPDATA%\Cursor\Cache`
   - **Linux** : `~/.config/Cursor/Cache`
3. Rouvrez Cursor

### Solution 2 : Cr?er la PR manuellement via Git

Si l'erreur persiste, cr?ez la PR manuellement :

```bash
# V?rifiez votre branche actuelle
git branch

# Poussez votre branche
git push origin cursor/rebuild-front-end-and-integrate-domain-8e0b

# Ensuite allez sur GitHub et cr?ez la PR depuis l'interface web
```

### Solution 3 : R?duire la taille du commit

Si vous avez beaucoup de fichiers, essayez de :
1. Commiter en plusieurs fois
2. V?rifier que tous les fichiers sont bien track?s avec `git status`

### Solution 4 : Reconnecter GitHub dans Cursor

1. Ouvrez les param?tres de Cursor (Cmd/Ctrl + ,)
2. Allez dans "Accounts" ou "GitHub"
3. D?connectez et reconnectez votre compte GitHub

### Solution 5 : Utiliser GitHub CLI

Si Cursor continue ? buguer, utilisez GitHub CLI :

```bash
# Installer GitHub CLI si pas d?j? fait
# brew install gh  # Mac
# choco install gh  # Windows

# Login
gh auth login

# Cr?er la PR
gh pr create --title "Rebuild frontend and integrate domain" --body "New Next.js frontend to replace Lovable"
```

## ?? Erreurs li?es corrig?es

J'ai aussi corrig? les erreurs dans votre frontend :

1. ? **Appels API** : Maintenant utilise directement le client API au lieu des rewrites
2. ? **Cookies Supabase** : Configuration corrig?e pour ?viter les warnings
3. ? **Synchronisation utilisateur** : Utilise maintenant l'API directement

## ?? Note

Les erreurs 404 que vous voyez dans les logs sont normales si le backend n'est pas encore d?ploy? ou si `NEXT_PUBLIC_BACKEND_URL` n'est pas configur?. Une fois le backend d?ploy?, configurez cette variable et les erreurs dispara?tront.
