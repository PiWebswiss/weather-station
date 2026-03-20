# DEVLOG — Station Météo E-Ink

Historique des décisions de développement, bugs corrigés et raisonnements techniques.

---

## Session 1 — Architecture & Setup

### Pourquoi InkyPi ?
Choix d'InkyPi comme base (https://github.com/fatihak/InkyPi) plutôt qu'un script from scratch :
- Architecture Flask propre avec système de plugins
- Support natif Inky et Waveshare
- Système de playlists et refresh configurable
- UI web admin déjà fonctionnelle

### Pourquoi Raspberry Pi Zero 2 W ?
- Prix : ~20 CHF
- WiFi intégré
- Assez puissant pour Flask + Playwright (screenshot)
- Faible consommation (~500mA en pointe)

---

## Session 2 — APIs Météo

### Pourquoi 3 providers ?
1. **Open-Meteo** : gratuit, sans clé, global → provider par défaut
2. **MeteoSwiss** : données officielles suisses, précision maximale pour la Suisse
3. **OpenWeatherMap** : pour les utilisateurs hors Suisse qui veulent une clé

### MeteoSwiss STAC API — Comment ça marche
1. Télécharge la liste des points de prévision : `ogd-local-forecasting_meta_point.csv`
2. Calcule la distance Haversine à chaque point pour trouver le plus proche
3. Récupère les assets STAC (CSV par paramètre) via `items?limit=1`
4. Parse les CSV : `tre200h0` (temp), `rre150h0` (précip), `jww003i0` (symboles)
5. Enrichit avec les données SMN en temps réel (station météo la plus proche)
6. Cache 30 min pour éviter les requêtes répétées

---

## Session 3 — Bugs Corrigés

### Bug #1 : `get_icon_path({name})` — Set literal Python
**Symptôme** : Icônes météo ne s'affichaient pas, chemin de fichier invalide
**Cause** : `{variable}` en Python crée un *set*, pas une string. Résultat : `icons/{'01d'}.svg` au lieu de `icons/01d.svg`
**Fix** : `self.get_icon_path(current_icon)` (3 endroits : lignes 213, 238, 477)

### Bug #2 : OpenMeteo `models=best_match` deprecated
**Symptôme** : Requête Open-Meteo retournait une erreur API
**Cause** : Le paramètre `models=best_match` a été supprimé de l'API v1
**Fix** : Suppression du paramètre de l'URL

### Bug #3 : OpenMeteo `daily=weathercode` vs `daily=weather_code`
**Symptôme** : Toutes les icônes de prévision quotidienne = soleil (valeur par défaut)
**Cause** : L'API retourne `weather_code` mais l'URL demandait `weathercode` (sans underscore)
**Fix** : `daily=weather_code` dans l'URL + `daily_data.get('weather_code', ...)` dans le parser

### Bug #4 : OpenStreetMap tiles bloqués (Access blocked)
**Symptôme** : La carte de sélection de localisation affichait "Referer is required"
**Cause** : Les tiles OSM bloquent les requêtes sans header Referer (politique tile usage)
**Fix** : Remplacement par CartoDB tiles (`basemaps.cartocdn.com`) qui n'ont pas cette restriction

### Bug #5 : Géolocalisation GPS silencieusement bloquée
**Symptôme** : Bouton GPS ne faisait rien sur HTTP
**Cause** : `navigator.geolocation` nécessite HTTPS (sauf localhost)
**Fix** : Détection explicite du protocole + message d'erreur clair + Cloudflare tunnel pour HTTPS

---

## Session 4 — UI/UX Améliorations

### Recherche de ville par nom (Nominatim)
- Problème : L'utilisateur devait connaître ses coordonnées ou utiliser la carte
- Solution : Geocodage par nom de ville via Nominatim (OSM, gratuit, sans clé)
- API : `https://nominatim.openstreetmap.org/search?format=json&q=...`
- UX : Autocomplete dans un dropdown, clic pour sélectionner

### Auto-détection de localisation au chargement
- Si pas de lat/lon sauvegardés → appel automatique à `ipapi.co/json/`
- Permet à un nouvel utilisateur d'avoir une localisation par défaut sans configuration

### Dark mode : couleurs trop sombres
- Version initiale : `#141311` (très sombre, difficile à lire)
- Amélioré vers : `#1c1c1e` (iOS dark mode style, plus lisible)

### Notifications : modal → toast
- Avant : fenêtre modale bloquante au centre de l'écran
- Après : toast notification top-right qui s'auto-ferme après 4s

---

## Session 5 — Structure du Projet

```
src/
├── inkypi.py              # Point d'entrée Flask
├── config.py              # Gestionnaire de config JSON
├── refresh_task.py        # Thread de rafraîchissement en arrière-plan
├── blueprints/            # Routes Flask séparées par domaine
│   ├── main.py            # Dashboard + API
│   ├── plugin.py          # Gestion des plugins
│   ├── settings.py        # Paramètres de l'appareil
│   └── playlist.py        # Gestion des playlists
├── plugins/weather/
│   ├── weather.py         # Logique météo (1364 lignes, 3 providers)
│   ├── settings.html      # UI de configuration (city search, map, options)
│   └── render/
│       ├── weather.html   # Template d'affichage e-ink
│       └── weather.css    # Styles du rendu
└── static/
    ├── icons/             # Icônes météo SVG (MeteoSwiss + Meteocons)
    └── styles/main.css    # Styles de l'UI admin
```

---

## Décisions techniques notables

| Décision | Raison |
|---|---|
| Flask + Jinja2 | Léger, compatible Pi Zero 2 W |
| Playwright pour screenshot | Permet un rendu HTML riche → PNG e-ink |
| Cache 30min MeteoSwiss | API publique sans SLA, évite rate-limit |
| CartoDB tiles | OSM tiles bloquent sans Referer HTTP |
| Nominatim geocoding | Gratuit, pas de clé, données OSM précises |
| ipapi.co pour géoloc IP | Plus fiable que KeyCDN, retourne timezone |
| systemd service | Auto-restart si crash, démarre au boot |
