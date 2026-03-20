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

## Session 6 — Corrections critiques & Nouvelle UI

### Bugs critiques corrigés

#### Bug #6 : `device.json` manquant → crash au démarrage en production
**Symptôme** : L'application crashait immédiatement en mode production (sans `--dev`)
**Cause** : `config.py` lit `src/config/device.json` par défaut, mais seul `device_dev.json` existait
**Fix** : Création de `src/config/device.json` avec `display_type: "inky"`, résolution 800×480, playlist Default vide

#### Bug #7 : `image_modal.js` référencé mais inexistant → erreur 404
**Symptôme** : Erreur 404 dans la console sur chaque chargement du dashboard
**Cause** : `inky.html` chargeait `scripts/image_modal.js` mais le fichier n'existait pas
**Fix** : Création du fichier — clic sur l'aperçu ouvre l'image en plein écran (overlay modal)

#### Bug #8 : `buttons_bp` non enregistré dans Flask
**Symptôme** : La page `/settings/buttons` retournait 404
**Cause** : `buttons_bp` était implémenté dans `blueprints/buttons.py` mais jamais enregistré dans `inkypi.py`
**Fix** : Ajout de `app.register_blueprint(buttons_bp)` dans `inkypi.py`

#### Bug #9 : `device_config.set_config()` n'existe pas
**Symptôme** : Sauvegarde des boutons physiques levait `AttributeError`
**Cause** : `buttons.py` appelait `device_config.set_config()` — méthode qui n'existe pas dans `config.py`
**Fix** : Remplacement par `device_config.update_value()`

#### Bug #10 : `base.html` manquant → crash sur `/settings/buttons`
**Symptôme** : Jinja2 levait `TemplateNotFound: base.html`
**Cause** : `button_settings.html` hérite de `base.html` qui n'avait jamais été créé
**Fix** : Création de `src/templates/base.html` avec la navbar admin, dark mode, Bootstrap 5 (CDN)

#### Bug #11 : jQuery, Select2 JS/CSS manquants
**Symptôme** : Les dropdowns de recherche de ville ne fonctionnaient pas dans `plugin.html`
**Cause** : `plugin.html` référençait `scripts/jquery.min.js`, `scripts/select2.min.js`, `styles/select2.min.css` — aucun n'existait
**Fix** : Téléchargement local de jQuery 3.7.1 (87 KB), Select2 4.1.0 JS (73 KB) et CSS (16 KB)

#### Bug #12 : `current_image.png` absent → image cassée au premier lancement
**Symptôme** : Le dashboard affichait une image cassée avant le premier rafraîchissement
**Cause** : Le fichier est généré au runtime mais n'existait pas à l'installation
**Fix** : Génération d'une image placeholder (800×480, fond beige) au moment de la correction

---

### Nouvelles fonctionnalités UI

#### Polling d'aperçu accéléré (1 s au lieu de 3 s)
- `refreshIntervalMs` passé de `3000` à `1000` ms dans `inky.html`
- Le dashboard reflète les changements d'écran quasi-instantanément
- Utilise `If-Modified-Since` pour éviter de retélécharger si rien n'a changé

#### Bouton "Update Now" sur le dashboard
- Nouveau bouton dans la carte d'aperçu — force un rafraîchissement immédiat de l'écran e-ink
- Nouveau endpoint `POST /api/refresh_now` dans `blueprints/main.py`
- Détermine automatiquement la playlist active et le plugin courant, puis appelle `manual_update()`
- L'image se recharge dans l'aperçu web dans la seconde qui suit

#### Compte à rebours jusqu'au prochain rafraîchissement
- Affichage live `MM:SS` (ou `Xh YYm` si > 1 heure) dans la barre d'action du dashboard
- Décompte côté JS chaque seconde, resynchronisé depuis le serveur toutes les 30 s
- Nouveau endpoint `GET /api/status` exposant `seconds_until_refresh`, `last_refresh_time`, plugin et playlist actifs
- Calcul : `plugin_cycle_interval_seconds − (now − last_refresh_time)`

#### Drag-and-drop pour réordonner les plugins dans les playlists
- Chaque section de playlist a un bouton **Reorder** / **Save order**
- En mode réordonnage : poignées de glisser-déposer visibles, items déplaçables (HTML5 Drag API)
- La navigation (liens, boutons) est désactivée pendant le glisser pour éviter les clics accidentels
- Nouveau endpoint `POST /api/playlist_plugin_order/<playlist_name>` dans `blueprints/playlist.py`
- L'ordre est persisté dans `device.json` immédiatement

---

---

## Session 7 — Implémentation MeteoSwiss + Corrections

### MeteoSwiss — Implémentation complète
**Pourquoi MeteoSwiss ?** Fournisseur officiel suisse avec ses propres icônes SVG (`msw_1.svg`…`msw_142.svg`) — pièce maîtresse du projet.

**API** : `https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz=XXXXXX`
- Non documentée publiquement, découverte via l'app mobile MeteoSwiss
- PLZ 6 chiffres : `{NPA 4 chiffres}00` (ex. Lausanne 1002 → `100200`)
- Retourne : temp actuelle, icône (1-35 jour, 101-135 nuit), prévisions 6j, graphe 24h, vent, précipitations, lever/coucher

**Problème : NPA partiellement supportés**
- `100100` (NPA 1001) → HTTP 500 (non supporté)
- `100200` (NPA 1002) → HTTP 200 ✓
- Fix : scan ±10 NPA autour du NPA Nominatim jusqu'à trouver un valide

**Flux** : Lat/Lon → Nominatim (zoom=16) → pays=CH → scan PLZ → API MeteoSwiss → cache 30 min → parsing

**Icônes** : `msw_{code}.svg` codes 1-142 déjà dans `src/plugins/weather/icons/`

---

## Session 8 — Corrections UI & plugin météo

### Bug #13 : `plugin-info.json` weather — class name mismatch
**Symptôme** : Erreur `{"error":"An error occurred: Plugin 'weather' is not registered."}`
**Cause** : `plugin-info.json` déclarait `"class": "Weather"` mais la classe réelle est `WeatherPlugin`
**Fix** : Mis à jour en `"class": "WeatherPlugin"`

### Bug #14 : `WeatherPlugin` sans `__init__` → `TypeError` au chargement
**Symptôme** : `load_plugins` échouait silencieusement à instancier `WeatherPlugin(config)` car aucun `__init__` défini
**Cause** : `plugin_registry.py` appelle `plugin_class(plugin)` — `WeatherPlugin` n'héritait pas de `BasePlugin` et n'avait pas de constructeur
**Fix** : `WeatherPlugin` hérite maintenant de `BasePlugin` (qui fournit `__init__`, `generate_settings_template`, `cleanup`)

### Bug #15 : "Update Now" bloqué sans playlist
**Symptôme** : Cliquer "Update Now" sans playlist configurée retournait une erreur 400 et ne faisait rien
**Cause** : `refresh_now` exigeait une playlist active avec des plugins
**Fix** : Fallback — si pas de playlist, pousse directement `current_image.png` vers l'écran e-ink via `display_manager.display_image()`. Le bouton fonctionne toujours.

### Bug #16 : `alert()` bloquant pour les erreurs "Update Now"
**Symptôme** : Cliquer "Update Now" sans playlist configurée affichait un `alert()` navigateur bloquant
**Cause** : Mauvais UX — `alert()` bloque le thread JS et est intrusif
**Fix** : Remplacé par un toast inline (rouge) qui disparaît après 4 s. Message adapté : "Add a plugin to a playlist first."

### Améliorations visuelles
- Image de démarrage e-ink : remplacé `"inkypi"` par `"Hello there!"` avec fond beige chaud et tagline
- Placeholder web `current_image.png` : généré avec le même message accueillant

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
| jQuery + Select2 en local | Pas de dépendance CDN à l'exécution pour les dropdowns |
| Bootstrap 5 via CDN (base.html seulement) | Page boutons rarement visitée, poids acceptable |
| Polling 1 s avec If-Modified-Since | Aperçu réactif sans surcharger le Pi |
| Countdown côté JS + resync 30 s | Décompte fluide sans polling serveur excessif |
| HTML5 Drag API (natif) | Pas de librairie externe pour le réordonnage des plugins |
