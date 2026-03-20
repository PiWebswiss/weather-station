# Station Météo E-Ink — Documentation d'implémentation complète

**Projet** : Station météo e-ink sur Raspberry Pi Zero 2 W
**Auteur** : Développement assisté par Claude (Anthropic)
**Date** : Mars 2026
**Dépôt** : `/home/pi/weather-station`
**Base** : [E-InkPi](https://github.com/fatihak/E-InkPi) par fatihak

---

## Table des matières

1. [Contexte et objectifs](#1-contexte-et-objectifs)
2. [Architecture matérielle](#2-architecture-matérielle)
3. [Architecture logicielle](#3-architecture-logicielle)
4. [Session 1 — Analyse de l'existant et choix technologiques](#4-session-1--analyse-de-lexistant-et-choix-technologiques)
5. [Session 2 — APIs météo et implémentation des providers](#5-session-2--apis-météo-et-implémentation-des-providers)
6. [Session 3 — Bugs corrigés (phase 1)](#6-session-3--bugs-corrigés-phase-1)
7. [Session 4 — Amélioration UX et nouvelles fonctionnalités UI](#7-session-4--amélioration-ux-et-nouvelles-fonctionnalités-ui)
8. [Session 5 — Restructuration et architecture finale](#8-session-5--restructuration-et-architecture-finale)
9. [Session 6 — Corrections critiques et nouvelle UI](#9-session-6--corrections-critiques-et-nouvelle-ui)
10. [Session 7 — Implémentation MeteoSwiss (pièce maîtresse)](#10-session-7--implémentation-meteoswiss-pièce-maîtresse)
11. [Session 8 — Corrections finales et polish](#11-session-8--corrections-finales-et-polish)
12. [Installation et désinstallation](#12-installation-et-désinstallation)
13. [Décisions techniques — Récapitulatif](#13-décisions-techniques--récapitulatif)
14. [Bugs résolus — Récapitulatif complet](#14-bugs-résolus--récapitulatif-complet)
15. [API MeteoSwiss — Documentation technique](#15-api-meteoswiss--documentation-technique)
16. [Structure finale du projet](#16-structure-finale-du-projet)
17. [Addendum — Watch interactif, météo polish et workflow boutons](#17-addendum--watch-interactif-météo-polish-et-workflow-boutons)

---

## 1. Contexte et objectifs

### Vision initiale

L'objectif était de construire une **station météo personnalisée sur écran e-ink**, en utilisant un Raspberry Pi Zero 2 W comme cerveau et un écran Inky Impression (7 couleurs) comme afficheur.

La contrainte principale : afficher les **données météo officielles MeteoSwiss** (Suisse) avec leurs **icônes SVG propriétaires** — c'est « la pièce maîtresse du projet ».

### Objectifs fonctionnels

| Objectif | Statut |
|----------|--------|
| Affichage météo e-ink avec données MeteoSwiss | ✅ |
| UI web d'administration moderne | ✅ |
| Drag-and-drop pour réordonner les plugins | ✅ |
| Preview en direct (1 seconde) | ✅ |
| Bouton "Update Now" toujours fonctionnel | ✅ |
| Compte à rebours jusqu'au prochain refresh | ✅ |
| Firewall UFW (SSH/HTTP/HTTPS uniquement) | ✅ |
| Installation et désinstallation en une commande | ✅ |
| Icônes MeteoSwiss SVG (msw_1.svg à msw_142.svg) | ✅ |

---

## 2. Architecture matérielle

### Raspberry Pi Zero 2 W

- **Prix** : ~20 CHF
- **CPU** : ARM Cortex-A53 quad-core 1 GHz (64-bit)
- **RAM** : 512 MB LPDDR2
- **Connectivité** : Wi-Fi 802.11 b/g/n, Bluetooth 4.2
- **GPIO** : 40 broches
- **Consommation** : ~500 mA en pointe

**Pourquoi ce modèle ?**
Le Pi Zero 2 W est le premier modèle « Zero » assez puissant pour faire tourner Flask + Playwright simultanément. Son prédécesseur (Pi Zero W) était trop lent pour le rendu HTML vers PNG.

### Écran Inky Impression

- **Résolution** : 800×480 pixels
- **Couleurs** : 7 couleurs e-ink (noir, blanc, rouge, vert, bleu, jaune, orange)
- **Interface** : SPI + I2C
- **Refresh** : ~30 secondes pour un rafraîchissement complet
- **Persistance** : L'image est conservée sans alimentation

### Connexion physique

```
Pi Zero 2 W GPIO ──── SPI ──── Inky Impression
                  └── I2C ──── (lecture des données d'écran)
```

L'installation active SPI et I2C via `raspi-config` et modifie `/boot/firmware/config.txt`.

---

## 3. Architecture logicielle

### Vue d'ensemble

```
Flask (Waitress en prod)
    ├── blueprints/
    │   ├── main.py        # Dashboard + API endpoints
    │   ├── plugin.py      # Gestion des plugins
    │   ├── settings.py    # Paramètres de l'appareil
    │   ├── playlist.py    # Gestion des playlists
    │   └── buttons.py     # Mapping des boutons physiques
    ├── plugins/
    │   ├── base_plugin/   # Classe de base abstraite
    │   └── weather/       # Plugin météo (MeteoSwiss / OpenMeteo / OWM)
    ├── display/           # Abstraction écran (Inky + Waveshare)
    ├── config.py          # Gestionnaire de config JSON
    └── refresh_task.py    # Thread de rafraîchissement en arrière-plan
```

### Flux de données

```
Utilisateur → UI Web → Flask API → Plugin Weather → MeteoSwiss API
                                       ↓
                              Playwright (screenshot HTML → PNG)
                                       ↓
                              Inky display (SPI → e-ink)
                                       ↓
                              current_image.png (preview web)
```

### Système de plugins

Chaque plugin se compose de :
- `plugin-info.json` : métadonnées (id, nom affiché, nom de classe Python)
- `{plugin}.py` : logique métier, hérite de `BasePlugin`
- `settings.html` : formulaire de configuration (Jinja2)
- `render/` : template HTML + CSS pour le rendu e-ink

Le registre de plugins charge dynamiquement les classes via `importlib` :

```python
plugin_class = PLUGIN_CLASSES.get(plugin_id)
instance = plugin_class(plugin_config)  # appelle __init__(config)
image = instance.generate_image(width, height, device_config)
```

---

## 4. Session 1 — Analyse de l'existant et choix technologiques

### Pourquoi E-InkPi comme base ?

Plutôt que de partir from scratch, E-InkPi offrait :
- Architecture Flask propre avec système de plugins modulaire
- Support natif Inky (Pimoroni) et Waveshare
- Système de playlists et intervalles de refresh configurables
- UI web admin déjà fonctionnelle (même si nécessitant refonte)

**Coût** : le code de base était fonctionnel mais incomplet — plusieurs bugs critiques empêchaient son utilisation en production.

### Choix de Waitress vs Gunicorn vs dev server

Waitress a été choisi comme serveur WSGI de production :
- Pure Python, pas de dépendances C
- Multithread (contrairement au serveur de dev Flask)
- Simple à configurer
- Compatible ARM sans compilation

### Choix de Playwright vs wkhtmltopdf vs WeasyPrint

Pour le rendu HTML → PNG :
- **Playwright** : rendu Chromium complet, support CSS moderne, JavaScript
- **wkhtmltopdf** : pas de JS, support CSS limité
- **WeasyPrint** : CSS limité, problèmes avec les polices custom

Playwright gagne malgré son poids (~200 MB) car il permet un rendu fidèle des templates météo complexes.

---

## 5. Session 2 — APIs météo et implémentation des providers

### Architecture multi-provider

Trois providers météo ont été implémentés pour différents cas d'usage :

#### Provider 1 : Open-Meteo (défaut international)

- **URL** : `https://api.open-meteo.com/v1/forecast`
- **Avantages** : Gratuit, sans clé API, global
- **Données** : température, précipitations, codes météo WMO, vent
- **Bugs rencontrés** :
  - `models=best_match` supprimé de l'API v1 → erreur 400
  - `daily=weathercode` devait être `daily=weather_code` (avec underscore)

#### Provider 2 : OpenWeatherMap (pour les non-Suisses)

- **URL** : `https://api.openweathermap.org/data/2.5/`
- **Avantages** : Bien documenté, icônes officielles
- **Inconvénients** : Clé API requise (freemium)

#### Provider 3 : MeteoSwiss (prioritaire pour la Suisse)

Voir section dédiée (Session 7).

### Sélection du provider dans l'UI

```html
<select name="weatherProvider">
  <option value="MeteoSwiss" selected>MeteoSwiss (Switzerland only)</option>
  <option value="OpenMeteo">Open-Meteo (Global, no API key)</option>
  <option value="OpenWeatherMap">OpenWeatherMap (API key required)</option>
</select>
```

MeteoSwiss est sélectionné par défaut.

---

## 6. Session 3 — Bugs corrigés (phase 1)

### Bug #1 : `get_icon_path({name})` — Set literal Python

**Symptôme** : Les icônes météo ne s'affichaient pas.

**Cause** : En Python, `{variable}` crée un **set**, pas une f-string. Le code écrivait :
```python
self.get_icon_path({current_icon})  # Produit : icons/{'01d'}.svg
```
au lieu de :
```python
self.get_icon_path(current_icon)    # Produit : icons/01d.svg
```

**Fix** : Correction des 3 occurrences (lignes 213, 238, 477).

### Bug #2 : OpenMeteo `models=best_match` deprecated

**Symptôme** : Requêtes Open-Meteo retournaient une erreur API.

**Cause** : Le paramètre `models=best_match` a été retiré de l'API v1 après une mise à jour.

**Fix** : Suppression du paramètre de l'URL de requête.

### Bug #3 : OpenMeteo `weathercode` vs `weather_code`

**Symptôme** : Toutes les prévisions quotidiennes affichaient une icône soleil.

**Cause** : L'API retourne `weather_code` (avec underscore) mais l'URL demandait `weathercode`.

**Fix** :
- URL : `daily=weather_code`
- Parser : `daily_data.get('weather_code', ...)`

### Bug #4 : OpenStreetMap tiles bloqués

**Symptôme** : La carte de sélection de localisation affichait "Referer is required".

**Cause** : Les tiles OSM `tile.openstreetmap.org` bloquent les requêtes sans header `Referer`, conformément à leur politique d'utilisation.

**Fix** : Remplacement par les tiles CartoDB :
```javascript
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '© CartoDB'
})
```

### Bug #5 : Géolocalisation GPS silencieusement bloquée

**Symptôme** : Le bouton GPS ne répondait pas sur HTTP.

**Cause** : `navigator.geolocation` est une API sécurisée — elle nécessite HTTPS (sauf sur `localhost`). Sur une connexion HTTP simple, l'appel échoue silencieusement.

**Fix** : Détection explicite du protocole + message d'erreur clair :
```javascript
if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
    showError('GPS requires HTTPS. Use Cloudflare tunnel or localhost.');
    return;
}
```

---

## 7. Session 4 — Amélioration UX et nouvelles fonctionnalités UI

### Recherche de ville par nom (Nominatim)

**Problème** : L'utilisateur devait connaître ses coordonnées GPS ou utiliser la carte Leaflet.

**Solution** : Géocodage par nom de ville via l'API Nominatim (OpenStreetMap, gratuit, sans clé) :

```javascript
fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=5`)
    .then(r => r.json())
    .then(results => showDropdown(results))
```

**UX** : Champ de recherche avec autocomplete — liste déroulante avec les 5 premiers résultats, clic pour sélectionner et centrer la carte.

### Auto-détection de localisation au chargement

Si aucune lat/lon n'est sauvegardée, l'application appelle automatiquement `ipapi.co` :

```javascript
if (!savedLat && !savedLon) {
    fetch('https://ipapi.co/json/')
        .then(r => r.json())
        .then(data => {
            map.setView([data.latitude, data.longitude], 12);
            updateCoords(data.latitude, data.longitude);
        });
}
```

### Dark mode UI

Implémenté avec une variable CSS `--bg-color` et une classe `dark` sur `<body>` :

- **Couleur initiale** : `#141311` — trop sombre, difficile à lire
- **Couleur finale** : `#1c1c1e` — style iOS dark mode, plus lisible

Toggle persisté dans `localStorage`.

### Notifications : modal → toast

**Avant** : `window.alert()` — modal bloquant, bloque le thread JS, UX terrible.

**Après** : Toast notification top-right :
- Apparaît en `position: fixed; top: 1rem; right: 1rem`
- Auto-dismiss après 4 secondes
- Variants : `.success` (vert) et `.error` (rouge)
- Non-bloquant, l'utilisateur peut continuer à utiliser l'UI

---

## 8. Session 5 — Restructuration et architecture finale

### Structure du projet

```
src/
├── inkypi.py              # Point d'entrée Flask + enregistrement des blueprints
├── config.py              # Gestionnaire de config JSON (device.json, plugins.json)
├── refresh_task.py        # Thread de rafraîchissement en arrière-plan
├── blueprints/
│   ├── main.py            # Dashboard + API (status, refresh_now, current_image)
│   ├── plugin.py          # CRUD plugins
│   ├── settings.py        # Paramètres device
│   ├── playlist.py        # Gestion playlists + réordonnage
│   └── buttons.py         # Mapping boutons physiques
├── plugins/
│   ├── base_plugin/
│   │   └── base_plugin.py # Classe abstraite BasePlugin
│   └── weather/
│       ├── plugin-info.json
│       ├── weather.py      # 1400+ lignes — 3 providers
│       ├── settings.html   # UI configuration météo
│       └── render/
│           ├── weather.html
│           └── weather.css
├── display/
│   ├── display_manager.py
│   ├── inky_display.py
│   └── waveshare_epd/
├── templates/
│   ├── base.html          # Layout admin Bootstrap 5
│   └── inky.html          # Dashboard principal
├── static/
│   ├── icons/             # Icônes UI
│   ├── images/
│   │   └── current_image.png
│   ├── scripts/
│   │   ├── jquery.min.js
│   │   ├── select2.min.js
│   │   └── image_modal.js
│   └── styles/
│       ├── main.css
│       └── select2.min.css
└── config/
    ├── device.json         # Config runtime (display_type, résolution, playlists)
    └── device_dev.json     # Config développement
```

---

## 9. Session 6 — Corrections critiques et nouvelle UI

### Bug #6 : `device.json` manquant → crash au démarrage

**Symptôme** : L'application crashait immédiatement en mode production.

**Cause** : `config.py` lit `src/config/device.json` par défaut. Seul `device_dev.json` existait.

**Fix** : Création de `src/config/device.json` :
```json
{
    "display_type": "inky",
    "resolution": [800, 480],
    "playlists": {
        "Default": {
            "plugins": [],
            "interval": 300
        }
    },
    "active_playlist": "Default"
}
```

### Bug #7 : `image_modal.js` manquant → 404

**Symptôme** : Erreur 404 dans la console sur chaque chargement du dashboard.

**Fix** : Création du fichier — clic sur l'aperçu ouvre l'image en plein écran (overlay modal avec fermeture au clic ou touche Escape).

### Bug #8 : `buttons_bp` non enregistré dans Flask

**Symptôme** : La page `/settings/buttons` retournait 404.

**Cause** : `buttons_bp` était implémenté dans `blueprints/buttons.py` mais jamais enregistré.

**Fix** : Dans `inkypi.py` :
```python
from blueprints.buttons import buttons_bp
app.register_blueprint(buttons_bp)
```

### Bug #9 : `device_config.set_config()` inexistant

**Symptôme** : Sauvegarde des boutons physiques levait `AttributeError`.

**Cause** : `buttons.py` appelait `device_config.set_config()` — méthode inexistante dans `config.py`.

**Fix** : Remplacement par `device_config.update_value()`.

### Bug #10 : `base.html` manquant → crash Jinja2

**Symptôme** : `TemplateNotFound: base.html`

**Fix** : Création de `src/templates/base.html` avec navbar admin, dark mode toggle, Bootstrap 5 (CDN).

### Bug #11 : jQuery, Select2 manquants

**Symptôme** : Erreurs 404 pour `scripts/jquery.min.js`, `scripts/select2.min.js`, `styles/select2.min.css`.

**Fix** : Téléchargement local :
- jQuery 3.7.1 (87 KB)
- Select2 4.1.0 JS (73 KB)
- Select2 4.1.0 CSS (16 KB)

Hébergement local pour éviter la dépendance CDN à l'exécution.

### Bug #12 : `current_image.png` absent au premier lancement

**Symptôme** : Dashboard affichait une image cassée (img 404).

**Fix** : Génération d'une image placeholder via PIL au moment de l'installation :
```python
from PIL import Image, ImageDraw, ImageFont

img = Image.new('RGB', (800, 480), (245, 242, 235))
draw = ImageDraw.Draw(img)
draw.text((400, 200), "Hello there!", fill=(40, 40, 40), anchor='mm', font=title_font)
draw.text((400, 260), "Your display is ready.", fill=(100, 100, 100), anchor='mm', font=sub_font)
img.save('src/static/images/current_image.png')
```

### Nouvelles fonctionnalités UI

#### Polling d'aperçu accéléré (1 s au lieu de 3 s)

```javascript
const refreshIntervalMs = 1000;

function pollPreview() {
    fetch('/api/current_image', {
        headers: { 'If-Modified-Since': lastModified }
    })
    .then(r => {
        if (r.status === 200) {
            lastModified = r.headers.get('Last-Modified');
            return r.blob();
        }
        // 304 Not Modified — rien à faire
    })
    .then(blob => blob && (previewImg.src = URL.createObjectURL(blob)));
}

setInterval(pollPreview, refreshIntervalMs);
```

**Côté serveur** (`/api/current_image`) :
```python
@main_bp.route('/api/current_image')
def current_image():
    path = device_config.current_image_file
    mtime = os.path.getmtime(path)
    last_modified = http_date(mtime)

    if_modified = request.headers.get('If-Modified-Since')
    if if_modified and parsedate(if_modified) >= parsedate(last_modified):
        return '', 304

    return send_file(path, last_modified=mtime)
```

#### Bouton "Update Now"

**Endpoint** : `POST /api/refresh_now`

**Logique** :
1. Cherche la playlist active
2. Si playlist avec plugins → exécute le plugin courant
3. Si pas de playlist ou aucun plugin → pousse `current_image.png` directement :

```python
# Fallback sans playlist
with Image.open(device_config.current_image_file) as img:
    display_manager.display_image(img.copy())
```

**Important** : Le bouton fonctionne **toujours**, même sans aucun plugin configuré.

#### Compte à rebours

**Endpoint** : `GET /api/status`
```json
{
    "seconds_until_refresh": 247,
    "last_refresh_time": "2026-03-20T14:32:00Z",
    "current_plugin_id": "weather",
    "active_playlist": "Default"
}
```

**Côté JS** : Tick toutes les secondes, resync depuis le serveur toutes les 30 s :
```javascript
let secondsLeft = 0;

function updateCountdown() {
    if (secondsLeft > 3600) {
        const h = Math.floor(secondsLeft / 3600);
        const m = Math.floor((secondsLeft % 3600) / 60);
        countdownEl.textContent = `${h}h ${String(m).padStart(2,'0')}m`;
    } else {
        const m = Math.floor(secondsLeft / 60);
        const s = secondsLeft % 60;
        countdownEl.textContent = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }
    secondsLeft = Math.max(0, secondsLeft - 1);
}

setInterval(updateCountdown, 1000);
setInterval(syncFromServer, 30000);
```

#### Drag-and-drop pour réordonner les plugins

Implémenté avec l'API HTML5 Drag native (sans bibliothèque externe) :

```javascript
item.draggable = true;
item.addEventListener('dragstart', e => {
    dragSrc = item;
    e.dataTransfer.effectAllowed = 'move';
});
item.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    // Réordonnage visuel pendant le drag
    const rect = item.getBoundingClientRect();
    const isBefore = e.clientY < rect.top + rect.height / 2;
    list.insertBefore(dragSrc, isBefore ? item : item.nextSibling);
});
```

**Endpoint de sauvegarde** : `POST /api/playlist_plugin_order/<playlist_name>`

---

## 10. Session 7 — Implémentation MeteoSwiss (pièce maîtresse)

### Pourquoi MeteoSwiss est critique

MeteoSwiss est le fournisseur météo officiel de la Confédération suisse. Ses données :
- Sont générées à partir de 160+ stations météo sur le territoire suisse
- Utilisent des modèles numériques de haute résolution (COSMO-1E, ICON-CH)
- Incluent des **prévisions horaires sur 7 jours**
- Sont accompagnées d'**icônes SVG officielles** (msw_1.svg à msw_142.svg) — 35 codes de jour + 35 codes de nuit + variantes

Ces icônes sont la signature visuelle du projet : elles donnent à l'affichage e-ink un aspect officiel et professionnel.

### Découverte de l'API

#### API STAC/OGD (voie officielle) — abandonné

MeteoSwiss publie une API officielle via leur portail OGD (données ouvertes gouvernementales). Après investigation, cette API :
- Retournait 404 pour tous les endpoints testés dans les collections forecasting
- N'offrait pas de données de prévision en temps réel structurées
- Nécessitait le téléchargement de CSV volumineux (points de prévision nationaux)

#### API App Mobile (non documentée) — retenue

En analysant le trafic réseau de l'application mobile MeteoSwiss, une API non documentée a été découverte :

```
GET https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz=XXXXXX
```

**Paramètre** : `plz` — code postal suisse en **format 6 chiffres** : `{NPA à 4 chiffres}00`

**Exemples** :
- Lausanne (NPA 1002) → `plz=100200`
- Genève (NPA 1201) → `plz=120100`
- Zurich (NPA 8001) → `plz=800100`

**Réponse** (JSON, résumé) :
```json
{
    "currentWeather": {
        "temperature": 12.3,
        "icon": 5,
        "iconV2": 5,
        "windDirection": 270,
        "windSpeed": 15.2,
        "humidity": 68
    },
    "forecast": [
        {
            "dayDate": "2026-03-20",
            "iconDay": 5,
            "temperatureMax": 15,
            "temperatureMin": 8,
            "precipitation": 2.1,
            "windDirection": 270,
            "windSpeed": 18
        }
    ],
    "graph": {
        "start": "2026-03-20T00:00:00+01:00",
        "temperatureShade1h": [8.1, 8.3, 8.5, ...],
        "precipitation10m": [0.0, 0.0, 0.1, ...],
        "windSpeed10m": [12.0, 11.5, ...],
        "sunriseDate": "2026-03-20T06:42:00+01:00",
        "sunsetDate": "2026-03-20T19:18:00+01:00"
    }
}
```

### Problème : PLZ partiellement supportés

**Découverte critique** : L'API MeteoSwiss ne supporte pas tous les NPA suisses. Certains retournent HTTP 500 :

```
plz=100100 → HTTP 500 (NPA 1001, Lausanne centre — non supporté)
plz=100200 → HTTP 200 ✓ (NPA 1002, Lausanne — supporté)
plz=120100 → HTTP 500
plz=121200 → HTTP 200 ✓
```

**Solution : algorithme de scan**

```python
def _find_valid_msw_plz(base_plz4: int) -> str | None:
    """Scan ±10 PLZ codes to find one supported by MeteoSwiss API."""
    deltas = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8, 9, -9, 10, -10]

    for delta in deltas:
        plz6 = f"{base_plz4 + delta:04d}00"
        try:
            r = requests.get(
                "https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail",
                params={"plz": plz6},
                timeout=5,
                headers={"User-Agent": "MeteoSwissApp/2.5.1"}
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("currentWeather", {}).get("temperature") is not None:
                    return plz6
        except Exception:
            continue

    return None
```

### Flux complet MeteoSwiss

```
Lat/Lon (utilisateur)
    ↓
Nominatim reverse geocoding (zoom=16)
    → Retourne: postcode="1006", country_code="ch"
    ↓
_find_valid_msw_plz(1006)
    → Scan: 100600, 100700, 100500, ...
    → Retourne: "100600" (si supporté)
    ↓
GET /v1/plzDetail?plz=100600
    → Données météo complètes
    ↓
Cache en mémoire (30 min, clé = base_plz4)
    ↓
_parse_meteoswiss(data, settings)
    → Température actuelle, icône, vent, humidité
    → Prévisions 6 jours (iconDay, tempMax, tempMin)
    → Graphe 24h (températures horaires, précipitations)
    → Lever/coucher du soleil
```

**Note critique sur Nominatim** : Le zoom=16 est **obligatoire** pour obtenir les codes postaux suisses. Les zooms 10-15 retournent des données trop générales (niveau commune/canton), sans postcode.

```python
r = requests.get(
    "https://nominatim.openstreetmap.org/reverse",
    params={"lat": lat, "lon": lon, "format": "json", "zoom": 16},
    headers={"User-Agent": "E-InkPi-WeatherStation/1.0"}
)
address = r.json().get("address", {})
country = address.get("country_code", "").lower()
postcode = address.get("postcode", "")
```

### Icônes MeteoSwiss

**Codes** :
- 1–35 : codes de **jour** (msw_1.svg à msw_35.svg)
- 101–135 : codes de **nuit** (msw_101.svg à msw_135.svg)
- La nuit = code_jour + 100

**Descriptions principales** :
```python
_MSW_DESCRIPTIONS = {
    1: "Ensoleillé",
    2: "Légèrement nuageux",
    3: "Partiellement nuageux",
    5: "Nuageux",
    8: "Couvert",
    14: "Pluie et soleil",
    17: "Orage",
    27: "Neige",
    # ... (35 codes au total)
}
```

### Cache 30 minutes

```python
_MSW_CACHE: dict[int, tuple[float, dict]] = {}
CACHE_TTL = 1800  # 30 minutes en secondes

def _fetch_meteoswiss(lat: float, lon: float) -> dict:
    base_plz4 = _get_base_plz4(lat, lon)

    if base_plz4 in _MSW_CACHE:
        cached_at, data = _MSW_CACHE[base_plz4]
        if time.time() - cached_at < CACHE_TTL:
            return data

    plz6 = _find_valid_msw_plz(base_plz4)
    data = requests.get(f"https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz={plz6}").json()
    _MSW_CACHE[base_plz4] = (time.time(), data)
    return data
```

Le cache est essentiel : l'API publique non documentée n'a pas de SLA, et le scan des PLZ peut prendre plusieurs secondes.

---

## 11. Session 8 — Corrections finales et polish

### Bug #13 : `plugin-info.json` — class name mismatch

**Symptôme** : `{"error":"Plugin 'weather' is not registered."}` sur chaque opération météo.

**Cause** : `plugin-info.json` déclarait `"class": "Weather"` mais la classe Python est `WeatherPlugin`.

**Fix** :
```json
{
    "display_name": "Weather",
    "id": "weather",
    "class": "WeatherPlugin"
}
```

Ce bug bloquait **100% des fonctionnalités météo** depuis le début.

### Bug #14 : `WeatherPlugin` sans `__init__` → TypeError

**Symptôme** : `load_plugins` échouait silencieusement.

**Cause** : Le registre appelle `plugin_class(plugin_config)`. Sans `__init__`, Python utilisait `object.__init__()` qui n'accepte pas d'arguments.

**Fix** : `WeatherPlugin` hérite de `BasePlugin` :
```python
from plugins.base_plugin.base_plugin import BasePlugin

class WeatherPlugin(BasePlugin):
    # BasePlugin fournit __init__(config), generate_settings_template(), cleanup()
    pass
```

### Bug #15 : "Update Now" bloqué sans playlist

**Symptôme** : Erreur 400 lors du clic sur "Update Now" sans playlist configurée.

**Fix** : Fallback — si pas de playlist, pousse directement `current_image.png` :
```python
@main_bp.route('/api/refresh_now', methods=['POST'])
def refresh_now():
    # Essayer la playlist active
    active_playlist = device_config.get_active_playlist()
    if active_playlist and active_playlist.get('plugins'):
        # ... logique normale ...
    else:
        # Fallback : pousser l'image courante
        with Image.open(device_config.current_image_file) as img:
            display_manager.display_image(img.copy())
        return jsonify({"success": True, "message": "Current image pushed to display"})
```

### Bug #16 : `alert()` bloquant pour les erreurs

**Fix** : Remplacement de tous les `alert()` par des toasts inline :
```javascript
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('visible'), 10);
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
```

### Redesign du Layout Designer (plugin météo)

**Problème** : L'ancien design ressemblait à un PowerPoint — blocs colorés criards, peu professionnel.

**Nouvelle approche** — design inspiré de Notion/Linear :
- Fond blanc/crème pour simuler l'e-ink
- Cadre de prévisualisation avec bordure sombre
- Blocs de zone avec **accent left-border** coloré (au lieu de fond coloré)
- Toggle switch CSS natif (pas de checkbox visible)
- Boutons taille S/M/L en style pill/segmented

```css
.zone-card {
    border-left: 4px solid var(--zone-accent);
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.eink-preview {
    background: #f5f2eb;
    border: 2px solid #2d2d2d;
    border-radius: 4px;
    aspect-ratio: 5/3;
}
```

### Image de démarrage

Remplacé le texte "E-InkPi" par un message accueillant :

```python
draw.text((400, 200), "Hello there!", fill=(40, 40, 40), anchor='mm', font=title_font)
draw.text((400, 260), "Your display is ready.", fill=(100, 100, 100), anchor='mm', font=sub_font)
draw.text((400, 320), f"Visit {hostname}.local or {ip_address}", fill=(130, 130, 130), anchor='mm', font=url_font)
```

---

## 12. Installation et désinstallation

### `sudo bash install/install.sh`

**Séquence d'exécution** :

```
1. parse_arguments          → Détection du flag -W (Waveshare)
2. check_permissions        → Vérification sudo
3. stop_service             → Arrêt du service si en cours
4. fetch_waveshare_driver   → (si -W) Téléchargement du driver
5. enable_interfaces        → Activation SPI + I2C dans config.txt
6. install_debian_dependencies → apt-get install
7. setup_zramswap_service   → (si Bookworm/OS 12) ZRAM swap
8. setup_earlyoom_service   → Protection OOM
9. install_src              → Symlink /usr/local/inkypi/src → repo/src
10. install_cli             → Scripts CLI
11. create_venv             → Python venv + pip install
12. install_executable      → Copie de l'exécutable dans /usr/local/bin
13. install_config          → Copie device.json (si inexistant)
14. update_config           → (si -W) Mise à jour display_type
15. install_app_service     → Installation service systemd
16. update_vendors.sh       → Mise à jour JS/CSS vendors
17. setup_firewall          → Configuration UFW
18. ask_for_reboot          → Proposition de redémarrage
```

### Configuration UFW (firewall)

```bash
setup_firewall() {
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp   comment 'SSH'
    ufw allow 80/tcp   comment 'HTTP'
    ufw allow 443/tcp  comment 'HTTPS'
    ufw --force enable
}
```

**Politique** :
- Tout le trafic entrant bloqué par défaut
- SSH (22), HTTP (80), HTTPS (443) autorisés
- Tout le trafic sortant autorisé (pour les API météo)

### `sudo bash install/uninstall.sh`

```
1. check_permissions    → Vérification sudo
2. confirm_uninstall    → Confirmation y/N
3. stop_service         → Arrêt du service
4. disable_service      → Désactivation + suppression du fichier .service
5. remove_files         → Suppression de /usr/local/inkypi + exécutable
6. remove_firewall      → Reset UFW + désactivation
```

La désinstallation ne touche pas au dépôt git source (`/home/pi/weather-station`).

### Service systemd

Fichier : `/etc/systemd/system/inkypi.service`

```ini
[Unit]
Description=E-InkPi Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/usr/local/inkypi/src
ExecStart=/usr/local/inkypi/venv_inkypi/bin/python inkypi.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Symlink** : `/usr/local/inkypi/src` → `/home/pi/weather-station/src`

Cela signifie que les modifications dans le dépôt git sont **immédiatement actives** sans réinstallation.

---

## 13. Décisions techniques — Récapitulatif

| Décision | Raison |
|----------|--------|
| Flask + Jinja2 | Léger, compatible Pi Zero 2 W, syntaxe simple |
| Waitress (WSGI prod) | Pure Python, multithread, sans dépendances C |
| Playwright pour screenshot | Rendu HTML complet avec CSS + JS |
| Cache 30min MeteoSwiss | API publique sans SLA, scan PLZ peut être lent |
| CartoDB tiles | OSM tiles bloquent sans header Referer |
| Nominatim geocoding | Gratuit, sans clé, données OSM précises |
| Nominatim zoom=16 | Seul niveau retournant les codes postaux suisses |
| ipapi.co pour géoloc IP | Plus fiable que KeyCDN, retourne aussi la timezone |
| systemd service | Auto-restart si crash, démarre au boot automatiquement |
| jQuery + Select2 local | Pas de dépendance CDN à l'exécution |
| Bootstrap 5 CDN (base.html) | Page boutons rarement visitée, poids acceptable |
| Polling 1s avec If-Modified-Since | Preview réactif sans surcharger le Pi Zero |
| Countdown côté JS + resync 30s | Décompte fluide sans polling serveur excessif |
| HTML5 Drag API natif | Pas de bibliothèque externe pour le réordonnage |
| UFW firewall | Protection minimale, faible impact CPU |
| ZRAM swap (Bookworm) | Playwright + Flask sur 512 MB RAM nécessite swap rapide |
| earlyoom | Évite les freezes complets si OOM sur Pi Zero |
| Symlink src vs copie | Les modifications git sont immédiatement live |
| Scan PLZ ±10 | Tous les NPA suisses ne sont pas dans la DB MeteoSwiss |

---

## 14. Bugs résolus — Récapitulatif complet

| # | Symptôme | Cause | Fix |
|---|----------|-------|-----|
| 1 | Icônes météo absentes | `{variable}` Python = set, pas string | `get_icon_path(var)` sans accolades |
| 2 | Erreur API Open-Meteo | `models=best_match` supprimé | Retrait du paramètre |
| 3 | Icônes prévisions = soleil | `weathercode` vs `weather_code` | Ajout underscore |
| 4 | Carte OSM "Referer required" | Politique tiles OSM | Passage à CartoDB |
| 5 | GPS silencieux sur HTTP | API géoloc nécessite HTTPS | Détection protocole + message |
| 6 | Crash démarrage prod | `device.json` absent | Création du fichier |
| 7 | 404 sur `image_modal.js` | Fichier référencé mais inexistant | Création du fichier |
| 8 | 404 sur `/settings/buttons` | Blueprint non enregistré | `app.register_blueprint(buttons_bp)` |
| 9 | AttributeError boutons | `set_config()` inexistant | Remplacement par `update_value()` |
| 10 | TemplateNotFound: base.html | Fichier non créé | Création `src/templates/base.html` |
| 11 | 404 jQuery/Select2 | Fichiers non présents | Téléchargement local |
| 12 | Image cassée au démarrage | `current_image.png` absent | Génération placeholder PIL |
| 13 | "Plugin not registered" | `plugin-info.json` wrong class | `"class": "WeatherPlugin"` |
| 14 | TypeError au chargement plugin | Pas de `__init__` | Héritage `BasePlugin` |
| 15 | "Update Now" → 400 sans playlist | Pas de fallback | Fallback push image courante |
| 16 | `alert()` bloquant | Mauvais UX | Toast inline 4s auto-dismiss |

---

## 15. API MeteoSwiss — Documentation technique

### Endpoint principal

```
GET https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz={PLZ6}
```

**Headers requis** :
```
User-Agent: MeteoSwissApp/2.5.1
Accept: application/json
```

### Format PLZ

| NPA | PLZ6 | Exemple |
|-----|------|---------|
| 1002 | 100200 | Lausanne |
| 1201 | 120100 | Genève |
| 3011 | 301100 | Berne |
| 8001 | 800100 | Zurich |
| 6003 | 600300 | Lucerne |
| 7000 | 700000 | Coire |

**Règle** : PLZ6 = `f"{npa:04d}00"`

### Structure de réponse complète

```json
{
  "currentWeather": {
    "time": "2026-03-20T14:00:00+01:00",
    "icon": 5,
    "iconV2": 5,
    "temperature": 12.3,
    "windDirection": 270,
    "windSpeed": 15.2,
    "gustPeak": 28.4,
    "precipitation": 0.0,
    "humidity": 68,
    "dewPoint": 5.8,
    "visibility": 28000,
    "uvIndex": 3
  },
  "forecast": [
    {
      "dayDate": "2026-03-20",
      "iconDay": 5,
      "iconV2Day": 5,
      "temperatureMax": 15,
      "temperatureMin": 8,
      "precipitation": 2.1,
      "precipitationMin": 0.5,
      "precipitationMax": 6.0,
      "windDirection": 270,
      "windSpeed": 18,
      "gustPeak": 32,
      "sunrise": "2026-03-20T06:42:00+01:00",
      "sunset": "2026-03-20T19:18:00+01:00"
    }
  ],
  "graph": {
    "start": "2026-03-20T00:00:00+01:00",
    "temperatureShade1h": [...],
    "temperatureMean1h": [...],
    "precipitation10m": [...],
    "precipitationMin10m": [...],
    "precipitationMax10m": [...],
    "windSpeed10m": [...],
    "windDirection10m": [...],
    "gustSpeed10m": [...],
    "sunriseDate": "2026-03-20T06:42:00+01:00",
    "sunsetDate": "2026-03-20T19:18:00+01:00"
  }
}
```

### Codes icônes et descriptions

| Code | Jour | Nuit (+100) | Description |
|------|------|-------------|-------------|
| 1 | ☀️ | 🌙 | Ensoleillé / Ciel clair |
| 2 | 🌤 | 🌤 | Légèrement nuageux |
| 3 | ⛅ | ⛅ | Partiellement nuageux |
| 5 | 🌥 | 🌥 | Nuageux |
| 8 | ☁️ | ☁️ | Très nuageux / Couvert |
| 14 | 🌦 | 🌦 | Pluie et soleil |
| 17 | ⛈ | ⛈ | Orage |
| 27 | 🌨 | 🌨 | Neige |
| 29 | ❄️ | ❄️ | Forte neige |
| 35 | 🌪 | 🌪 | Tempête |

Les fichiers SVG correspondants : `src/plugins/weather/icons/msw_{code}.svg`

---

## 16. Structure finale du projet

```
weather-station/
├── install/
│   ├── install.sh           # Installation complète (SPI, venv, service, UFW)
│   ├── uninstall.sh         # Désinstallation propre
│   ├── requirements.txt     # Dépendances Python (pip)
│   ├── debian-requirements.txt  # Dépendances système (apt)
│   ├── ws-requirements.txt  # Dépendances Waveshare optionnelles
│   ├── inkypi.service       # Fichier service systemd
│   ├── inkypi               # Exécutable shell wrapper
│   ├── config_base/
│   │   └── device.json      # Config par défaut (copié si absent)
│   └── update_vendors.sh    # Mise à jour JS/CSS vendors
├── src/
│   ├── inkypi.py            # Point d'entrée Flask
│   ├── config.py            # Gestionnaire device.json
│   ├── refresh_task.py      # Thread de refresh
│   ├── blueprints/
│   │   ├── main.py          # API principale + dashboard
│   │   ├── plugin.py        # CRUD plugins
│   │   ├── settings.py      # Paramètres device
│   │   ├── playlist.py      # Gestion playlists
│   │   └── buttons.py       # Mapping boutons GPIO
│   ├── plugins/
│   │   ├── base_plugin/
│   │   │   └── base_plugin.py
│   │   └── weather/
│   │       ├── plugin-info.json
│   │       ├── weather.py   # Provider logic + timezone + parsing MeteoSwiss
│   │       ├── settings.html
│   │       └── render/
│   │           ├── weather.html
│   │           └── weather.css
│   ├── display/
│   │   ├── display_manager.py
│   │   ├── inky_display.py
│   │   └── waveshare_epd/
│   ├── templates/
│   │   ├── base.html            # Layout commun (navbar admin)
│   │   ├── button_settings.html # Configuration boutons physiques
│   │   ├── inky.html            # Dashboard (preview image + watch interactif)
│   │   ├── live.html            # Watch temps réel / mode embarqué
│   │   ├── plugin.html          # Édition des plugins + "Update Display"
│   │   └── settings.html        # Paramètres de l'appareil
│   ├── static/
│   │   ├── icons/
│   │   ├── images/
│   │   │   └── current_image.png
│   │   ├── scripts/
│   │   │   ├── jquery.min.js
│   │   │   ├── select2.min.js
│   │   │   └── image_modal.js
│   │   └── styles/
│   │       ├── main.css
│   │       └── select2.min.css
│   ├── config/
│   │   ├── device.json
│   │   └── device_dev.json
│   └── utils/
│       └── app_utils.py     # generate_startup_image(), etc.
├── DEVLOG.md                # Journal technique par session
└── IMPLEMENTATION.md        # Ce document
```

---

## 17. Addendum — Watch interactif, météo polish et workflow boutons

### Watch interactif

Un mode **watch temps réel** a été ajouté au dashboard pour répondre au besoin "pas juste une image, mais une vraie montre".

- Nouvelle route Flask : `/live`
- Nouveau template : `src/templates/live.html`
- Le dashboard `src/templates/inky.html` propose maintenant un switch :
  - **Display Image** : aperçu PNG de l'écran e-ink
  - **Interactive Watch** : rendu navigateur en temps réel
- Le watch utilise la timezone de l'appareil, mémorise le thème, l'affichage des secondes et la face choisie (`analog`, `digital`, `word`)
- Chargement paresseux via iframe embarquée pour éviter du travail inutile tant que l'utilisateur reste sur l'aperçu image
- Correctifs de stabilité ajoutés ensuite :
  - mode `embed` allégé pour éviter une iframe trop chargée
  - redimensionnement du canvas basé sur la vraie carte du watch plutôt que sur le viewport brut
  - grille du word clock réalignée
  - persistance `localStorage` sécurisée
  - suppression du polling preview dupliqué côté dashboard

### Plugin météo — rendu plus professionnel

Le plugin météo a été repoli pour se rapprocher de la direction visuelle d'InkyPi : plus éditorial, plus lisible, plus "produit fini".

- **MeteoSwiss** devient le provider par défaut pour les nouvelles instances
- Le rendu `weather.html` a été entièrement refait :
  - header plus propre
  - hero section température + icône
  - grille de métriques avec icônes
  - bloc prévisions plus dense et plus lisible
  - badge source (`MeteoSwiss` / `Open-Meteo`)
- Les icônes **MeteoSwiss SVG** restent utilisées comme référence principale
- La timezone du rendu est maintenant respectée côté Python :
  - timezone de la localisation
  - ou timezone de l'appareil selon le réglage
- Si l'API MeteoSwiss ne retourne pas toute la structure attendue (graphique / prévisions), le plugin complète désormais les données via **Open-Meteo** tout en conservant l'habillage visuel MeteoSwiss
- Le réglage **moonPhase** est maintenant réellement consommé dans le rendu
- L'option OpenWeatherMap reste visible comme piste future mais est marquée **coming soon** pour éviter de guider vers un provider non pris en charge dans cette branche
- Le layout météo a ensuite été resserré pour coller davantage à la référence utilisateur :
  - ville centrée
  - grande température
  - colonnes de métriques compactes
  - courbe horaire plus douce
  - cartes forecast à bords fins et palette bleu/gris plus pro
- Un **Display Composer** a été ajouté dans les paramètres du plugin météo :
  - ajout de blocs texte
  - ajout de blocs image
  - déplacement visuel sur un canvas de preview
  - édition via inspecteur (taille, position, couleur, forme, alignement, opacité)
  - sauvegarde persistante dans les settings du plugin
  - rendu réel sur l'image météo générée, pas seulement dans le formulaire

### Workflow boutons / aperçu / mise à jour

Plusieurs irritants UX ont été corrigés dans le flux quotidien :

- Le bouton **Update Display** est maintenant visible sur `plugin.html`
- La page **Physical Buttons** est accessible depuis la navigation principale
- Le toast de sauvegarde des boutons utilisait les arguments du modal dans le mauvais ordre : corrigé
- L'action bouton physique **refresh** rafraîchissait auparavant le plugin suivant au lieu du plugin affiché : corrigé
- La configuration boutons est donc maintenant cohérente :
  - sauvegarde visible
  - navigation accessible
  - action refresh fidèle à son intitulé

### Vérifications effectuées

- `git diff --check` : OK
- Compilation Python des fichiers modifiés vers `/tmp` : OK
- Rendu Jinja2 du nouveau template météo : OK
- Vérification HTTP après redémarrage service :
  - `/` : `200`
  - `/settings` : `200`
  - `/plugin/weather` : `200`
  - `/live` : `200`
  - `/settings/buttons` : `200`
  - `/playlist` : `200`

### Polish UI web 2026

Un passage supplémentaire a été fait sur la couche UI partagée pour rapprocher l'interface des bonnes pratiques web actuelles :

- focus clavier plus visible sur boutons, liens, cartes et navigation
- tailles de cibles tactiles harmonisées autour d'un minimum confortable
- champs Bootstrap et champs custom alignés visuellement
- shell de page plus respirant avec marges plus stables
- modales plus robustes sur petits écrans
- suppression des `alert()` navigateur restants dans les vues principales au profit du modal/toast maison

### Installation / désinstallation

Le flux d'installation a été durci pour éviter les erreurs de nommage entre ancien et nouveau service :

- les scripts `install.sh`, `update.sh` et `uninstall.sh` utilisent maintenant le nom cohérent `inkypi`
- l'erreur de recherche du fichier `e-inkpi.service` a été corrigée
- l'écran de démarrage par défaut est réactivé à l'installation
- cet écran de bienvenue affiche :
  - `http://<hostname>.local`
  - `http://<ip-address>`
- la désinstallation nettoie maintenant aussi les anciens restes `e-inkpi` si présents
- la désinstallation évite de supprimer les fichiers de config du dépôt source lorsque l'installation repose sur un lien symbolique vers `src/`

### Météo par défaut

Le rendu météo par défaut a été repoli pour se rapprocher davantage de la maquette fournie par l'utilisateur :

- hiérarchie plus éditoriale
- header plus simple
- grande température centrale
- colonnes de métriques plus compactes
- cartes forecast allégées
- surcharge visuelle réduite par défaut

Le style d'icônes MeteoSwiss est désormais conservé aussi pour les écrans alimentés par **Open-Meteo**, afin d'éviter le retour à l'ancien pack d'icônes.

Deux réglages de thème ont aussi été ajoutés au plugin météo :

- couleur de fond globale
- couleur de texte globale

Vérification ciblée :
- rendu réel d'un écran météo `800x480` pour **Los Angeles** avec provider **Open-Meteo** : OK
- routes après redémarrage :
  - `/` : `200`
  - `/plugin/weather` : `200`
  - `/live` : `200`
  - `/settings` : `200`

### Ajustements récents du plugin météo

Le plugin météo a reçu un nouveau passage de simplification et de lisibilité :

- suppression de l'ancien bloc `Layout Designer` dans les settings météo pour éviter la confusion avec le vrai `Display Composer`
- conservation du `Display Composer` pour l'ajout de texte et d'images personnalisés
- cartes forecast 5 jours adoucies :
  - bordure visible
  - fond moins blanc et mieux intégré au thème
- meilleure lisibilité des textes sous le graphique horaire sur l'écran e-ink
- métriques météo renforcées visuellement :
  - labels plus lisibles
  - valeurs plus contrastées
  - icônes légèrement plus présentes
- bloc pression rendu plus clair dans le panneau météo courant
- pour MeteoSwiss, récupération systématique du complément Open-Meteo afin d'alimenter la pression et les métriques manquantes
- ajout d'un badge clair derrière les icônes météo pour qu'elles restent visibles sur les écrans plus sombres

Vérification ciblée :
- `/plugin/weather` : `200`
- `/` : `200`
- suppression confirmée des chaînes :
  - `Layout Designer`
  - `Drag to reorder zones`
  - `Live preview`
- compilation Python de `src/plugins/weather/weather.py` vers `/tmp` : OK
- `git diff --check` ciblé : OK

### Rendu de la watch interactive

La watch interactive du dashboard n'était au départ qu'un aperçu navigateur :

- elle s'affichait en iframe dans le web UI
- mais `Update Now` n'envoyait pas cette watch au display
- seule l'image statique courante ou un plugin de playlist pouvait être poussée à l'écran

Le flux a été corrigé :

- ajout d'un vrai endpoint serveur de rendu `live_watch`
- génération d'une image statique de la watch analogique / digitale / word depuis l'état courant
- le bouton dashboard change maintenant de libellé en mode watch :
  - `Update Now` en mode image
  - `Render Watch` en mode watch
- après rendu, l'image de watch devient bien `current_image.png` et peut être affichée sur l'écran

### Correctif de l'heure de la watch

Un décalage d'heure pouvait encore apparaître sur la watch rendue et dans la page interactive :

- le rendu statique dépendait encore de `new Date()` côté navigateur headless
- la page `/live` dépendait elle aussi de l'horloge du navigateur pour animer l'heure

Le flux a été fiabilisé :

- le serveur calcule maintenant un snapshot horaire timezone-aware
- ce snapshot est injecté dans `live_render.html` pour que l'image envoyée au display utilise l'heure exacte du Raspberry
- `/api/status` expose aussi l'heure serveur, l'offset et le timezone label
- la page `/live` se resynchronise désormais sur cette horloge serveur au lieu de dépendre de l'heure locale du navigateur
- l'affichage `Last display refresh` utilise maintenant un format cohérent avec le timestamp réellement enregistré

Vérification ciblée :
- `/` : `200`
- `/live` : `200`
- `/api/current_image` : `200`
- `/api/status` retourne bien :
  - `server_timezone: Europe/Zurich`
  - `server_time_iso` cohérent avec l'heure système
- `POST /api/render_live_watch` : OK
- `current_plugin_id: live_watch` après rendu : OK

### Notification d'update écran

Les actions d'update du display remontent maintenant explicitement l'heure de mise à jour :

- le bouton `Update Display` des plugins affiche une notification de succès avec l'heure réelle de mise à jour
- le bouton `Update Now` du dashboard affiche lui aussi `Screen updated at HH:MM`
- le rendu de la watch affiche `Watch rendered at HH:MM`
- l'action d'affichage depuis les playlists réutilise le même message horodaté

Les endpoints serveur renvoient désormais :

- `updated_at`
- `updated_at_display`
- `updated_at_long`
- `updated_timezone`

Vérification ciblée :
- `POST /api/refresh_now` : OK, retour avec `updated_at_display`
- `POST /api/render_live_watch` : OK, retour avec `updated_at_display`

### Ajustement final des profils couleur météo

Le rendu météo a été consolidé pour mieux supporter les fonds personnalisés, y compris les profils sombres et intermédiaires :

- le thème météo dérive maintenant automatiquement des couleurs de fond / texte sûres pour conserver un contraste lisible
- si l'utilisateur choisit une combinaison trop faible en contraste, la couleur de texte est sécurisée automatiquement
- les cartes principales météo et graphique ont maintenant une vraie forme de carte avec bordure et fond dérivé du thème
- les badges d'icônes métriques restent visibles même sur fond sombre
- l'affichage des métriques est recentré sur 4 informations principales :
  - `Sunrise`
  - `Wind`
  - `Pressure`
  - `Humidity`
- les sélecteurs de couleur de l'UI web ont été renforcés pour rester visibles en mode clair et sombre

Vérification ciblée :
- compilation Python de `src/plugins/weather/weather.py` vers `/tmp` : OK
- `git diff --check` ciblé : OK

### Ajustement d'espacement sur l'en-tête des plugins

L'en-tête partagé des pages plugin / settings a été retouché pour mieux respirer :

- le bouton `Back` a maintenant plus d'espace sous lui
- le bloc titre / icône plugin descend légèrement pour éviter l'effet tassé
- le correctif est appliqué via le style partagé, pas uniquement au plugin météo

Vérification ciblée :
- sweep des pages plugin : `200` pour tous les vrais plugins détectés
- `/settings` : `200`
- `/playlist` : `200`
- `/plugin/weather` : `200`

### Traduction des couleurs météo pour l'E-Ink

Le rendu météo a été recentré sur un mode normal clair, plus fidèle au visuel de référence :

- retour à la logique couleur météo plus simple et plus stable
- conservation d'une protection automatique de contraste si le texte devient trop faible
- valeurs par défaut météo fixées à :
  - fond `#ffffff`
  - texte `#111111`
- génération immédiate d'un nouvel écran météo clair pour remplacer l'ancien rendu sombre
- suppression des grands dégradés de fond et simplification des cartes en rectangles plus francs
- séparation plus nette entre :
  - mode clair : page blanche, texte sombre, cartes blanches bordées
  - mode noir : fond noir, texte clair, cartes et bordures simplifiées pour mieux coller au rendu panel
- durcissement du texte de support en mode clair :
  - date
  - labels métriques
  - valeurs secondaires
  - texte du graphique horaire
  - températures basses du forecast
- passe de netteté ciblée sur le rendu météo :
  - icônes SVG rendues plus nettes
  - texte Chromium moins flou
  - unsharp mask léger appliqué après capture HTML

Vérification ciblée :
- compilation Python de `src/plugins/weather/weather.py` vers `/tmp` : OK
- `/plugin/weather` : `200`
- `/` : `200`
- `POST /update_now` pour la météo : OK

### Réglage du rendu réel Spectra

Le dernier problème couleur ne venait plus du template météo lui-même, mais du chemin matériel Inky / Spectra :

- le rendu météo sombre produit maintenant un vrai fond noir dans `src/plugins/weather/weather.py`
- l'unsharp mask météo est désactivé pour les thèmes sombres afin d'éviter les halos gris qui se quantifient mal sur Spectra
- les valeurs matérielles par défaut ont été recentrées pour éviter les écrans brûlés / saturés :
  - `brightness` : `1.0`
  - `inky_saturation` : `0.0`
- ces valeurs ont été alignées dans :
  - `src/config/device.json`
  - `install/config_base/device.json`
  - `src/display/inky_display.py`
  - `src/blueprints/settings.py`
  - `src/templates/settings.html`

Vérification réelle après redémarrage :
- `inkypi.service` : `active`
- rendu météo sombre poussé via `/update_now` : OK
- rendu météo clair poussé via `/update_now` : OK
- échantillonnage du `current_image.png` :
  - mode sombre : fond et cartes à `(0, 0, 0)`
  - mode clair : fond à `(255, 255, 255)`, cartes en gris clair lisible

Limite connue de la session :
- impossible de faire un smoke test complet d'import **de tous les plugins** dans cet environnement shell nu, car l'interpréteur Python disponible ici n'a pas toutes les dépendances du projet (`psutil`, `pytz`, etc.). Sur le Raspberry avec l'environnement projet installé, ces imports sont pris en charge normalement.

---

*Documentation générée le 20 mars 2026 — Station Météo E-Ink sur Raspberry Pi Zero 2 W*
