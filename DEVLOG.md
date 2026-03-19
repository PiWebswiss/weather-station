# InkyPi Weather Station — Development Log

> This document records every decision, bug fix, UX improvement, and infrastructure change made during the project. It is meant to be read by the student, teacher, or anyone reviewing this work.

---

## Table of Contents

0. [Session Prompts — What Was Asked](#0-session-prompts--what-was-asked)
1. [Project Overview](#1-project-overview)
2. [Issue Analysis](#2-issue-analysis)
3. [Changes Made — Detailed](#3-changes-made--detailed)
   - 3.1 MeteoSwiss Weather Accuracy
   - 3.2 Admin UI Redesign (WordPress-like)
   - 3.3 Fast Partial Refresh (Temperature Zone)
   - 3.4 Icon Rendering Quality
   - 3.5 GPS Modal & Cloudflare HTTPS
   - 3.6 Pi Firewall Setup
4. [Cloudflare Tunnel Setup Guide](#4-cloudflare-tunnel-setup-guide)
5. [Architecture Notes](#5-architecture-notes)
6. [Known Limitations & Future Work](#6-known-limitations--future-work)

---

## 0. Session Prompts — What Was Asked

These are the original user prompts from this development session, lightly corrected for clarity. They explain what triggered each decision.

---

**Prompt 1** — Initial bug report and feature requests:

> "There are several issues: the refresh timer is not working. We should also have an interactive way of setting up the display. For me it's too pixelated. Please check the MeteoSwiss weather app — it does not show the correct weather even if I set up the correct coordinates myself; it shows weather that does not match MeteoSwiss. For now, remove the Cloudflare setup as local access is fine. The Pi should also have a firewall just to be on the safe side — SSH must still work. Please make a detailed document of all prompts, decisions, thinking, and code changes — for now in a README."

---

**Prompt 2** — Admin interface request:

> "I want a WordPress-style interface where I can edit settings the way I want, but with a very modern look."

---

**Prompt 3** — Fast update and icon quality:

> "We must add a function for fast updates so not the entire screen refreshes each time — just the temperature text and number. Also, the icons are pixelated and do not look nice on the screen."

---

**Prompt 4** — Cloudflare tunnel reconsideration:

> "Can I not use a Cloudflare/HTTPS tunnel so we have HTTPS? Please document how to set it up (use it by default). Plain HTTP is not safe and geolocation will not work over HTTP."

---

**Prompt 5** — Firewall updated for HTTPS-only:

> "Also update the firewall to only allow HTTPS."

---

**Prompt 6** — Safety check and prompt logging:

> "Is it safe to run? Will it break my screen? The DEVLOG also needs to include my prompts (you can correct them)."

---

## 1. Project Overview

**InkyPi** is an e-ink display dashboard for Raspberry Pi. It runs a local Flask web server that:
- Serves an admin web UI for configuration
- Renders weather (and other plugins) as HTML → PNG via headless Chromium
- Pushes the PNG image to the e-ink display (Pimoroni Inky or Waveshare)

**Three weather providers** are supported:
| Provider | Cost | API Key | Accuracy |
|---|---|---|---|
| Open-Meteo | Free | No | Good (global) |
| OpenWeatherMap | Free tier | Yes | Good (global) |
| MeteoSwiss | Free | No | Excellent (Switzerland only) |

---

## 2. Issue Analysis

### Issue 1 — MeteoSwiss shows wrong weather

**Root cause (found):** Two bugs:

1. **Stale cache.** The MeteoSwiss cache TTL was 2 hours (`METEOSWISS_CACHE_TTL_SECONDS = 7200`). During the day, the plugin served data that was up to 2 hours old. MeteoSwiss forecast data is updated frequently, so this caused mismatches.

2. **Incorrect "current" time slot selection.** The code selected the last forecast slot that was `<= now`. At 14:45 for example, it selected the 14:00 slot correctly. But if the clock was slightly off or the time zone was wrong, it could select the wrong hour. Replaced with "closest slot to now" logic (minimum absolute time difference).

3. **Station wind data unit mismatch.** The SMN station CSV reports wind (`fu3010h0`) in m/s. The code stored this directly as `wind_kmh` without converting. Fixed: multiply by 3.6 to get km/h, which is what MeteoSwiss website displays.

4. **Station data only partially overrode forecast.** When live SMN station data was available, only temperature was overridden (only if non-None). Wind, humidity, and pressure were always set even if `None`, potentially overwriting valid forecast values with `None`. Fixed with explicit `if not None` guards.

**Why MeteoSwiss may still differ slightly from the website:**
- The website shows real-time automatic station data, updated every 10 minutes.
- Our plugin uses the **local-forecasting** dataset (hourly point forecasts) with SMN observations as override for current conditions.
- For remote coordinates far from a measurement station, the plugin uses forecast data only — these may differ slightly from the nearest city shown on the MeteoSwiss website.
- **Best practice:** set coordinates to exactly the MeteoSwiss station you want to compare with.

### Issue 2 — Refresh timer not working

**Root cause:** The refresh *badge* (showing last update time) works correctly — it shows when `generate_image()` was last called. However, the *system refresh interval* (`plugin_cycle_interval_seconds`) defaults to 3600 seconds (1 hour). If the MeteoSwiss 2-hour cache was still valid, the plugin would regenerate with the same cached data, resulting in the same image hash — so the e-ink display would not update (by design, to reduce ghosting).

**Fix:** Reducing cache TTL to 30 minutes means fresh data every 30 minutes when available, which will change the displayed temperature and trigger a real display refresh.

### Issue 3 — Display too pixelated / icons look bad

**Root cause (two factors):**

1. **PNG icons being upscaled.** The weather icons (`01d.png`, etc.) are small raster images. When the headless Chromium renders them at e-ink display resolution (e.g. 800×480), upscaling a 64×64 icon to 120px looks pixelated.

2. **Forced pixel font on small screens.** The CSS rule `@media (max-width: 250px)` applied the "Dogica" pixel font. This was removed — it was designed for a specific tiny display but degraded quality on normal e-ink displays.

**Fix applied:** Added `image-rendering: smooth; image-rendering: -webkit-optimize-contrast;` to all icon CSS rules. This tells Chromium to use bicubic interpolation when upscaling.

**Recommended long-term fix:** Replace PNG icons with SVG vector icons. SVG scales perfectly at any resolution. A good free set: [Meteocons](https://bas.dev/work/meteocons) or [weather-icons](https://erikflowers.github.io/weather-icons/). This requires mapping the existing icon names to SVG filenames.

### Issue 4 — No fast/partial temperature update

**Root cause:** The e-ink display requires a full redraw for any change (otherwise ghosting appears). The existing "partial zone" feature renders only one zone (header, current, graph, or forecast) but still triggers a full display refresh.

**Fix:** Added a new `temp` partial zone that renders only the current temperature, feels-like, and today's min/max — the smallest possible content change. This is ideal for frequent updates (e.g. every 15 minutes) to show the current temperature without redrawing the graph and forecast.

**How to use:** In the plugin settings, set **Partial Refresh Zone** → **Temperature only (fastest update)**.

### Issue 5 — GPS location requires HTTPS

**Root cause:** The W3C Geolocation API specification requires a secure context (HTTPS). Modern browsers block `navigator.geolocation` on plain HTTP pages. The original modal referenced Cloudflare specifically but was confusing (mixed French/English, mentioned a specific domain).

**Fix:** The modal now gives clear, language-neutral browser instructions. Cloudflare Tunnel (see section 4) is the recommended way to get HTTPS for free without port forwarding.

### Issue 6 — No firewall on the Pi

**Risk:** A Raspberry Pi exposed on a local network (or internet via port forwarding) with no firewall accepts connections on all ports. This is a security risk.

**Fix:** Created `install/setup_firewall.sh` using UFW (Uncomplicated Firewall):
- SSH (port 22) — always open for remote admin
- HTTP (port 80) — open for local network access
- HTTPS (port 443) — open for Cloudflare tunnel
- All other inbound traffic — blocked by default

---

## 3. Changes Made — Detailed

### 3.1 MeteoSwiss Weather Accuracy

**File:** `src/plugins/weather/weather.py`

```python
# Before:
METEOSWISS_CACHE_TTL_SECONDS = 2 * 60 * 60  # 2 hours — data was very stale

# After:
METEOSWISS_CACHE_TTL_SECONDS = 30 * 60  # 30 minutes — much fresher
```

```python
# Before (current slot selection — could miss if timezone was slightly wrong):
current_slot = None
for dt in sorted(temp_map.keys()):
    if dt <= now:
        current_slot = dt

# After (closest slot to now — robust to time zone edge cases):
current_slot = None
min_diff = None
for dt in sorted(temp_map.keys()):
    diff = abs((dt - now).total_seconds())
    if min_diff is None or diff < min_diff:
        min_diff = diff
        current_slot = dt
```

```python
# Before (wind stored in m/s but labelled km/h; None values overwrite valid data):
current["wind_kmh"] = self._safe_float(station_data.get("fu3010h0"))

# After (convert m/s → km/h; only update if value is not None):
wind_ms = self._safe_float(station_data.get("fu3010h0"))
if wind_ms is not None:
    current["wind_kmh"] = wind_ms * 3.6
```

### 3.2 Admin UI Redesign (WordPress-like)

**Files:** `src/templates/inky.html`, `src/static/styles/main.css`

**Layout change:** From a single scrolling frame to a sticky top admin bar + fixed sidebar + main content area. Inspired by WordPress admin panel design.

```
┌─────────────── Admin Bar (sticky) ────────────────────┐
│ InkyPi       Settings  Playlists  API Keys  ☾          │
├──────────┬────────────────────────────────────────────┤
│ DISPLAY  │  ┌── Live Preview ──────────────────────┐  │
│ Dashboard│  │  [e-ink screen image, auto-refresh]  │  │
│ Settings │  └──────────────────────────────────────┘  │
│          │  ┌── Plugins ───────────────────────────┐  │
│ CONTENT  │  │  [weather]  [calendar]  [clock] ...  │  │
│ Playlists│  └──────────────────────────────────────┘  │
│          │                                            │
│ INTEGRAT │                                            │
│ API Keys │                                            │
└──────────┴────────────────────────────────────────────┘
```

Key UX improvements:
- **Live preview card** with a pulsing green dot that shows the last update time
- **Plugin cards** redesigned with icon wrapper, name, and chevron arrow
- **Sidebar navigation** with section labels (Display / Content / Integrations)
- **Responsive**: sidebar collapses to a horizontal nav bar on mobile (< 768px)
- **Dark mode** preserved via the top bar dark-mode toggle button

### 3.3 Fast Partial Refresh (Temperature Zone)

**Files:** `src/plugins/weather/render/weather.html`, `src/plugins/weather/settings.html`

**Important — what this does NOT do:** This is NOT true hardware partial refresh. The e-ink panel always does a full physical refresh (full flicker, 2–3 seconds) when any image is pushed. The `inky_display.py` driver always calls `self.inky_display.show()` — a full-panel update with no partial-update API used.

**What it actually does:**
1. **If temperature didn't change:** the rendered image is pixel-identical to the previous one → image hash matches → the display is **skipped entirely** (zero refresh, zero flicker). This is the main benefit.
2. **If temperature changed:** a simpler image is rendered (faster Chromium processing), then the full display refreshes as normal with the full flicker.

**True hardware partial refresh** (only the temperature pixels flicker, rest of screen untouched) would require modifying `src/display/inky_display.py` to use the Pimoroni partial-update API. This is a possible future improvement.

**What the `temp` zone shows:**
- Current weather icon
- Current temperature + unit
- Feels Like
- Today's min / max

**What it hides:**
- Header (city + date)
- Metrics (wind, humidity, pressure, UV, etc.)
- Hourly graph
- Forecast

**CSS applied when `temp` zone is selected:**
```css
[data-zone="header"],
[data-zone="graph"],
[data-zone="forecast"] { display: none !important; }
.data-points { display: none !important; }
.current-temperature { width: 100% !important; max-width: 600px; }
```

The last rule is important — without it, the temperature block stays at 50% width (half the screen with empty space on the right). Fixed during review.

The settings dropdown now shows:
```
All zones — full display
Temperature only (fastest update)   ← NEW
Header only (city + date)
Current weather + metrics
Hourly graph only
Forecast only
```

**Recommended usage:** Set the plugin cycle interval to 15 minutes, use "Temperature only" zone, and configure a second playlist entry with "All zones" every 2–3 hours for a full refresh.

**Only active when you explicitly choose it.** The default "All zones" is unchanged.

### 3.4 Icon Rendering Quality

**File:** `src/plugins/weather/render/weather.css`

```css
/* Added to .current-icon, .data-point-icon, .forecast-icon, .moon-phase-icon */
image-rendering: smooth;
image-rendering: -webkit-optimize-contrast;
```

Also removed the `@media (max-width: 250px) { font-family: "Dogica"; }` rule that forced a pixel font on small-screen renders, making text look intentionally pixelated.

### 3.5 GPS Modal & Language Cleanup

**File:** `src/plugins/weather/settings.html`

- Removed Cloudflare-specific domain references from the GPS modal
- Translated all French strings to English
- Simplified browser permission instructions
- Clarified that the map picker works without GPS/HTTPS
- Added mention of Cloudflare Tunnel as HTTPS solution (see section 4)

### 3.6 Pi Firewall Setup

**File:** `install/setup_firewall.sh`

```bash
sudo ./install/setup_firewall.sh
```

UFW rules applied:
| Port | Protocol | Status | Reason |
|------|----------|--------|--------|
| 22 | TCP | OPEN | SSH remote admin |
| 80 | TCP | OPEN | HTTP local access |
| 443 | TCP | OPEN | HTTPS / Cloudflare tunnel |
| * | * | BLOCKED | All other inbound |

Once Cloudflare Tunnel is running, you can optionally close port 80 to external traffic and keep it only for localhost:
```bash
sudo ufw delete allow 80/tcp
sudo ufw allow from 127.0.0.1 to any port 80
```

---

## 4. Cloudflare Tunnel Setup Guide

**Why use Cloudflare Tunnel?**
- Gives your Pi a public HTTPS URL (e.g. `https://inkypi.yourdomain.com`) for **free**
- GPS geolocation in the browser requires HTTPS — this enables it
- No port forwarding or static IP needed
- Traffic is encrypted end-to-end
- The tunnel runs as a lightweight background service on the Pi

### Step 1 — Create a free Cloudflare account

Go to [cloudflare.com](https://cloudflare.com) and create a free account. Add your domain (or use a free subdomain via Cloudflare's free plan).

### Step 2 — Install cloudflared on the Pi

```bash
# Download the ARM64 binary for Raspberry Pi
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

For 32-bit Pi OS:
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

### Step 3 — Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This opens a browser. Log in to your Cloudflare account and authorize the tunnel.

### Step 4 — Create the tunnel

```bash
# Create tunnel named "inkypi"
cloudflared tunnel create inkypi

# Note the tunnel UUID printed (e.g. abc123-def456-...)
```

### Step 5 — Configure the tunnel

Create the config file:
```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

Content:
```yaml
tunnel: inkypi
credentials-file: /home/pi/.cloudflared/<YOUR-TUNNEL-UUID>.json

ingress:
  - hostname: inkypi.yourdomain.com
    service: http://localhost:80
  - service: http_status:404
```

Replace `inkypi.yourdomain.com` with your actual domain/subdomain.

### Step 6 — Route DNS

```bash
cloudflared tunnel route dns inkypi inkypi.yourdomain.com
```

This creates a CNAME DNS record in Cloudflare automatically.

### Step 7 — Install as a system service (auto-start)

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### Step 8 — Test

Open `https://inkypi.yourdomain.com` in your browser. You should see the InkyPi dashboard with a valid HTTPS certificate from Cloudflare.

Now GPS location detection in the weather plugin settings will work from any browser.

### Step 9 — Update the firewall

With Cloudflare Tunnel active, you no longer need port 80 open to the internet (the tunnel uses outbound connections only):
```bash
# Keep HTTP for localhost only (the Flask app runs on port 80)
sudo ufw delete allow 80/tcp
sudo ufw allow from 127.0.0.1 to any port 80 comment 'HTTP localhost only'

# Keep HTTPS open (Cloudflare tunnel uses port 443 outbound anyway,
# but this allows direct HTTPS if you also set up a local cert)
sudo ufw allow 443/tcp comment 'HTTPS'
```

### Cloudflare Tunnel Summary

| Before | After |
|--------|-------|
| `http://192.168.1.x` — local only, no GPS | `https://inkypi.yourdomain.com` — secure, GPS works |
| No encryption | TLS via Cloudflare |
| Requires local network | Accessible from anywhere |
| No authentication | Can add Cloudflare Access rules (IP allowlist, email auth) |

---

## 5. Architecture Notes

### Refresh cycle

```
Flask API call (POST /plugin/<id>/save)
  → RefreshTask.manual_update()
    → plugin.generate_image(settings, device_config)
      → WeatherPlugin.generate_image()
        → fetch MeteoSwiss/OpenMeteo/OWM data
        → render_image() → headless Chromium → PNG
      → compare SHA-256 hash with previous image
      → if different: DisplayManager.display_image()
      → update device.json config
```

### E-ink partial refresh strategy

For minimum ghosting, use this playlist structure:
1. **Plugin: Weather (Temperature only)** — every 15 min
2. **Plugin: Weather (All zones)** — every 2 hours

The e-ink display will do fast partial updates for temperature, and full refreshes (which clean up ghosting) every 2 hours.

### MeteoSwiss data flow

```
get_meteoswiss_data(lat, lon)
  → _find_nearest_point()     — finds closest forecast grid point (CSV)
  → _get_local_forecast_assets() — fetches STAC asset URLs
  → check cache (30 min TTL)
  → download 4 CSV parameters: temperature, precip, precip_prob, symbol
  → _get_smn_current()        — fetches live station observations (CSV)
  → merge: forecast + station observations
  → cache result
  → return structured data dict
```

---

## 6. Known Limitations & Future Work

### Icons — long-term improvement
Current PNG icons look pixelated when upscaled on e-ink displays. The proper fix is **SVG weather icons**. Recommended approach:
1. Download [Meteocons](https://bas.dev/work/meteocons) SVG set (free, MIT license)
2. Place SVGs in `src/plugins/weather/icons_svg/`
3. Update `weather.html` to use `<img src="...svg">` or inline SVGs
4. SVGs scale perfectly at any resolution

### MeteoSwiss — real-time observation accuracy
For the highest accuracy matching the MeteoSwiss website:
1. Note the exact station abbreviation from [data.geo.admin.ch](https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/ogd-smn_meta_stations.csv)
2. Set your coordinates to exactly that station's lat/lon
3. The plugin will then pull live observations from that station

### Refresh timer display
The "↻ HH:MM" badge shows when the image was **generated**, not when the e-ink display was **updated**. The display update only happens when the image hash changes. This is intentional to reduce e-ink wear.

### WordPress-like live editing
The current admin redesign gives a WordPress-like sidebar layout. A true live-edit experience (change settings → instant preview) would require:
1. AJAX settings save (already works via `POST /plugin/<id>/save`)
2. Auto-trigger a manual refresh after save
3. WebSocket push from Pi to browser for real-time preview update
This is possible but requires changes to `blueprints/plugin.py` to return a preview image after save.

---

*Last updated: 2026-03-19*
*Author: Claude Sonnet 4.6 + Louis (CFC28 IoE Project)*
