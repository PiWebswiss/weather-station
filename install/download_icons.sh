#!/usr/bin/env bash
# =============================================================================
# download_icons.sh
# Downloads MeteoSwiss official SVG weather icons (codes 1-42 day, 101-142 night)
# from the official MeteoSwiss CDN, plus Meteocons SVG icons for OpenWeatherMap
# and OpenMeteo providers.
#
# Usage: sudo bash install/download_icons.sh
#        (called automatically by install.sh and update.sh)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICONS_DIR="$SCRIPT_DIR/../src/plugins/weather/icons"

MSW_BASE="https://www.meteoschweiz.admin.ch/static/resources/weather-symbols"
METEOCONS_BASE="https://raw.githubusercontent.com/basmilius/weather-icons/master/production/fill/svg"

ok=0
fail=0

download() {
  local url="$1" dest="$2" label="$3"
  if curl -sf --max-time 10 "$url" -o "$dest"; then
    echo "  ✓ $label"
    ok=$((ok + 1))
  else
    echo "  ✗ $label (skipped)" >&2
    fail=$((fail + 1))
  fi
}

# ── MeteoSwiss official icons (1–42 day, 101–142 night) ──────────────────────
echo "Downloading MeteoSwiss official weather symbol icons..."
for code in $(seq 1 42) $(seq 101 142); do
  download "$MSW_BASE/$code.svg" "$ICONS_DIR/msw_$code.svg" "msw_$code.svg"
done

# ── Meteocons icons for OWM / Open-Meteo providers ───────────────────────────
echo ""
echo "Downloading Meteocons SVG icons (for OpenWeatherMap / Open-Meteo)..."

declare -A ICON_MAP=(
  ["01d.svg"]="clear-day"
  ["01n.svg"]="clear-night"
  ["022d.svg"]="partly-cloudy-day"
  ["022n.svg"]="partly-cloudy-night"
  ["02d.svg"]="partly-cloudy-day"
  ["02n.svg"]="partly-cloudy-night"
  ["03d.svg"]="overcast-day"
  ["04d.svg"]="overcast"
  ["09d.svg"]="rain"
  ["10d.svg"]="drizzle"
  ["10n.svg"]="drizzle"
  ["11d.svg"]="thunderstorms-rain"
  ["13d.svg"]="snow"
  ["48d.svg"]="fog"
  ["50d.svg"]="fog"
  ["51d.svg"]="drizzle"
  ["53d.svg"]="rain"
  ["56d.svg"]="sleet"
  ["57d.svg"]="sleet"
  ["71d.svg"]="snow"
  ["73d.svg"]="snow"
  ["77d.svg"]="snow"
  # Moon phases
  ["newmoon.svg"]="moon-new"
  ["waxingcrescent.svg"]="moon-waxing-crescent"
  ["firstquarter.svg"]="moon-first-quarter"
  ["waxinggibbous.svg"]="moon-waxing-gibbous"
  ["fullmoon.svg"]="moon-full"
  ["waninggibbous.svg"]="moon-waning-gibbous"
  ["lastquarter.svg"]="moon-last-quarter"
  ["waningcrescent.svg"]="moon-waning-crescent"
  # Metric icons
  ["humidity.svg"]="humidity"
  ["wind.svg"]="wind"
  ["sunrise.svg"]="sunrise"
  ["sunset.svg"]="sunset"
  ["uvi.svg"]="uv-index"
  ["visibility.svg"]="mist"
  ["pressure.svg"]="barometer"
)

for target in "${!ICON_MAP[@]}"; do
  src="${ICON_MAP[$target]}"
  download "$METEOCONS_BASE/$src.svg" "$ICONS_DIR/$target" "$target"
done

echo ""
echo "Done: $ok downloaded, $fail skipped (existing PNG files used as fallback)."
