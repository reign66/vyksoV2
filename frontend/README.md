# Vykso Frontend

Frontend moderne et intuitif pour Vykso - G?n?ration de vid?os TikTok avec IA.

## ?? Technologies

- **Next.js 14** (App Router)
- **TypeScript**
- **Tailwind CSS**
- **Supabase Auth** (Google OAuth)
- **Zustand** (State management)
- **Axios** (API client)

## ?? Installation

```bash
cd frontend
npm install
```

## ?? Configuration

Copiez `.env.example` vers `.env.local` :

```bash
cp .env.example .env.local
```

Remplissez les variables :

```env
NEXT_PUBLIC_SUPABASE_URL=https://votre-projet.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=votre_anon_key
NEXT_PUBLIC_BACKEND_URL=https://api.vykso.com
```

## ?? D?veloppement

```bash
npm run dev
```

Ouvrez [http://localhost:3000](http://localhost:3000)

## ??? Build

```bash
npm run build
npm start
```

## ?? Structure

```
frontend/
??? app/              # Pages Next.js (App Router)
?   ??? page.tsx      # Page d'accueil
?   ??? login/        # Page de connexion
?   ??? dashboard/    # Tableau de bord
?   ??? ...
??? components/       # Composants React
?   ??? ui/          # Composants UI de base
?   ??? ...
??? lib/             # Utilitaires
?   ??? api.ts       # Client API
?   ??? supabase/    # Client Supabase
??? store/           # State management (Zustand)
```

## ?? Personnalisation

### Logo

Remplacez le composant `Logo` dans `/components/Logo.tsx` ou ajoutez votre logo dans `/public/logo.png`.

### Couleurs

Modifiez `tailwind.config.ts` pour changer la palette de couleurs.

## ?? Fonctionnalit?s

- ? Authentification Google OAuth
- ? G?n?ration de vid?os avec IA
- ? Galerie de vid?os
- ? Gestion des cr?dits
- ? Achat de cr?dits (Stripe)
- ? Interface moderne et intuitive

## ?? S?curit?

- Les cl?s API sont c?t? serveur uniquement
- Supabase Auth g?re l'authentification
- RLS activ? sur toutes les tables
