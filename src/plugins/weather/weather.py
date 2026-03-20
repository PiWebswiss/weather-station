"""
Weather plugin — fetches data from Open-Meteo and renders the e-ink weather
display via weather.html, then returns a PIL Image via Chromium headless.
"""
from __future__ import annotations

import json
import os
import datetime


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


# ---------------------------------------------------------------------------
# Helper: simple SVG bar-chart for hourly temperatures
# ---------------------------------------------------------------------------

def _build_hourly_svg(hours: list[dict], width: int = 388, height: int = 48) -> str:
    """Build a minimal SVG bar chart from a list of {time, temp} dicts."""
    if not hours:
        return ""
    temps = [h.get("temp", 0) for h in hours]
    lo, hi = min(temps), max(temps)
    spread = hi - lo or 1
    bar_w = max(1, width // len(temps) - 1)
    rects = []
    labels = []
    for i, h in enumerate(hours):
        t = h.get("temp", 0)
        norm = (t - lo) / spread
        bar_h = max(4, int(norm * (height - 16)))
        x = i * (bar_w + 1) + 1
        y = height - bar_h - 8
        rects.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="#444"/>')
        if i % 4 == 0:
            time_str = h.get("time", "")
            labels.append(f'<text x="{x + bar_w // 2}" y="{height - 1}" font-size="7" '
                          f'text-anchor="middle" fill="#666">{time_str}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">')
    svg += "".join(rects) + "".join(labels) + "</svg>"
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
    """Return the web path for a WMO weather code icon, or None if not found."""
    name = _WMO_ICON_MAP.get(code, "cloudy")
    icon_dir = os.path.join(os.path.dirname(__file__), "icons")
    if os.path.exists(os.path.join(icon_dir, f"{name}.svg")):
        return f"/static/plugins/weather/icons/{name}.svg"
    if os.path.exists(os.path.join(icon_dir, "cloudy.svg")):
        return "/static/plugins/weather/icons/cloudy.svg"
    return None


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
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        f"wind_speed_10m,surface_pressure,weather_code,precipitation"
        f"&hourly=temperature_2m,weather_code"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max"
        f"&temperature_unit={temp_unit}&wind_speed_unit={wind_unit}"
        f"&precipitation_unit=mm&forecast_days=7&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def _parse_open_meteo(data: dict, plugin_settings: dict) -> dict:
    """Parse Open-Meteo JSON into the template context dict."""
    cur    = data.get("current", {})
    daily  = data.get("daily", {})
    hourly = data.get("hourly", {})

    temp     = cur.get("temperature_2m", "—")
    feels    = cur.get("apparent_temperature", "—")
    humidity = cur.get("relative_humidity_2m", "—")
    wind     = cur.get("wind_speed_10m", "—")
    pressure = cur.get("surface_pressure", "—")
    rain     = cur.get("precipitation", 0)
    code     = cur.get("weather_code", 0)

    # Hourly forecast for graph (next 24 h)
    h_times = hourly.get("time", [])[:24]
    h_temps = hourly.get("temperature_2m", [])[:24]
    hourly_list = [{"time": t[11:16], "temp": v} for t, v in zip(h_times, h_temps)]

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
        forecast_days.append({
            "day":         day_name,
            "description": _wmo_desc(wmo),
            "temp_max":    round(d_hi[i]) if i < len(d_hi) else "—",
            "temp_min":    round(d_lo[i]) if i < len(d_lo) else "—",
            "icon_path":   _wmo_icon_path(wmo),
            "wmo_code":    wmo,
        })

    sunrise = d_sunrise[0][11:16] if d_sunrise else "—"
    sunset  = d_sunset[0][11:16]  if d_sunset  else "—"
    uvi     = round(d_uvi[0], 1)  if d_uvi     else "—"

    now = datetime.datetime.now()
    moon_icon, moon_name = _moon_phase(now.date())

    return {
        "temperature":         round(temp)     if isinstance(temp, float)     else temp,
        "feels_like":          round(feels)    if isinstance(feels, float)    else feels,
        "weather_description": _wmo_desc(code),
        "weather_icon_path":   _wmo_icon_path(code),
        "humidity":            humidity,
        "wind_speed":          round(wind)     if isinstance(wind, float)     else wind,
        "pressure":            round(pressure) if isinstance(pressure, float) else pressure,
        "rain":                rain,
        "uvi":                 uvi,
        "sunrise":             sunrise,
        "sunset":              sunset,
        "moon_phase_icon":     moon_icon,
        "moon_phase":          moon_name,
        "hourly_graph_svg":    _build_hourly_svg(hourly_list),
        "forecast_days":       forecast_days,
        "current_date":        now.strftime("%a, %d %b %Y"),
        "current_time":        now.strftime("%H:%M"),
        "refresh_time":        now.strftime("%H:%M"),
        "wmo_code":            code,
    }


# ---------------------------------------------------------------------------
# Main plugin class
# ---------------------------------------------------------------------------

class WeatherPlugin:
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

        provider = plugin_settings.get("weatherProvider", "OpenMeteo")
        units    = plugin_settings.get("units", "metric")

        if provider == "OpenMeteo":
            raw = _fetch_open_meteo(lat, lon, units)
            ctx = _parse_open_meteo(raw, plugin_settings)
        else:
            raise RuntimeError(
                f"Provider '{provider}' is not yet implemented. "
                "Please select Open-Meteo in the settings."
            )

        # Title and city
        title_sel = plugin_settings.get("titleSelection", "custom")
        ctx["title"] = (plugin_settings.get("customTitle", "Weather")
                        if title_sel == "custom"
                        else plugin_settings.get("city", "Weather"))
        ctx["city"] = plugin_settings.get("city", "—")
        ctx["plugin_settings"] = plugin_settings

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
