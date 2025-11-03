# ?? Guide de Setup Frontend - Vykso

## ?? Installation rapide

```bash
cd frontend
npm install
```

## ?? Configuration

1. Cr?ez `.env.local` :
```bash
cp .env.example .env.local
```

2. Remplissez les variables :
```env
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=votre_anon_key
NEXT_PUBLIC_BACKEND_URL=http://localhost:8080  # En dev
# NEXT_PUBLIC_BACKEND_URL=https://api.vykso.com  # En production
```

## ?? D?veloppement local

```bash
npm run dev
```

Ouvrez [http://localhost:3000](http://localhost:3000)

## ?? Structure du projet

```
frontend/
??? app/                    # Pages Next.js (App Router)
?   ??? page.tsx           # Page d'accueil
?   ??? login/             # Connexion Google OAuth
?   ??? dashboard/         # Tableau de bord principal
?   ??? auth/
?   ?   ??? callback/      # Callback OAuth
?   ??? payment-success/   # Page apr?s paiement Stripe
?
??? components/            # Composants React
?   ??? ui/               # Composants UI de base (Button, etc.)
?   ??? AuthProvider.tsx  # Provider d'authentification
?   ??? Logo.tsx          # Composant logo
?   ??? VideoGenerator.tsx # Formulaire de g?n?ration
?   ??? VideoGallery.tsx  # Galerie de vid?os
?
??? lib/                   # Utilitaires
?   ??? api.ts            # Client API (axios)
?   ??? supabase/         # Clients Supabase
?   ??? utils.ts          # Helpers (cn, etc.)
?
??? store/                # State management (Zustand)
    ??? auth.ts           # Store d'authentification
```

## ?? Personnalisation

### Logo
Ajoutez votre logo dans `/public/logo.png` et modifiez `components/Logo.tsx`.

### Couleurs
Modifiez `tailwind.config.ts` pour changer les couleurs primaires.

### Contenu
- Page d'accueil : `app/page.tsx`
- Dashboard : `app/dashboard/page.tsx`
- G?n?ration : `components/VideoGenerator.tsx`

## ?? Fonctionnalit?s

? Authentification Google OAuth via Supabase  
? G?n?ration de vid?os avec IA (Sora 2, Veo 3)  
? Galerie de vid?os avec statut en temps r?el  
? Gestion des cr?dits  
? Achat de cr?dits via Stripe  
? Interface moderne et responsive  

## ?? D?ploiement

### Railway
1. Cr?ez un nouveau service
2. Connectez le dossier `frontend/`
3. Ajoutez les variables d'environnement
4. Railway d?tectera Next.js automatiquement

### Vercel (alternative)
```bash
npm install -g vercel
vercel
```

## ?? Notes

- Le frontend utilise le backend via l'URL configur?e dans `NEXT_PUBLIC_BACKEND_URL`
- Les routes `/api/backend/*` sont automatiquement proxy?es vers votre backend
- L'authentification est g?r?e par Supabase Auth
- Les noms/pr?noms sont r?cup?r?s automatiquement depuis Google OAuth

## ?? Troubleshooting

**Erreur CORS** : V?rifiez que `FRONTEND_URL` est configur? dans le backend  
**OAuth ne fonctionne pas** : V?rifiez l'URL de callback dans Supabase  
**Les vid?os ne se chargent pas** : V?rifiez que `NEXT_PUBLIC_BACKEND_URL` est correct
