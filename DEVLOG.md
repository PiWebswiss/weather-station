# DEVLOG — Station Météo E-Ink

Historique des décisions de développement, bugs corrigés et raisonnements techniques.

---

## Session 1 — Architecture & Setup

### Pourquoi E-InkPi ?
Choix d'E-InkPi comme base (https://github.com/fatihak/E-InkPi) plutôt qu'un script from scratch :
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

---

## Session 9 — Watch interactif + météo polish + workflow boutons

### Objectif
Transformer le dashboard d'un simple aperçu PNG en une interface plus vivante, tout en améliorant la qualité perçue du plugin météo et la boucle "configurer → sauvegarder → afficher".

### Changements principaux

#### 1. Nouveau mode watch interactif
- Ajout d'une route Flask `/live`
- Création de `src/templates/live.html`
- Le dashboard `src/templates/inky.html` propose maintenant deux modes :
  - **Display Image** : l'aperçu e-ink historique
  - **Interactive Watch** : une vraie montre côté navigateur
- Le watch mémorise :
  - le thème
  - l'affichage des secondes
  - la face (`analog`, `digital`, `word`)
- Chargement lazy de l'iframe pour éviter un coût de rendu inutile si l'utilisateur reste sur l'image

#### 2. Plugin météo : MeteoSwiss par défaut + rendu plus pro
- Correction d'un décalage subtil : l'UI affichait MeteoSwiss en premier, mais la valeur JS par défaut restait `OpenMeteo`
- `WeatherPlugin` utilise maintenant **MeteoSwiss** par défaut pour les nouvelles instances
- Refonte du rendu `src/plugins/weather/render/weather.html` :
  - hero section température + icône
  - métriques sous forme de cartes
  - badge source
  - forecast plus compact et plus lisible
- Le rendu respecte maintenant réellement la timezone choisie (`locationTimeZone` ou `localTimeZone`)
- Le réglage `moonPhase` est enfin exploité dans le template
- OpenWeatherMap est laissé en **coming soon** pour éviter de guider vers un provider non supporté ici

#### 3. Workflow plugin / boutons
- Ajout d'un bouton **Update Display** sur `src/templates/plugin.html`
- Ajout des liens **Buttons** dans la navigation principale
- Correction de `button_settings.html` :
  - appel à `showResponseModal()` avec les paramètres dans le bon ordre
- Correction de `button_handler.py` :
  - l'action physique `refresh` rafraîchit désormais **le plugin actuellement affiché**
  - auparavant elle avançait silencieusement au plugin suivant

### Vérifications
- `git diff --check` : OK
- Compilation Python ciblée des fichiers modifiés vers `/tmp` : OK
- Smoke test de rendu Jinja du template météo : OK
- Rendu réel du plugin météo en venv projet : image `800x480` générée avec succès après la refonte de layout

### Limite connue
- Un test d'import exhaustif de tous les plugins n'a pas pu être finalisé dans le shell brut de cette session, car l'interpréteur Python disponible n'embarquait pas toutes les dépendances du projet (`psutil`, `pytz`, etc.).

### Ajustement final météo
- Refonte du template météo pour se rapprocher visuellement de la maquette fournie :
  - titre centré
  - grand bloc température
  - métriques en deux colonnes
  - bande de tendance plus douce
  - cartes forecast plus fines
- La palette, les marges et les formes ont été repolies pour un rendu plus propre côté écran et côté aperçu web
- Ajout d'un fallback MeteoSwiss -> Open-Meteo pour garder un écran complet même si l'API MeteoSwiss renvoie une structure partielle

### Stabilisation de l'interface watch interactive
- Correction d'un ensemble de bugs UX sur `live.html` :
  - iframe embed simplifiée
  - resize / repaint plus robustes
  - duplication de lecture masquée en mode digital
  - word clock réaligné
  - timers nettoyés quand l'onglet se masque ou se ferme
- Correction du dashboard :
  - suppression du polling preview redondant
  - nettoyage des anciens `blob:` URLs pour éviter les fuites mémoire à force de refresh

### Composer visuel pour le plugin météo
- Le plugin météo dispose maintenant d'un vrai **Display Composer** dans `settings.html`
- L'utilisateur peut :
  - ajouter un bloc texte
  - ajouter un bloc image
  - sélectionner / déplacer un bloc sur un canvas
  - modifier son contenu, sa taille, sa position, ses couleurs, son style et son opacité
- Les images uploadées sont stockées comme fichiers sauvegardés du projet, puis reliées au bloc concerné via une clé stable
- Le rendu `weather.html` affiche réellement ces blocs personnalisés sur l'écran météo généré

### Polish final UI web
- Reprise du thème partagé `main.css` pour renforcer le rendu admin :
  - focus clavier plus visible
  - meilleure cohérence liens / boutons / cartes
  - tailles tactiles minimales plus propres
  - shell de page et modales mieux espacés
- Alignement des pages Bootstrap héritées via `base.html` pour éviter l'effet "mélange de styles"
- Remplacement des `alert()` bruts par le système de toast/modal sur :
  - settings
  - buttons
  - plugin editor
  - playlist
- Redémarrage de `inkypi.service` puis vérification HTTP :
  - `/` `200`
  - `/settings` `200`
  - `/plugin/weather` `200`
  - `/live` `200`
  - `/settings/buttons` `200`
  - `/playlist` `200`

### Correctifs install / uninstall + welcome screen
- Correction du bug d'installation lié au nom historique `e-inkpi` :
  - les scripts d'installation / update / uninstall utilisaient encore l'ancien nom
  - le dépôt embarque pourtant `inkypi.service`
- Alignement des scripts sur le nom réel `inkypi`
- Durcissement de `uninstall.sh` :
  - suppression des unités `inkypi` et `e-inkpi` si elles existent
  - suppression des binaires et chemins legacy
  - évitement de la suppression accidentelle de `src/config/device.json` dans le dépôt quand `src` est monté via symlink
- Réactivation de l'écran de bienvenue au moment de l'installation
- Refonte du rendu de ce welcome screen :
  - titre plus clair
  - `http://<hostname>.local`
  - `http://<ip-address>`
  - message d'aide réseau si `.local` ne résout pas

### Vérifications complémentaires
- `bash -n install/install.sh` : OK
- `bash -n install/uninstall.sh` : OK
- `python3 -m py_compile src/utils/app_utils.py` : OK
- rendu réel du welcome screen généré en `800x480` : OK

### Reprise du layout météo par défaut
- Refonte du template météo pour coller davantage à la référence fournie :
  - header simplifié
  - bloc météo principal plus aéré
  - température plus dominante
  - cartes forecast plus fines
  - moins d'éléments parasites par défaut
- Le thème MeteoSwiss n'est plus réservé au provider MeteoSwiss :
  - les icônes météo MeteoSwiss sont aussi utilisées avec **Open-Meteo**
  - cela garde une cohérence visuelle pour les villes hors Suisse
- Ajout de deux contrôles de personnalisation globaux dans les settings météo :
  - `weatherBackgroundColor`
  - `weatherTextColor`
- Par défaut, le champ "refresh time" est maintenant désactivé pour garder un écran plus proche de la maquette

### Vérifications météo
- `git diff --check` ciblé sur le plugin météo : OK
- compilation Python ciblée de `weather.py` : OK
- rendu réel `800x480` d'un écran **Los Angeles, California** avec **Open-Meteo** et style MeteoSwiss : OK
- après redémarrage service :
  - `/` `200`
  - `/plugin/weather` `200`
  - `/live` `200`
  - `/settings` `200`

### Correctif render watch / clock dashboard
- Diagnostic :
  - le screenshot utilisateur montrait le mode `Interactive Watch` du dashboard
  - ce mode n'était qu'un aperçu navigateur
  - `Update Now` ne rendait donc pas la watch au display
- Correctif appliqué :
  - ajout d'un endpoint `POST /api/render_live_watch`
  - génération serveur d'une image statique de la watch à partir de l'état courant :
    - face `analog`
    - face `digital`
    - face `word`
    - thème clair / sombre
    - secondes on/off
  - le bouton dashboard adapte maintenant son libellé :
    - `Update Now` pour l'image
    - `Render Watch` pour la watch
- Vérifications :
  - `main.py` compilé vers `/tmp` : OK
  - `git diff --check` ciblé : OK
  - `POST /api/render_live_watch` : OK
  - `/api/status` retourne maintenant `current_plugin_id: live_watch`
  - `current_image.png` contient bien la watch rendue

### Correctif heure watch / live clock
- Problème signalé :
  - l'heure de la watch n'était pas toujours correcte
  - le rendu statique et la page interactive dépendaient encore trop de l'horloge du navigateur
- Correctif appliqué :
  - ajout d'un snapshot horaire serveur timezone-aware dans `main.py`
  - injection de ce snapshot dans `live_render.html` pour figer le rendu e-ink sur l'heure exacte du serveur
  - enrichissement de `/api/status` avec :
    - `server_time_iso`
    - `server_time_epoch_ms`
    - `server_time_offset_minutes`
    - `server_timezone`
  - la page `live.html` utilise maintenant cette horloge serveur comme base et se resynchronise au polling statut
  - le footer de dernière mise à jour n'utilise plus le fuseau local du navigateur
- Vérifications :
  - compilation Python de `src/blueprints/main.py` vers `/tmp` : OK
  - `git diff --check` ciblé : OK
  - redémarrage de `inkypi.service` : OK
  - `/` : `200`
  - `/live` : `200`
  - `/api/current_image` : `200`
  - `/api/status` : `200`
  - `POST /api/render_live_watch` : OK
  - `/api/status` après rendu :
    - `current_plugin_id: live_watch`
    - `server_timezone: Europe/Zurich`

### Simplification UI du plugin météo + lisibilité écran
- Suppression de l'ancien bloc `Layout Designer` dans `src/plugins/weather/settings.html`
- Conservation du `Display Composer` comme seul outil de personnalisation visuelle côté météo
- Reprise des cartes forecast 5 jours :
  - bordure plus propre
  - fond moins blanc
  - meilleur rendu sur les thèmes plus sombres
- Reprise du rendu météo principal :
  - texte sous le graphique horaire assombri et agrandi
  - labels des métriques plus lisibles
  - valeurs météo plus contrastées
  - icônes météo un peu plus présentes
  - pression mise en avant avec son icône dans le panneau courant
  - badge clair ajouté derrière les icônes pour une meilleure visibilité sur fond sombre
  - complément Open-Meteo désormais récupéré aussi en mode MeteoSwiss pour garantir la pression
- Vérifications :
  - compilation Python de `src/plugins/weather/weather.py` vers `/tmp` : OK
  - `git diff --check` ciblé : OK
  - redémarrage de `inkypi.service` : OK
  - `/plugin/weather` : `200`
  - `/` : `200`

### Notification horodatée lors des mises à jour écran
- Les endpoints d'update renvoient maintenant un horodatage structuré :
  - `updated_at`
  - `updated_at_display`
  - `updated_at_long`
  - `updated_timezone`
- Le bouton `Update Display` des pages plugin affiche maintenant un message du type :
  - `Screen updated at 21:31 (Europe/Zurich).`
- Le dashboard affiche désormais :
  - `Screen updated at HH:MM`
  - `Watch rendered at HH:MM`
- L'action d'affichage d'une instance depuis les playlists réutilise aussi ce message horodaté
- Vérifications :
  - compilation Python de `src/blueprints/main.py` vers `/tmp` : OK
  - compilation Python de `src/blueprints/plugin.py` vers `/tmp` : OK
  - `git diff --check` ciblé : OK
  - `POST /api/refresh_now` : OK
  - `POST /api/render_live_watch` : OK

### Consolidation météo multi-profils couleur
- Problème signalé :
  - les icônes de métriques restaient peu visibles sur fonds sombres
  - certaines combinaisons personnalisées fond / texte rendaient l'écran trop plat
  - l'utilisateur voulait rester sur seulement 4 métriques
- Correctif appliqué :
  - ajout d'une dérivation de thème météo plus robuste dans `src/plugins/weather/weather.py`
  - correction automatique de la couleur de texte si le contraste avec le fond choisi est insuffisant
  - ajout d'un fond de carte et d'une bordure au bloc météo principal et au bloc graphique dans `src/plugins/weather/render/weather.html`
  - limitation du panneau métriques à 4 informations principales :
    - `Sunrise`
    - `Wind`
    - `Pressure`
    - `Humidity`
  - badges d'icônes renforcés pour rester visibles sur thèmes sombres
  - champs `input[type=color]` rendus plus lisibles dans `src/static/styles/main.css`
- Vérifications :
  - compilation Python de `src/plugins/weather/weather.py` vers `/tmp` : OK
  - `git diff --check` ciblé : OK

### Ajustement du header partagé des plugins
- Problème signalé :
  - le bouton `Back` était trop proche du bloc titre / icône sur les pages plugin
  - besoin de vérifier aussi les autres plugins
- Correctif appliqué :
  - ajout d'une marge sous le bouton `Back` dans `src/static/styles/main.css`
  - léger ajustement vertical du header partagé plugin/settings
  - correctif mutualisé pour toutes les pages qui utilisent ce shell
- Vérifications :
  - `git diff --check` ciblé : OK
  - sweep des routes `/plugin/<id>` : tous les vrais plugins testés retournent `200`
  - `/settings` : `200`
  - `/playlist` : `200`
  - `/plugin/weather` : `200`

### Sécurisation des couleurs météo pour l'écran E-Ink
- Problème signalé :
  - avec certaines autres couleurs, le rendu météo devenait trop faible ou presque invisible sur l'écran
- Correctif appliqué :
  - rollback des essais couleur météo qui dégradaient le rendu
  - retour à une logique thème météo plus simple dans `src/plugins/weather/weather.py`
  - protection automatique de la couleur de texte si le contraste devient trop faible
  - valeurs par défaut météo fixées à fond blanc / texte sombre dans `src/plugins/weather/settings.html`
  - push manuel d'un nouvel écran météo clair via `/update_now` pour remplacer l'ancien rendu sombre
  - retrait des dégradés de fond météo et simplification des cartes / bordures dans `src/plugins/weather/render/weather.html`
  - clarification du comportement :
    - mode clair = fond blanc et rectangles lisibles
    - mode noir = fond noir et structure plus dure, pensée pour mieux correspondre au rendu Spectra réel
  - renforcement du texte trop faible en mode clair :
    - labels météo plus foncés
    - graph labels plus foncés
    - textes secondaires agrandis
  - amélioration de netteté du rendu météo :
    - image-rendering plus strict sur les icônes
    - text-rendering plus précis côté HTML
    - unsharp mask léger appliqué après screenshot Chromium
- Vérifications :
  - compilation Python de `src/plugins/weather/weather.py` vers `/tmp` : OK
  - `git diff --check` ciblé : OK
  - redémarrage de `inkypi.service` : OK
  - `/plugin/weather` : `200`
  - `/` : `200`
  - `POST /update_now` météo : OK

### Stabilisation du rendu matériel Inky / Spectra
- Nouveau constat :
  - le screenshot météo était redevenu correct, mais la photo du panneau montrait encore une dérive couleur côté matériel
- Correctif appliqué :
  - durcissement du mode sombre météo pour revenir à un vrai noir en fond / panneaux dans `src/plugins/weather/weather.py`
  - désactivation de l'unsharp mask pour le mode sombre afin d'éviter les halos gris visibles après quantification Spectra
  - recentrage des réglages matériels par défaut :
    - `brightness` de `2.0` vers `1.0`
    - `inky_saturation` de `0.5` vers `0.0`
  - alignement des valeurs de fallback dans :
    - `src/display/inky_display.py`
    - `src/blueprints/settings.py`
    - `src/templates/settings.html`
    - `src/config/device.json`
    - `install/config_base/device.json`
- Vérifications :
  - compilation Python ciblée : OK
  - `git diff --check` ciblé : OK
  - `inkypi.service` : `active`
  - `/` : `200`
  - `/plugin/weather` : `200`
  - `POST /update_now` sombre : OK
  - `POST /update_now` clair : OK
  - `current_image.png` vérifié :
    - sombre : noir réel
    - clair : blanc réel + cartes gris clair

### Nettoyage visuel de la pression météo
- Ajustement demandé :
  - retirer la ligne / forme spéciale autour de `Pressure`
- Correctif appliqué :
  - suppression du style dédié `.stat-item.pressure-item` dans `src/plugins/weather/render/weather.html`
  - la métrique pression utilise désormais exactement le même rendu que les autres métriques
- Vérifications :
  - `git diff --check` ciblé : OK
  - `inkypi.service` : `active`
  - `/plugin/weather` : `200`
