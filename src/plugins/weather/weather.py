"""
Weather plugin — fetches data from Open-Meteo and renders the e-ink weather
display via weather.html, then returns a PIL Image via Chromium headless.
"""
from __future__ import annotations

import json
import os
import datetime
import re
import pytz
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import ImageFilter


# ---------------------------------------------------------------------------
# Helper: moon phase
# ---------------------------------------------------------------------------

def _moon_phase(dt: datetime.date) -> tuple[str, str]:
    """Return (emoji, name) for a rough moon-phase calculation."""
    known_new = datetime.date(2000, 1, 6)
    diff = (dt - known_new).days % 29
    phases = [
        (0,  "🌑", "New Moon"),
        (4,  "🌒", "Waxing Crescent"),
        (8,  "🌓", "First Quarter"),
        (12, "🌔", "Waxing Gibbous"),
        (15, "🌕", "Full Moon"),
        (19, "🌖", "Waning Gibbous"),
        (23, "🌗", "Last Quarter"),
        (27, "🌘", "Waning Crescent"),
    ]
    icon, name = phases[-1][1], phases[-1][2]
    for threshold, ph_icon, ph_name in phases:
        if diff <= threshold:
            icon, name = ph_icon, ph_name
            break
    return icon, name


_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
_MOON_PHASE_ASSETS = {
    "New Moon": "newmoon.png",
    "Waxing Crescent": "waxingcrescent.png",
    "First Quarter": "firstquarter.png",
    "Waxing Gibbous": "waxinggibbous.png",
    "Full Moon": "fullmoon.png",
    "Waning Gibbous": "waninggibbous.png",
    "Last Quarter": "lastquarter.png",
    "Waning Crescent": "waningcrescent.png",
}


def _asset_path(filename: str | None) -> str | None:
    """Return a file:// path for a plugin asset if it exists."""
    if not filename:
        return None
    full = os.path.join(_ICON_DIR, filename)
    if os.path.exists(full):
        return f"file://{full}"
    return None


def _moon_phase_asset(name: str) -> str | None:
    """Return an icon path for the given moon phase name."""
    return _asset_path(_MOON_PHASE_ASSETS.get(name))


def _safe_timezone(name: str | None) -> pytz.BaseTzInfo:
    """Resolve a timezone name with a safe UTC fallback."""
    try:
        return pytz.timezone(name or "UTC")
    except Exception:
        return pytz.UTC


def _resolve_display_timezone(provider: str, raw_data: dict, plugin_settings: dict, device_config) -> str:
    """Resolve the timezone used on the rendered display."""
    preference = plugin_settings.get("weatherTimeZone", "locationTimeZone")
    if preference == "localTimeZone":
        return device_config.get_config("timezone", default="UTC")
    if provider == "MeteoSwiss":
        return "Europe/Zurich"
    return raw_data.get("timezone") or device_config.get_config("timezone", default="UTC")


def _convert_iso_time(value: str, source_timezone: str, target_timezone: str) -> str:
    """Convert an ISO-like time string between timezones and return HH:MM."""
    if not value:
        return "—"
    try:
        dt = datetime.datetime.fromisoformat(value)
        source_tz = _safe_timezone(source_timezone)
        target_tz = _safe_timezone(target_timezone)
        if dt.tzinfo is None:
            dt = source_tz.localize(dt)
        else:
            dt = dt.astimezone(source_tz)
        return dt.astimezone(target_tz).strftime("%H:%M")
    except Exception:
        if "T" in value:
            return value.split("T", 1)[1][:5]
        return value[:5] if len(value) >= 5 else value


def _format_visibility(value) -> str:
    """Format visibility values into a compact human-readable string."""
    if value in (None, "", "—"):
        return "—"
    try:
        meters = float(value)
    except (TypeError, ValueError):
        return str(value)

    if meters >= 10000:
        return "> 10 km"
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{int(meters)} m"


def _format_display_date(dt: datetime.datetime) -> str:
    """Return a friendly header date."""
    return dt.strftime("%A, %B %d")


def _temperature_unit_symbol(units: str) -> str:
    """Return the compact temperature unit symbol."""
    if units == "imperial":
        return "F"
    if units == "standard":
        return "K"
    return "C"


def _convert_temperature(value, units: str):
    """Convert a Celsius value into the configured temperature unit."""
    if not isinstance(value, (int, float)):
        return value
    if units == "imperial":
        return round((value * 9 / 5) + 32)
    if units == "standard":
        return round(value + 273.15)
    return round(value)


def _convert_wind_speed(value, units: str):
    """Convert a km/h wind speed into the configured unit."""
    if not isinstance(value, (int, float)):
        return value
    if units == "imperial":
        return round(value * 0.621371, 1)
    return round(value)


def _location_label_from_address(address: dict) -> str | None:
    """Extract a compact location label from a reverse-geocoded address."""
    if not address:
        return None
    for key in ("city", "town", "village", "municipality", "hamlet", "county"):
        value = address.get(key)
        if value:
            return value
    return None


def _path_to_file_url(path: str | None) -> str | None:
    """Convert an absolute file path into a Chromium-friendly file:// URL."""
    if not path or not isinstance(path, str):
        return None
    if path.startswith(("file://", "http://", "https://", "data:")):
        return path
    if os.path.exists(path):
        return f"file://{path}"
    return None


def _safe_json_list(raw_value) -> list:
    """Parse a JSON list safely."""
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _clamp_float(value, minimum: float, maximum: float, default: float) -> float:
    """Parse and clamp a float value."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, numeric))


def _clamp_int(value, minimum: int, maximum: int, default: int) -> int:
    """Parse and clamp an integer value."""
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, numeric))


def _sanitize_color(value: str | None, default: str) -> str:
    """Allow only simple safe color values for user-configurable overlays."""
    if not value or not isinstance(value, str):
        return default
    cleaned = value.strip()
    if cleaned == "transparent":
        return "transparent"
    if re.fullmatch(r"#[0-9a-fA-F]{6}", cleaned):
        return cleaned
    if re.fullmatch(r"#[0-9a-fA-F]{3}", cleaned):
        return cleaned
    return default


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Convert a hex color into an RGB tuple."""
    cleaned = value.lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB tuple back to a hex color."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix_hex(color_a: str, color_b: str, weight_a: float) -> str:
    """Mix two hex colors with a given weight for the first color."""
    weight = max(0.0, min(1.0, float(weight_a)))
    rgb_a = _hex_to_rgb(color_a)
    rgb_b = _hex_to_rgb(color_b)
    mixed = tuple(
        round((channel_a * weight) + (channel_b * (1 - weight)))
        for channel_a, channel_b in zip(rgb_a, rgb_b)
    )
    return _rgb_to_hex(mixed)


def _relative_luminance(color: str) -> float:
    """Return WCAG relative luminance for a hex color."""
    def _channel(value: int) -> float:
        normalized = value / 255
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    red, green, blue = _hex_to_rgb(color)
    r = _channel(red)
    g = _channel(green)
    b = _channel(blue)
    return (0.2126 * r) + (0.7152 * g) + (0.0722 * b)


def _contrast_ratio(color_a: str, color_b: str) -> float:
    """Return the contrast ratio between two hex colors."""
    luminance_a = _relative_luminance(color_a)
    luminance_b = _relative_luminance(color_b)
    lighter = max(luminance_a, luminance_b)
    darker = min(luminance_a, luminance_b)
    return (lighter + 0.05) / (darker + 0.05)


def _resolve_theme_colors(plugin_settings: dict) -> dict:
    """Build a small derived theme for the weather template."""
    paper = _sanitize_color(plugin_settings.get("weatherBackgroundColor"), "#ffffff")
    requested_ink = _sanitize_color(plugin_settings.get("weatherTextColor"), "#111111")
    is_dark_paper = _relative_luminance(paper) < 0.32
    fallback_ink = "#f5f3ef" if is_dark_paper else "#111111"
    ink = requested_ink if _contrast_ratio(paper, requested_ink) >= 3.8 else fallback_ink

    if is_dark_paper:
        paper = "#000000"
        paper_soft = "#000000"
        line = "#f2f2f2"
        line_soft = "#c9c9c9"
        panel_soft = "#000000"
        panel = "#000000"
        panel_strong = "#000000"
        icon_badge = "#ffffff"
        icon_badge_line = "#1a1a1a"
    else:
        paper = _mix_hex(paper, "#ffffff", 0.14)
        paper_soft = paper
        line = _mix_hex("#000000", paper, 0.34)
        line_soft = _mix_hex("#000000", paper, 0.18)
        panel_soft = _mix_hex(paper, "#edf0f2", 0.42)
        panel = _mix_hex(paper, "#eef1f4", 0.32)
        panel_strong = _mix_hex(paper, "#e6eaee", 0.26)
        icon_badge = "#ffffff"
        icon_badge_line = _mix_hex("#000000", paper, 0.22)

    return {
        "theme_paper": paper,
        "theme_paper_soft": paper_soft,
        "theme_ink": ink,
        "theme_ink_soft": _mix_hex(ink, paper, 0.86 if not is_dark_paper else 0.78),
        "theme_ink_muted": _mix_hex(ink, paper, 0.74 if not is_dark_paper else 0.64),
        "theme_line": line,
        "theme_line_soft": line_soft,
        "theme_panel_soft": panel_soft,
        "theme_panel": panel,
        "theme_panel_strong": panel_strong,
        "theme_icon_badge": icon_badge,
        "theme_icon_badge_line": icon_badge_line,
        "theme_mode": "dark" if is_dark_paper else "light",
    }


def _parse_custom_overlay_blocks(plugin_settings: dict) -> list[dict]:
    """Parse user-authored text/image overlay blocks for the weather display."""
    raw_blocks = _safe_json_list(plugin_settings.get("customOverlayConfig"))
    parsed_blocks: list[dict] = []

    for index, raw_block in enumerate(raw_blocks):
        if not isinstance(raw_block, dict):
            continue

        block_type = str(raw_block.get("type") or "").strip().lower()
        if block_type not in {"text", "image"}:
            continue

        block_id = str(raw_block.get("id") or f"overlay_{index}").strip()
        image_key = str(raw_block.get("imageKey") or f"designer_image_{block_id}").strip()
        image_src = _path_to_file_url(plugin_settings.get(image_key)) if block_type == "image" else None

        if block_type == "image" and not image_src:
            continue

        parsed_blocks.append({
            "id": block_id,
            "type": block_type,
            "name": str(raw_block.get("name") or ("Text block" if block_type == "text" else "Image block")).strip()[:48],
            "x": _clamp_float(raw_block.get("x"), 0, 94, 8),
            "y": _clamp_float(raw_block.get("y"), 0, 92, 12),
            "width": _clamp_float(raw_block.get("width"), 6, 72, 24 if block_type == "text" else 18),
            "height": _clamp_float(raw_block.get("height"), 6, 62, 10 if block_type == "text" else 18),
            "font_size": _clamp_int(raw_block.get("fontSize"), 10, 56, 22),
            "text": str(raw_block.get("text") or "").strip()[:220],
            "text_color": _sanitize_color(raw_block.get("textColor"), "#4e5e7d"),
            "background_color": _sanitize_color(raw_block.get("backgroundColor"), "transparent"),
            "style": (
                raw_block.get("style")
                if raw_block.get("style") in {"none", "card", "pill"}
                else "card"
            ),
            "text_align": (
                raw_block.get("align")
                if raw_block.get("align") in {"left", "center", "right"}
                else "left"
            ),
            "fit": raw_block.get("fit") if raw_block.get("fit") in {"contain", "cover"} else "contain",
            "opacity": _clamp_float(raw_block.get("opacity"), 0.2, 1, 1),
            "image_key": image_key,
            "image_src": image_src,
            "z_index": 30 + index,
        })

    return parsed_blocks


# ---------------------------------------------------------------------------
# Helper: simple SVG bar-chart for hourly temperatures
# ---------------------------------------------------------------------------

def _build_hourly_svg(hours: list[dict], width: int = 780, height: int = 92, palette: dict | None = None) -> str:
    """Build a soft hourly temperature area chart from a list of {time, temp} dicts."""
    palette = palette or {}
    theme_paper = palette.get("theme_paper", "#fffdfa")
    theme_ink = palette.get("theme_ink", "#54617a")
    theme_ink_soft = palette.get("theme_ink_soft", "#6f7f94")
    theme_line = palette.get("theme_line", "#d6e0ec")
    theme_line_soft = palette.get("theme_line_soft", "#edf2f7")
    chart_line = _mix_hex(theme_ink, theme_paper, 0.76)
    chart_label = _mix_hex(theme_ink, theme_paper, 0.94)
    chart_value = _mix_hex(theme_ink, theme_paper, 0.98)

    clean_hours = []
    for hour in hours:
        temp = hour.get("temp")
        if isinstance(temp, (int, float)):
            clean_hours.append({
                "time": hour.get("time", ""),
                "temp": float(temp),
            })

    if len(clean_hours) < 2:
        return ""

    temps = [hour["temp"] for hour in clean_hours]
    lo, hi = min(temps), max(temps)
    if hi == lo:
        hi += 1
        lo -= 1

    pad_left = 12
    pad_right = 12
    pad_top = 8
    pad_bottom = 26
    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom
    spread = hi - lo
    baseline_y = height - pad_bottom

    points = []
    for index, hour in enumerate(clean_hours):
        ratio_x = index / (len(clean_hours) - 1)
        ratio_y = (hour["temp"] - lo) / spread
        x = pad_left + (plot_width * ratio_x)
        y = baseline_y - (plot_height * ratio_y)
        points.append((x, y, hour))

    line_path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y, _ in points)
    area_path = (
        f"M {points[0][0]:.1f} {baseline_y:.1f} "
        + " L ".join(f"{x:.1f} {y:.1f}" for x, y, _ in points)
        + f" L {points[-1][0]:.1f} {baseline_y:.1f} Z"
    )

    guide_lines = []
    for fraction in (0.0, 0.5, 1.0):
        y = pad_top + (plot_height * fraction)
        guide_lines.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" '
            f'stroke="{theme_line}" stroke-width="1" stroke-dasharray="3 4"/>'
        )

    labels = []
    step = max(1, len(points) // 6)
    for index, (x, _, hour) in enumerate(points):
        if index == 0 or index == len(points) - 1 or index % step == 0:
            labels.append(
                f'<text x="{x:.1f}" y="{height - 6}" font-size="10.5" font-weight="800" '
                f'text-anchor="middle" fill="{chart_label}">{hour["time"]}</text>'
            )

    dots = []
    for index, (x, y, _) in enumerate(points):
        radius = 2.4 if index == 0 else 1.6
        fill = "#f0a85c" if index == 0 else "#8fa4c4"
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}" '
            f'stroke="{theme_paper}" stroke-width="1"/>'
        )

    temp_labels = [
        f'<text x="{pad_left}" y="{pad_top - 1}" font-size="11" font-weight="800" fill="{chart_value}">{round(hi)}°</text>',
        (
            f'<text x="{pad_left}" y="{baseline_y - 3}" font-size="11" font-weight="800" fill="{chart_value}">'
            f'{round(lo)}°</text>'
        ),
    ]

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" '
        f'viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        "<defs>"
        '<linearGradient id="wxArea" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#f3c17b" stop-opacity="0.28"/>'
        f'<stop offset="100%" stop-color="{theme_line_soft}" stop-opacity="0.16"/>'
        "</linearGradient>"
        "</defs>"
        f'<path d="{area_path}" fill="url(#wxArea)"/>'
        + "".join(guide_lines)
        + f'<path d="{line_path}" fill="none" stroke="{chart_line}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        + "".join(dots)
        + "".join(temp_labels)
        + "".join(labels)
        + "</svg>"
    )
    return svg


# ---------------------------------------------------------------------------
# WMO code → icon mapping
# ---------------------------------------------------------------------------

_WMO_ICON_MAP = {
    0:  "clear_day",
    1:  "clear_day",
    2:  "partly_cloudy_day",
    3:  "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "showers",
    81: "showers",
    82: "showers",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}


def _wmo_icon_path(code: int) -> str | None:
    """Return a file:// path for a WMO weather code icon (works in Chromium file:// screenshots)."""
    name = _WMO_ICON_MAP.get(code, "cloudy")
    for fname in (f"{name}.svg", "cloudy.svg"):
        full = os.path.join(_ICON_DIR, fname)
        if os.path.exists(full):
            return f"file://{full}"
    return None


_WMO_TO_MSW_ICON_MAP = {
    0: 1,
    1: 2,
    2: 3,
    3: 5,
    45: 6,
    48: 6,
    51: 7,
    53: 8,
    55: 8,
    61: 9,
    63: 10,
    65: 11,
    71: 14,
    73: 15,
    75: 16,
    77: 14,
    80: 28,
    81: 29,
    82: 30,
    85: 31,
    86: 31,
    95: 17,
    96: 19,
    99: 19,
}


def _wmo_to_msw_icon_code(code: int) -> int:
    """Approximate a MeteoSwiss symbol code from a WMO weather code."""
    return _WMO_TO_MSW_ICON_MAP.get(code, 5)


# ---------------------------------------------------------------------------
# MeteoSwiss icon codes → description
# ---------------------------------------------------------------------------

_MSW_DESCRIPTIONS = {
    1:  "Sunny", 2:  "Slightly cloudy", 3:  "Partly cloudy",
    4:  "Very cloudy", 5:  "Overcast", 6:  "Foggy",
    7:  "Light drizzle", 8:  "Drizzle", 9:  "Light rain",
    10: "Rain", 11: "Heavy rain", 12: "Snow flurries",
    13: "Sleet", 14: "Light snow", 15: "Snowfall", 16: "Heavy snow",
    17: "Thunderstorm", 18: "Thunderstorm", 19: "Thunderstorm with hail",
    20: "Low stratus", 21: "Fog", 22: "Light rain", 23: "Rain",
    24: "Snow", 25: "Thunderstorm", 26: "Stratus and fog",
    27: "Stratus with mist", 28: "Light showers", 29: "Showers",
    30: "Heavy showers", 31: "Snow showers", 32: "Hail thunderstorm",
    33: "Heavy thunderstorm", 34: "Storm", 35: "Windy",
}

def _msw_desc(code: int) -> str:
    """Description for a MeteoSwiss symbol code (day 1-35, night 101-135)."""
    base = code if code < 100 else code - 100
    return _MSW_DESCRIPTIONS.get(base, "Variable")

def _msw_icon_path(code: int) -> str:
    """Return a file:// path for a MeteoSwiss symbol icon (works in Chromium file:// screenshots)."""
    for candidate in [code, code - 100 if code > 100 else None]:
        if candidate and candidate > 0:
            fname = f"msw_{candidate}.svg"
            full = os.path.join(_ICON_DIR, fname)
            if os.path.exists(full):
                return f"file://{full}"
    return f"file://{os.path.join(_ICON_DIR, 'cloudy.svg')}"

# Cache: {plz: (unix_ts, data)}
_MSW_CACHE: dict = {}
_MSW_CACHE_TTL = 1800  # 30 minutes
_GEOCODE_CACHE: dict[tuple[float, float], str | None] = {}


def _reverse_geocode_location_label(lat: float, lon: float) -> str | None:
    """Resolve a human-readable location label from coordinates."""
    import urllib.request

    cache_key = (round(lat, 3), round(lon, 3))
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    url = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?format=json&lat={lat:.6f}&lon={lon:.6f}&zoom=12&addressdetails=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "E-InkPi/1.0"})
    label = None
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            geo = json.loads(resp.read())
        label = (
            _location_label_from_address(geo.get("address", {}))
            or (geo.get("display_name") or "").split(",", 1)[0].strip()
            or None
        )
    except Exception:
        label = None

    _GEOCODE_CACHE[cache_key] = label
    return label


def _find_valid_msw_plz(base_plz4: int) -> str | None:
    """Scan nearby Swiss PLZ codes to find one that MeteoSwiss supports."""
    import urllib.request
    for delta in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 8, -8, 10, -10]:
        plz4 = base_plz4 + delta
        if plz4 < 1000 or plz4 > 9999:
            continue
        plz6 = f"{plz4}00"
        url  = f"https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz={plz6}"
        req  = urllib.request.Request(url, headers={"User-Agent": "E-InkPi/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                d = json.loads(r.read())
            if d.get("currentWeather", {}).get("temperature") is not None:
                return plz6
        except Exception:
            continue
    return None


def _fetch_meteoswiss(lat: float, lon: float) -> dict:
    """Fetch MeteoSwiss forecast via the official app API, cached 30 min."""
    import urllib.request, time

    # 1. Reverse-geocode to Swiss PLZ (zoom=16 required for postcode)
    geo_url = (f"https://nominatim.openstreetmap.org/reverse"
               f"?format=json&lat={lat:.6f}&lon={lon:.6f}&zoom=16&addressdetails=1")
    req = urllib.request.Request(geo_url, headers={"User-Agent": "E-InkPi/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        geo = json.loads(resp.read())
    addr    = geo.get("address", {})
    country = addr.get("country_code", "").lower()
    if country != "ch":
        raise RuntimeError(
            "MeteoSwiss only covers Switzerland. "
            "Your location appears to be outside Switzerland — "
            "please switch to Open-Meteo in the settings."
        )
    postcode = addr.get("postcode", "")
    digits   = "".join(ch for ch in postcode if ch.isdigit())[:4]
    if len(digits) != 4:
        raise RuntimeError("Could not determine Swiss postal code for your location.")

    base_plz4 = int(digits)

    # 2. Cache check
    cache_key = str(base_plz4)
    cached    = _MSW_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _MSW_CACHE_TTL:
        return cached[1]

    # 3. Find nearest valid PLZ (MeteoSwiss only supports specific PLZ codes)
    plz6 = _find_valid_msw_plz(base_plz4)
    if not plz6:
        raise RuntimeError(
            f"No MeteoSwiss forecast found near postal code {base_plz4}. "
            "Try selecting a different location or switch to Open-Meteo."
        )

    # 4. Fetch full forecast data
    url = f"https://app-prod-ws.meteoswiss-app.ch/v1/plzDetail?plz={plz6}"
    req = urllib.request.Request(url, headers={"User-Agent": "E-InkPi/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    data["_location_label"] = (
        _location_label_from_address(addr)
        or (geo.get("display_name") or "").split(",", 1)[0].strip()
    )
    _MSW_CACHE[cache_key] = (time.time(), data)
    return data


def _parse_meteoswiss(
    data: dict,
    plugin_settings: dict,
    timezone_name: str,
    supplemental_ctx: dict | None = None,
) -> dict:
    """Parse MeteoSwiss API response into the shared template context dict."""
    cur          = data.get("currentWeather", {})
    forecast_raw = data.get("forecast", [])
    graph        = data.get("graph", {})
    tz           = _safe_timezone(timezone_name)
    units        = plugin_settings.get("units", "metric")
    fallback     = supplemental_ctx or {}
    theme_palette = _resolve_theme_colors(plugin_settings)

    temp      = cur.get("temperature", "—")
    icon_code = cur.get("icon", 1)

    def _ts_hhmm(ts_ms):
        if not ts_ms:
            return "—"
        return datetime.datetime.fromtimestamp(ts_ms / 1000, tz).strftime("%H:%M")

    sunrises = graph.get("sunrise", [])
    sunsets  = graph.get("sunset",  [])
    sunrise  = _ts_hhmm(sunrises[0]) if sunrises else "—"
    sunset   = _ts_hhmm(sunsets[0])  if sunsets  else "—"

    h_temps       = graph.get("temperatureMean1h", [])
    graph_start   = graph.get("start", 0)
    hourly_list   = []
    for i, value in enumerate(h_temps[:24]):
        ts = graph_start + i * 3600 * 1000
        hourly_list.append({
            "time": datetime.datetime.fromtimestamp(ts / 1000, tz).strftime("%H:%M"),
            "temp": _convert_temperature(value, units),
        })

    winds = graph.get("windSpeed3h", [])
    wind  = _convert_wind_speed(sum(winds[:8]) / len(winds[:8]), units) if winds else "—"

    n_days = int(plugin_settings.get("forecastDays", 7))
    forecast_days = []
    for day in forecast_raw[:n_days]:
        try:
            day_name = datetime.date.fromisoformat(day["dayDate"]).strftime("%a")
        except Exception:
            day_name = "—"
        d_icon = day.get("iconDay", 1)
        forecast_days.append({
            "day":         day_name,
            "description": _msw_desc(d_icon),
            "temp_max":    _convert_temperature(day.get("temperatureMax", "—"), units),
            "temp_min":    _convert_temperature(day.get("temperatureMin", "—"), units),
            "icon_path":   _msw_icon_path(d_icon),
            "precip":      day.get("precipitation", 0),
        })

    if not forecast_days and fallback.get("forecast_days"):
        for day in fallback["forecast_days"][:n_days]:
            forecast_days.append({
                **day,
                "icon_path": _msw_icon_path(_wmo_to_msw_icon_code(day.get("wmo_code", 0))),
            })

    now = datetime.datetime.now(tz)
    moon_icon, moon_name = _moon_phase(now.date())
    moon_asset = _moon_phase_asset(moon_name)
    rain_now = (graph.get("precipitation1h") or [0])[0]
    rain_value = round(rain_now, 1) if isinstance(rain_now, (int, float)) else rain_now
    if rain_value in (0, "—") and fallback.get("rain") not in (None, "", "—"):
        rain_value = fallback.get("rain")

    today_fc = forecast_raw[0] if forecast_raw else {}
    temp_max_today = _convert_temperature(today_fc.get("temperatureMax", "—"), units) if today_fc else "—"
    temp_min_today = _convert_temperature(today_fc.get("temperatureMin", "—"), units) if today_fc else "—"

    return {
        "temperature":         fallback.get("temperature", _convert_temperature(temp, units)),
        "feels_like":          fallback.get("feels_like", "—"),
        "weather_description": _msw_desc(icon_code),
        "weather_icon_path":   _msw_icon_path(icon_code),
        "humidity":            fallback.get("humidity", "—"),
        "wind_speed":          fallback.get("wind_speed", wind),
        "pressure":            fallback.get("pressure", "—"),
        "visibility":          fallback.get("visibility", "—"),
        "rain":                rain_value,
        "uvi":                 fallback.get("uvi", "—"),
        "sunrise":             sunrise if sunrise != "—" else fallback.get("sunrise", "—"),
        "sunset":              sunset if sunset != "—" else fallback.get("sunset", "—"),
        "temp_max_today":      temp_max_today if temp_max_today != "—" else fallback.get("temp_max_today", "—"),
        "temp_min_today":      temp_min_today if temp_min_today != "—" else fallback.get("temp_min_today", "—"),
        "moon_phase_icon":     moon_icon,
        "moon_phase":          moon_name,
        "moon_phase_asset":    moon_asset,
        "hourly_graph_svg":    _build_hourly_svg(hourly_list, palette=theme_palette) if hourly_list else fallback.get("hourly_graph_svg", ""),
        "forecast_days":       forecast_days,
        "current_date":        _format_display_date(now),
        "current_time":        now.strftime("%H:%M"),
        "refresh_time":        now.strftime("%H:%M"),
        "wmo_code":            None,
        "msw_icon_code":       icon_code,
        "temperature_unit_symbol": _temperature_unit_symbol(units),
        "wind_unit":           "mph" if units == "imperial" else "km/h",
        "rain_unit":           "in" if units == "imperial" else "mm",
        "wind_icon_path":      _asset_path("wind.svg"),
        "humidity_icon_path":  _asset_path("humidity.svg"),
        "pressure_icon_path":  _asset_path("pressure.svg"),
        "rain_icon_path":      _asset_path("rain.svg"),
        "sunrise_icon_path":   _asset_path("sunrise.svg"),
        "sunset_icon_path":    _asset_path("sunset.svg"),
        "visibility_icon_path": _asset_path("visibility.svg"),
        "uvi_icon_path":       _asset_path("uvi.svg"),
        "timezone_name":       timezone_name,
    }


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


def _wmo_desc(code: int) -> str:
    return WMO_CODES.get(code, f"Code {code}")


def _fetch_open_meteo(lat: float, lon: float, units: str) -> dict:
    import urllib.request
    temp_unit = "fahrenheit" if units == "imperial" else "celsius"
    wind_unit = "mph" if units == "imperial" else "kmh"
    precip_unit = "inch" if units == "imperial" else "mm"
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        f"wind_speed_10m,surface_pressure,weather_code,precipitation,visibility"
        f"&hourly=temperature_2m,weather_code"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max"
        f"&temperature_unit={temp_unit}&wind_speed_unit={wind_unit}"
        f"&precipitation_unit={precip_unit}&forecast_days=7&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def _parse_open_meteo(data: dict, plugin_settings: dict, timezone_name: str) -> dict:
    """Parse Open-Meteo JSON into the template context dict."""
    cur    = data.get("current", {})
    daily  = data.get("daily", {})
    hourly = data.get("hourly", {})
    source_timezone = data.get("timezone") or timezone_name
    tz = _safe_timezone(timezone_name)
    units = plugin_settings.get("units", "metric")
    theme_palette = _resolve_theme_colors(plugin_settings)

    temp     = cur.get("temperature_2m", "—")
    feels    = cur.get("apparent_temperature", "—")
    humidity = cur.get("relative_humidity_2m", "—")
    wind     = cur.get("wind_speed_10m", "—")
    pressure = cur.get("surface_pressure", "—")
    visibility = cur.get("visibility", "—")
    rain     = cur.get("precipitation", 0)
    code     = cur.get("weather_code", 0)

    # Hourly forecast for graph (next 24 h)
    h_times = hourly.get("time", [])[:24]
    h_temps = hourly.get("temperature_2m", [])[:24]
    hourly_list = [
        {"time": _convert_iso_time(t, source_timezone, timezone_name), "temp": v}
        for t, v in zip(h_times, h_temps)
    ]

    # Daily forecast
    d_dates   = daily.get("time", [])
    d_codes   = daily.get("weather_code", [])
    d_hi      = daily.get("temperature_2m_max", [])
    d_lo      = daily.get("temperature_2m_min", [])
    d_sunrise = daily.get("sunrise", [])
    d_sunset  = daily.get("sunset", [])
    d_uvi     = daily.get("uv_index_max", [])

    forecast_days = []
    n_days = int(plugin_settings.get("forecastDays", 7))
    for i in range(min(n_days, len(d_dates))):
        try:
            day_name = datetime.date.fromisoformat(d_dates[i]).strftime("%a")
        except Exception:
            day_name = d_dates[i] if i < len(d_dates) else "—"
        wmo = d_codes[i] if i < len(d_codes) else 0
        msw_code = _wmo_to_msw_icon_code(wmo)
        high = d_hi[i] if i < len(d_hi) else "—"
        low = d_lo[i] if i < len(d_lo) else "—"
        if units == "standard":
            high = _convert_temperature(high, units)
            low = _convert_temperature(low, units)
        elif isinstance(high, float):
            high = round(high)
        elif isinstance(high, int):
            high = high
        if units != "standard":
            if isinstance(low, float):
                low = round(low)
            elif isinstance(low, int):
                low = low
        forecast_days.append({
            "day":         day_name,
            "description": _msw_desc(msw_code),
            "temp_max":    high,
            "temp_min":    low,
            "icon_path":   _msw_icon_path(msw_code),
            "wmo_code":    wmo,
            "msw_icon_code": msw_code,
        })

    sunrise = _convert_iso_time(d_sunrise[0], source_timezone, timezone_name) if d_sunrise else "—"
    sunset  = _convert_iso_time(d_sunset[0], source_timezone, timezone_name) if d_sunset  else "—"
    uvi     = round(d_uvi[0], 1)  if d_uvi     else "—"

    now = datetime.datetime.now(tz)
    moon_icon, moon_name = _moon_phase(now.date())
    moon_asset = _moon_phase_asset(moon_name)
    current_msw_code = _wmo_to_msw_icon_code(code)

    return {
        "temperature":         _convert_temperature(temp, units) if units == "standard" else (round(temp) if isinstance(temp, float) else temp),
        "feels_like":          _convert_temperature(feels, units) if units == "standard" else (round(feels) if isinstance(feels, float) else feels),
        "weather_description": _msw_desc(current_msw_code),
        "weather_icon_path":   _msw_icon_path(current_msw_code),
        "humidity":            humidity,
        "wind_speed":          round(wind)     if isinstance(wind, float)     else wind,
        "pressure":            round(pressure) if isinstance(pressure, float) else pressure,
        "visibility":          _format_visibility(visibility),
        "rain":                rain,
        "uvi":                 uvi,
        "sunrise":             sunrise,
        "sunset":              sunset,
        "temp_max_today":      (_convert_temperature(d_hi[0], units) if units == "standard" else round(d_hi[0])) if d_hi else "—",
        "temp_min_today":      (_convert_temperature(d_lo[0], units) if units == "standard" else round(d_lo[0])) if d_lo else "—",
        "moon_phase_icon":     moon_icon,
        "moon_phase":          moon_name,
        "moon_phase_asset":    moon_asset,
        "hourly_graph_svg":    _build_hourly_svg(hourly_list, palette=theme_palette),
        "forecast_days":       forecast_days,
        "current_date":        _format_display_date(now),
        "current_time":        now.strftime("%H:%M"),
        "refresh_time":        now.strftime("%H:%M"),
        "wmo_code":            code,
        "msw_icon_code":       current_msw_code,
        "temperature_unit_symbol": _temperature_unit_symbol(units),
        "wind_unit":           "mph" if units == "imperial" else "km/h",
        "rain_unit":           "in" if units == "imperial" else "mm",
        "wind_icon_path":      _asset_path("wind.svg"),
        "humidity_icon_path":  _asset_path("humidity.svg"),
        "pressure_icon_path":  _asset_path("pressure.svg"),
        "rain_icon_path":      _asset_path("rain.svg"),
        "sunrise_icon_path":   _asset_path("sunrise.svg"),
        "sunset_icon_path":    _asset_path("sunset.svg"),
        "visibility_icon_path": _asset_path("visibility.svg"),
        "uvi_icon_path":       _asset_path("uvi.svg"),
        "timezone_name":       timezone_name,
    }


# ---------------------------------------------------------------------------
# Main plugin class
# ---------------------------------------------------------------------------

class WeatherPlugin(BasePlugin):
    """InkyPi weather plugin — returns a PIL Image ready to display on e-ink."""

    PLUGIN_NAME = "weather"

    def generate_image(self, plugin_settings: dict, device_config) -> "PIL.Image.Image":
        """
        Fetch weather data, render HTML, screenshot via Chromium, return PIL Image.

        CRITICAL: use `is None` check (not `not lat`) so lat=0.0 (equator) is valid.
        """
        lat = plugin_settings.get("latitude")
        lon = plugin_settings.get("longitude")

        try:
            lat = float(lat) if lat not in (None, "", "None") else None
            lon = float(lon) if lon not in (None, "", "None") else None
        except (TypeError, ValueError):
            lat = None
            lon = None

        if lat is None or lon is None:
            raise RuntimeError(
                "Latitude and Longitude are required. "
                "Open the weather plugin settings and set your location."
            )

        provider = plugin_settings.get("weatherProvider", "MeteoSwiss")
        units    = plugin_settings.get("units", "metric")
        location_label = (plugin_settings.get("city") or "").strip()

        if provider == "MeteoSwiss":
            raw = _fetch_meteoswiss(lat, lon)
            display_timezone = _resolve_display_timezone(provider, raw, plugin_settings, device_config)
            supplemental_ctx = None
            supplemental_raw = _fetch_open_meteo(lat, lon, units)
            supplemental_ctx = _parse_open_meteo(supplemental_raw, plugin_settings, display_timezone)
            ctx = _parse_meteoswiss(raw, plugin_settings, display_timezone, supplemental_ctx=supplemental_ctx)
            location_label = location_label or raw.get("_location_label")
        elif provider == "OpenMeteo":
            raw = _fetch_open_meteo(lat, lon, units)
            display_timezone = _resolve_display_timezone(provider, raw, plugin_settings, device_config)
            ctx = _parse_open_meteo(raw, plugin_settings, display_timezone)
        else:
            raise RuntimeError(f"Unknown provider: '{provider}'.")

        # Title and city
        title_sel = plugin_settings.get("titleSelection", "custom")
        custom_title = (plugin_settings.get("customTitle") or "").strip()
        if not location_label and (title_sel == "location" or not custom_title):
            location_label = _reverse_geocode_location_label(lat, lon)
        ctx["city"] = location_label or custom_title or "Weather"
        ctx["title"] = (
            ctx["city"] if title_sel == "location"
            else (custom_title or ctx["city"] or "Weather")
        )
        ctx["plugin_settings"] = plugin_settings
        ctx["source_name"] = "MeteoSwiss" if provider == "MeteoSwiss" else "Open-Meteo"
        ctx["custom_overlay_blocks"] = _parse_custom_overlay_blocks(plugin_settings)
        ctx.update(_resolve_theme_colors(plugin_settings))

        # Display dimensions from device config
        try:
            width  = int(device_config.get_config("display_width",  default=800))
            height = int(device_config.get_config("display_height", default=480))
        except Exception:
            width, height = 800, 480

        ctx["display_width"]  = width
        ctx["display_height"] = height

        # Render HTML → PIL Image
        html = self._render(ctx)
        from utils.image_utils import take_screenshot_html
        timeout_ms = int(plugin_settings.get("screenshotTimeout", 15000))
        image = take_screenshot_html(html, (width, height), timeout_ms=timeout_ms)
        if image is None:
            raise RuntimeError(
                "Weather display render failed — Chromium returned no image. "
                "Check that chromium or chromium-headless-shell is installed."
            )
        # Tighten vector-ish UI edges after the Chromium screenshot pass so
        # icons and labels stay crisper on the e-ink panel.
        # Skip this for dark themes because it introduces gray halos that
        # Spectra panels can quantize into unwanted colors.
        is_dark_theme = _relative_luminance(
            _sanitize_color(plugin_settings.get("weatherBackgroundColor"), "#ffffff")
        ) < 0.32
        if not is_dark_theme:
            image = image.filter(ImageFilter.UnsharpMask(radius=0.7, percent=165, threshold=2))
        return image

    def _render(self, ctx: dict) -> str:
        """Load and render the Jinja2 weather.html template."""
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            return self._fallback_html(ctx)

        template_dir = os.path.join(os.path.dirname(__file__), "render")
        env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
        import json as _json
        env.filters.setdefault("tojson", lambda v: _json.dumps(v))
        return env.get_template("weather.html").render(**ctx)

    def _fallback_html(self, ctx: dict) -> str:
        temp  = ctx.get("temperature", "—")
        desc  = ctx.get("weather_description", "")
        title = ctx.get("title", "Weather")
        return (
            f"<!DOCTYPE html><html><body style='font-family:sans-serif;padding:20px'>"
            f"<h2>{title}</h2><p style='font-size:3em'>{temp}°</p>"
            f"<p>{desc}</p></body></html>"
        )


__all__ = ["WeatherPlugin"]
