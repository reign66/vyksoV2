# Instructions de mise à jour Frontend - Lovable

## Contexte

Le backend Vykso a été mis à jour avec un nouveau système de tiers utilisateurs et des améliorations significatives. Ce document détaille toutes les modifications que le frontend doit intégrer.

---

## 1. Nouveau système de deux tiers utilisateurs

### Vue d'ensemble

L'application supporte maintenant deux types d'abonnements distincts avec des fonctionnalités différentes :

#### Tier CREATOR (pour créateurs TikTok/YouTube Shorts)
- Optimisé pour le contenu viral court
- Durée de vidéo **fixe** (pas de choix)
- Prompts automatiquement optimisés pour le style TikTok/Shorts
- Interface simplifiée

#### Tier PROFESSIONAL (pour publicités professionnelles)
- Optimisé pour les publicités et contenus commerciaux
- Durée de vidéo **variable** (6 à 60 secondes)
- Prompts automatiquement optimisés pour les pubs premium
- Fonctionnalités avancées (séquences multiples)

---

## 2. Nouvelle page de tarification (Pricing)

### Plans CREATOR à ajouter

Créer une nouvelle section ou onglet "Créateur" sur la page de pricing avec trois plans :

| Plan | Prix | Crédits | Équivalent |
|------|------|---------|------------|
| Creator Basic | 34,99€/mois | 100 crédits | 10 vidéos de 10 secondes |
| Creator Pro | 65,99€/mois | 200 crédits | 20 vidéos de 10 secondes |
| Creator Max | 89,99€/mois | 300 crédits | 30 vidéos de 10 secondes |

### Différenciation visuelle

- Ajouter un système d'onglets ou de toggle pour basculer entre "Créateur" et "Professionnel"
- Les plans Creator doivent avoir une esthétique plus jeune, dynamique, colorée (style TikTok)
- Les plans Professional gardent l'esthétique actuelle plus corporate/premium
- Afficher clairement les différences de fonctionnalités entre les deux tiers

### Points clés à communiquer pour Creator

- "Parfait pour TikTok et YouTube Shorts"
- "Durée optimisée automatiquement"
- "Prompts boostés pour la viralité"
- "Interface simplifiée"

### Points clés à communiquer pour Professional

- "Idéal pour les publicités et contenus commerciaux"
- "Contrôle total sur la durée"
- "Prompts optimisés pour la conversion"
- "Séquences narratives avancées"

---

## 3. Interface de création de vidéo

### Nouvel endpoint à appeler

Avant d'afficher l'interface de création, appeler l'endpoint :
```
GET /api/users/{user_id}/tier
```

Cet endpoint retourne les informations du tier de l'utilisateur, notamment si la sélection de durée est autorisée.

### Adaptation selon le tier

#### Pour les utilisateurs CREATOR

- **Masquer complètement** le sélecteur de durée de vidéo
- La durée est fixée automatiquement :
  - 8 secondes pour les modèles VEO (veo-3.1, veo-3.1-fast)
  - 10 secondes pour les modèles Sora (sora-2, sora-2-pro)
- Afficher un message informatif : "Durée optimisée automatiquement pour les Shorts"
- L'interface doit être plus simple et directe

#### Pour les utilisateurs PROFESSIONAL

- **Afficher** le sélecteur de durée (6 à 60 secondes)
- Garder toutes les options avancées disponibles
- Permettre la création de séquences multiples

### Sélecteur d'images de référence

- **Augmenter la limite** de 3 images à **18 images maximum**
- Mettre à jour l'interface d'upload pour accepter jusqu'à 18 images
- Afficher un compteur : "X/18 images ajoutées"
- Les images peuvent être utilisées comme références de style ou de contenu

---

## 4. Dashboard utilisateur

### Affichage du tier

Dans le profil ou dashboard de l'utilisateur, afficher clairement :

- Le plan actuel (ex: "Creator Pro", "Professional Max")
- Le tier (Créateur ou Professionnel)
- Les crédits restants
- Les fonctionnalités disponibles selon le tier

### Badge ou indicateur visuel

Ajouter un badge visuel pour différencier les tiers :
- Badge "Créateur" avec une icône TikTok/vidéo courte
- Badge "Pro" avec une icône business/corporate

---

## 5. Formulaire de checkout Stripe

### Nouveaux plans à supporter

Le formulaire de checkout doit supporter les nouveaux identifiants de plans :

Plans Creator :
- `creator_basic`
- `creator_pro`
- `creator_max`

Plans Professional (existants) :
- `starter`
- `pro`
- `max`

### Paramètre à envoyer

Lors de l'appel à `/api/stripe/create-checkout`, envoyer le bon identifiant de plan selon la sélection de l'utilisateur.

---

## 6. Messages et textes à adapter

### Messages pour Creator

- Titre de génération : "Créez votre Short viral"
- Description : "Votre vidéo sera automatiquement optimisée pour TikTok et YouTube Shorts"
- Pendant la génération : "Création de votre contenu viral en cours..."

### Messages pour Professional

- Titre de génération : "Créez votre publicité professionnelle"
- Description : "Votre vidéo sera optimisée pour la conversion et le branding"
- Pendant la génération : "Production de votre contenu premium en cours..."

---

## 7. Métadonnées des vidéos générées

### Nouvelles informations disponibles

Les jobs de vidéo contiennent maintenant dans leurs métadonnées :
- `user_tier` : "creator" ou "professional"
- `num_images` : nombre d'images de référence utilisées

Ces informations peuvent être affichées dans l'historique des vidéos.

---

## 8. Validation côté client

### Validation des images

- Vérifier que le nombre d'images ne dépasse pas 18
- Afficher un message d'erreur clair si la limite est dépassée

### Validation de la durée (Professional uniquement)

- Minimum : 6 secondes
- Maximum : 60 secondes
- Pour Creator : aucune validation nécessaire (durée gérée par le backend)

---

## 9. États d'interface selon le plan

### Plan Free

- Accès limité (10 crédits de test)
- Afficher une bannière incitant à upgrader
- Montrer les deux options (Creator et Professional) pour l'upgrade

### Plan Creator

- Interface simplifiée
- Pas de sélection de durée
- Messages orientés "viral/TikTok"

### Plan Professional

- Interface complète
- Toutes les options disponibles
- Messages orientés "business/conversion"

---

## 10. Page "Mon compte" ou "Paramètres"

### Affichage des informations du tier

Créer une section qui affiche :

- **Plan actuel** : Nom du plan (ex: "Creator Pro")
- **Type de tier** : Créateur ou Professionnel
- **Crédits restants** : Nombre de crédits disponibles
- **Fonctionnalités** :
  - Pour Creator : "Durée fixe optimisée", "Prompts viraux", "Jusqu'à 18 images"
  - Pour Professional : "Durée personnalisable (6-60s)", "Prompts publicitaires", "Séquences multiples", "Jusqu'à 18 images"

### Option de changement de tier

Permettre aux utilisateurs de changer de tier (Creator ↔ Professional) via un bouton qui les redirige vers la page de pricing.

---

## 11. Responsive et mobile

### Considérations pour Creator

Les utilisateurs Creator sont probablement plus mobiles (créateurs TikTok). L'interface Creator doit être particulièrement optimisée pour mobile :
- Gros boutons tactiles
- Interface épurée
- Upload d'images depuis la galerie du téléphone simplifié

---

## 12. Onboarding

### Choix initial du tier

Lors de l'inscription ou première visite :
- Demander à l'utilisateur quel type de contenu il souhaite créer
- Option 1 : "Je crée pour TikTok/YouTube Shorts" → Orienter vers Creator
- Option 2 : "Je crée des publicités/contenus professionnels" → Orienter vers Professional

Cela permet de personnaliser l'expérience dès le départ.

---

## 13. Rappels importants

### Ce qui change pour le frontend

1. **Nouveau endpoint** `/api/users/{user_id}/tier` à appeler pour connaître le tier
2. **Sélecteur de durée** : conditionnel selon le tier
3. **Limite d'images** : passe de 3 à 18
4. **Nouveaux plans** Creator à ajouter au pricing
5. **Messages/textes** différenciés selon le tier

### Ce qui ne change PAS

- Les endpoints de génération de vidéo restent les mêmes
- Le format des réponses reste identique
- L'authentification reste inchangée
- Le système de crédits fonctionne de la même façon

---

## 14. Checklist de mise à jour

- [ ] Ajouter l'appel à `/api/users/{user_id}/tier` au chargement de l'app
- [ ] Créer le toggle/onglets Creator vs Professional sur la page pricing
- [ ] Ajouter les trois plans Creator avec leurs prix
- [ ] Conditionner l'affichage du sélecteur de durée selon le tier
- [ ] Augmenter la limite d'images de 3 à 18 dans l'interface d'upload
- [ ] Adapter les messages et textes selon le tier
- [ ] Afficher le tier dans le dashboard/profil utilisateur
- [ ] Mettre à jour le formulaire de checkout avec les nouveaux plans
- [ ] Tester le parcours complet pour les deux tiers
- [ ] Vérifier l'affichage mobile pour Creator

---

## Questions fréquentes

**Q: Comment savoir si un utilisateur est Creator ou Professional ?**
R: Appeler l'endpoint `/api/users/{user_id}/tier` qui retourne `tier: "creator"` ou `tier: "professional"`

**Q: Que se passe-t-il si un Creator essaie d'envoyer une durée personnalisée ?**
R: Le backend ignore la durée envoyée et applique automatiquement la durée fixe (8s ou 10s selon le modèle)

**Q: Les utilisateurs Free sont dans quel tier ?**
R: Les utilisateurs Free sont considérés comme "professional" par défaut et ont accès à toutes les fonctionnalités (avec leurs 10 crédits de test)

**Q: Un utilisateur peut-il passer de Creator à Professional ?**
R: Oui, il suffit de souscrire à un plan de l'autre tier. Le changement est immédiat.
