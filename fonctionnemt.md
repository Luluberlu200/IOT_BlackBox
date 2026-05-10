# Fonctionnement Technique — GuardDrive

## Stack Technologique

### Frontend
| Technologie | Rôle |
|-------------|------|
| **React 19** | Framework UI (composants, état) |
| **TypeScript** | Typage statique |
| **Vite** | Serveur de dev + build (port 8000) |
| **React Router 7** | Navigation côté client (SPA) |
| **Leaflet / react-leaflet** | Carte interactive |
| **CSS (BEM)** | Styles, thème clair/sombre |

### Backend
| Technologie | Rôle |
|-------------|------|
| **Node.js + Express 5** | Serveur HTTP (port 3000) |
| **MongoDB Atlas** | Base de données cloud |
| **Mongoose** | ODM (modèles de données) |
| **JWT (jsonwebtoken)** | Authentification sans session |
| **dotenv** | Variables d'environnement |

### Tests
| Technologie | Rôle |
|-------------|------|
| **Vitest + jsdom** | Tests unitaires |
| **Playwright** | Tests E2E (vrai navigateur Chrome) |

---

## Architecture Générale

```
Navigateur (React — port 8000)
        │
        │  /api/* → proxy Vite
        ▼
Serveur Express (Node.js — port 3000)
        │
        │  Mongoose
        ▼
MongoDB Atlas (cloud)
```

Le frontend ne connaît pas directement le port 3000. Vite intercepte tous les appels `/api/...` et les redirige vers le backend. En production, c'est le reverse proxy du serveur qui joue ce rôle.

---

## Authentification — Fonctionnement complet

### Schéma du flux de connexion

```
Utilisateur
    │  saisit email + mot de passe
    ▼
Login.tsx (validation front)
    │  email valide ? champs remplis ?
    ▼
AuthContext.login(email, password)
    │  POST /api/auth/login
    ▼
Express route auth.js
    │  User.findOne({ email, password })
    │  ← MongoDB
    │  génère JWT (expire dans 7 jours)
    ▼
Réponse : { token, user: { id, name, email } }
    │
    ▼
AuthContext
    │  localStorage.setItem('token', ...)
    │  localStorage.setItem('user', ...)
    │  setUser(data.user)
    ▼
Redirection vers /dashboard
```

---

### 1. Le formulaire — `Login.tsx`

L'utilisateur remplit un formulaire avec deux champs : `#email` et `#password`.

**Validations côté front (avant l'appel API) :**
- Le format de l'email est vérifié avec un regex
- Les deux champs doivent être non vides → le bouton submit est `disabled` sinon
- Si le format email est invalide → message d'erreur dans `.auth-form__error`

Un bouton `.auth-form__toggle` permet d'afficher/masquer le mot de passe en changeant l'attribut `type` du champ entre `"password"` et `"text"`.

---

### 2. Le contexte d'authentification — `AuthContext.tsx`

C'est le cerveau de l'authentification. Il expose :

- `user` — l'utilisateur connecté (ou `null`)
- `login(email, password)` — appelle l'API et stocke le token
- `logout()` — vide le localStorage et remet `user` à null
- `register(name, email, password)` — inscription + connexion automatique
- `updateUser(data)` — mise à jour du profil

**Au démarrage de l'app**, le contexte lit `localStorage` pour restaurer la session si un token existe déjà (persistance entre les rechargements de page).

---

### 3. Le service API — `src/services/api.ts`

Toutes les requêtes HTTP passent par ce service. Il ajoute automatiquement le token JWT dans chaque requête :

```
Authorization: Bearer <token_jwt>
```

Le token est lu depuis `localStorage` à chaque appel. Si pas de token → pas d'en-tête Authorization → le backend rejette avec 401.

---

### 4. Le backend — `POST /api/auth/login`

```
1. Reçoit { email, password }
2. Cherche dans MongoDB : User.findOne({ email, password })
3. Si pas trouvé → 401 "Identifiants invalides"
4. Si trouvé → génère un JWT :
      jwt.sign({ id: user._id }, JWT_SECRET, { expiresIn: '7d' })
5. Retourne { token, user: { id, name, email } }
```

Le JWT contient l'`id` de l'utilisateur (payload). Il est signé avec `JWT_SECRET` (variable d'environnement). Sans la clé secrète, personne ne peut en fabriquer un faux.

---

### 5. Le middleware de protection — `backend/middleware/auth.js`

Toutes les routes protégées passent par ce middleware avant d'être traitées :

```
Requête entrante
    │
    ▼
Extraire l'en-tête Authorization: Bearer <token>
    │
    ▼
jwt.verify(token, JWT_SECRET)
    │  ✅ Token valide → req.userId = decoded.id → next()
    │  ❌ Token invalide/expiré → 401 "Token invalide"
```

Ainsi, un utilisateur non connecté (sans token) ne peut jamais accéder aux données.

---

### 6. Les routes protégées côté React — `App.tsx`

React Router est configuré de façon à ce que les pages du tableau de bord ne soient accessibles qu'aux utilisateurs connectés :

```
/login, /register   → AuthLayout (pas de vérification)
/dashboard          → MainLayout (vérifie que user != null)
/alertes            →     "
/localisation       →     "
/etat-vehicule      →     "
/settings           →     "
/                   → redirige vers /login
/* (inconnu)        → redirige vers /login
```

Si `user` est null (non connecté) et qu'on tente d'accéder à `/dashboard`, le composant redirige vers `/login`.

---

## Base de données — Modèles MongoDB

### User
```
name     : String  (obligatoire)
email    : String  (obligatoire, unique)
password : String  (obligatoire)
```

### Vehicle
```
userId           : ref User
name             : String
plateNumber      : String
mileage          : Number
fuel             : Number (0–100)
battery          : Number (0–100)
lock             : "locked" | "unlocked"
temperature      : Number
tirePressure     : Number
tireWear         : { fl, fr, rl, rr }    ← usure par roue
tirePressureWheels: { fl, fr, rl, rr }  ← pression par roue
lastService      : String (date)
nextService      : String (date)
controleTechnique: String (date)
trips            : [{ date, distance, duration, from, to }]
lat, lng         : Number  ← position GPS
```

### Alert
```
userId    : ref User
type      : "intrusion" | "warning" | "info"
message   : String
status    : "active" | "archived"
date      : Date
vehicleId : ref Vehicle
ruleKey   : String  ← identifiant de la règle auto
```

---

## Alertes automatiques

À chaque appel `GET /api/vehicle`, le backend applique des **règles automatiques** sur l'état du véhicule et crée ou supprime des alertes en conséquence :

| Règle | Condition | Type |
|-------|-----------|------|
| `fuel_low` | Carburant < 20% | warning |
| `battery_low` | Batterie < 15% | warning |
| `unlocked` | Véhicule déverrouillé | intrusion |
| `service_soon` | Prochain entretien ≤ 15 jours | info |

Si la condition disparaît (ex : on recharge la batterie), l'alerte est supprimée automatiquement.

---

## Navigation dans l'app

L'application est une **SPA** (Single Page Application) : il n'y a pas de rechargement de page entre les sections. React Router change uniquement la partie affichée.

La barre de navigation en bas (mobile-first) contient 5 onglets :

```
🏠 Dashboard  →  /dashboard
📍 Localisation  →  /localisation
🚗 État  →  /etat-vehicule
🔔 Alertes  →  /alertes
⚙️ Réglages  →  /settings
```

---

## Fonctionnalités principales

### Dashboard
- Sélecteur de véhicule (dropdown)
- Jauges carburant et batterie (code couleur vert/orange/rouge)
- Bouton verrouillage/déverrouillage → `PATCH /api/vehicle/:id/lock`
- Contrôle de la température de climatisation
- Aperçu des dernières alertes

### Localisation
- Carte Leaflet avec tuiles OpenStreetMap (Carto Voyager)
- Marqueur vert animé = position du véhicule (lat/lng stockés en base)
- Marqueur bleu = position de l'utilisateur (API `navigator.geolocation`)
- Géocodage inverse : coordonnées → adresse via l'API Nominatim (OpenStreetMap)
- Boutons "Klaxonner" et "Appel de phares" (effets visuels simulés)

### État du véhicule
- Usure des 4 pneus en pourcentage (FL, FR, RL, RR)
- Pression par roue avec plage cible
- Kilométrage total
- Dates d'entretien et de contrôle technique

### Alertes
- Liste filtrée par statut (actives / archivées)
- Actions : archiver, désarchiver, supprimer
- Badge de type (intrusion / avertissement / info)

### Réglages
- Modification du profil (nom, email)
- Gestion des véhicules (ajout, suppression)
- Bascule thème clair/sombre (persisté en localStorage)
- Déconnexion

---

## Proxy Vite — Pourquoi deux ports ?

En développement, le frontend tourne sur le port 8000 et le backend sur le port 3000. Normalement, les navigateurs bloquent les requêtes entre deux origines différentes (CORS). Vite résout ça avec un proxy :

```typescript
// vite.config.ts
proxy: {
  '/api': 'http://localhost:3000'
}
```

Quand le front appelle `/api/auth/login`, Vite le redirige vers `http://localhost:3000/api/auth/login`. Le navigateur ne voit qu'une seule origine (port 8000), donc pas de problème CORS.

---

## Cycle de vie d'une session utilisateur

```
1. Ouverture de l'app
      └─ AuthContext lit localStorage
            ├─ Token trouvé → user restauré → /dashboard
            └─ Pas de token → /login

2. Connexion
      └─ Login → POST /api/auth/login → JWT stocké → /dashboard

3. Navigation dans l'app
      └─ Chaque requête API envoie Authorization: Bearer <token>
      └─ Backend vérifie le token à chaque route protégée

4. Déconnexion
      └─ localStorage vidé → user = null → /login

5. Token expiré (7 jours)
      └─ Backend retourne 401 → front doit reconnecter
```
