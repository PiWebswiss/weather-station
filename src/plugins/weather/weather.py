from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
import os
import csv
import json
import requests
import logging
from datetime import datetime, timedelta, timezone, date
from astral import moon
from astral import Observer
from astral.sun import sun
import pytz
from io import BytesIO, StringIO
import math

logger = logging.getLogger(__name__)
        
def get_moon_phase_name(phase_age: float) -> str:
    """Determines the name of the lunar phase based on the age of the moon."""
    PHASES_THRESHOLDS = [
        (1.0, "newmoon"),
        (7.0, "waxingcrescent"),
        (8.5, "firstquarter"),
        (14.0, "waxinggibbous"),
        (15.5, "fullmoon"),
        (22.0, "waninggibbous"),
        (23.5, "lastquarter"),
        (29.0, "waningcrescent"),
    ]

    for threshold, phase_name in PHASES_THRESHOLDS:
        if phase_age <= threshold:
            return phase_name  
    return "newmoon"

UNITS = {
    "standard": {
        "temperature": "K",
        "speed": "m/s",
        "distance":"km"
    },
    "metric": {
        "temperature": "°C",
        "speed": "m/s",
        "distance":"km"

    },
    "imperial": {
        "temperature": "°F",
        "speed": "mph",
        "distance":"mi"
    }
}

WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={long}&units={units}&exclude=minutely&appid={api_key}"
AIR_QUALITY_URL = "http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={long}&appid={api_key}"
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={long}&limit=1&appid={api_key}"

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={long}&hourly=weather_code,temperature_2m,precipitation,precipitation_probability,relative_humidity_2m,surface_pressure,visibility&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset&current=temperature,windspeed,winddirection,is_day,precipitation,weather_code,apparent_temperature&timezone=auto&models=best_match&forecast_days={forecast_days}"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={long}&hourly=european_aqi,uv_index,uv_index_clear_sky&timezone=auto"
OPEN_METEO_UNIT_PARAMS = {
    "standard": "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",  # temperature is converted to Kelvin later
    "metric":   "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",
    "imperial": "temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
}

IP_GEO_URL = "https://ipapi.co/json/"

METEOSWISS_STAC_BASE = "https://data.geo.admin.ch/api/stac/v1/collections"
METEOSWISS_LOCAL_FORECAST_COLLECTION = "ch.meteoschweiz.ogd-local-forecasting"
METEOSWISS_SMN_COLLECTION = "ch.meteoschweiz.ogd-smn"

METEOSWISS_LOCAL_FORECAST_META_POINT_URL = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-local-forecasting/ogd-local-forecasting_meta_point.csv"
METEOSWISS_SMN_META_STATIONS_URL = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/ogd-smn_meta_stations.csv"

METEOSWISS_CACHE_TTL_SECONDS = 30 * 60  # 30 min — was 2 h, kept stale during the day

# MeteoSwiss icon code -> internal icon name (mapped from official symbol descriptions)
METEOSWISS_ICON_MAP = {
    1: '01d', 2: '022d', 3: '02d', 4: '04d', 5: '04d', 6: '10d', 7: '13d', 8: '13d',
    9: '10d', 10: '13d', 11: '13d', 12: '11d', 13: '11d', 14: '10d', 15: '13d',
    16: '13d', 17: '10d', 18: '13d', 19: '13d', 20: '10d', 21: '13d', 22: '13d',
    23: '11d', 24: '11d', 25: '11d', 26: '04d', 27: '04d', 28: '50d', 29: '10d',
    30: '13d', 31: '13d', 32: '10d', 33: '10d', 34: '13d', 35: '04d', 36: '11d',
    37: '11d', 38: '11d', 39: '11d', 40: '11d', 41: '11d', 42: '11d',
    101: '01d', 102: '04d', 103: '04d', 104: '04d', 105: '04d', 106: '10d', 107: '13d',
    108: '13d', 109: '10d', 110: '13d', 111: '13d', 112: '11d', 113: '11d',
    114: '10d', 115: '13d', 116: '13d', 117: '10d', 118: '13d', 119: '13d',
    120: '10d', 121: '13d', 122: '13d', 123: '11d', 124: '11d', 125: '11d',
    126: '04d', 127: '04d', 128: '50d', 129: '10d', 130: '13d', 131: '13d',
    132: '10d', 133: '13d', 134: '13d', 135: '04d', 136: '11d', 137: '11d',
    138: '11d', 139: '11d', 140: '11d', 141: '11d', 142: '11d'
}

METEOSWISS_ICON_NIGHT_MAP = {
    "01d": "01n",
    "02d": "02n",
    "022d": "022n",
    "10d": "10n"
}

class Weather(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenWeatherMap",
            "expected_key": "OPEN_WEATHER_MAP_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        auto_location = str(settings.get('autoLocation', 'false')).lower() == 'true'
        lat = self._safe_float(settings.get('latitude'))
        long = self._safe_float(settings.get('longitude'))
        geo = None

        if auto_location:
            geo = self.get_ip_geolocation()
            if geo:
                lat = geo.get("lat")
                long = geo.get("lon")

        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        units = settings.get('units')
        if not units or units not in ['metric', 'imperial', 'standard']:
            raise RuntimeError("Units are required.")

        weather_provider = settings.get('weatherProvider', 'OpenWeatherMap')
        title = settings.get('customTitle', '')

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        try:
            if weather_provider == "OpenWeatherMap":
                api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
                if not api_key:
                    raise RuntimeError("Open Weather Map API Key not configured.")
                weather_data = self.get_weather_data(api_key, units, lat, long)
                aqi_data = self.get_air_quality(api_key, lat, long)
                if settings.get('titleSelection', 'location') == 'location':
                    title = self.get_location(api_key, lat, long)
                if settings.get('weatherTimeZone', 'locationTimeZone') == 'locationTimeZone':
                    logger.info("Using location timezone for OpenWeatherMap data.")
                    wtz = self.parse_timezone(weather_data)
                    template_params = self.parse_weather_data(weather_data, aqi_data, wtz, units, time_format, lat)
                else:
                    logger.info("Using configured timezone for OpenWeatherMap data.")
                    template_params = self.parse_weather_data(weather_data, aqi_data, tz, units, time_format, lat)
            elif weather_provider == "OpenMeteo":
                forecast_days = 7
                weather_data = self.get_open_meteo_data(lat, long, units, forecast_days + 1)
                aqi_data = self.get_open_meteo_air_quality(lat, long)
                template_params = self.parse_open_meteo_data(weather_data, aqi_data, tz, units, time_format, lat)
            elif weather_provider == "MeteoSwiss":
                forecast_days = int(settings.get('forecastDays', 7))
                tz_name = timezone
                if settings.get('weatherTimeZone', 'locationTimeZone') == 'locationTimeZone' and geo and geo.get('timezone'):
                    tz_name = geo.get('timezone')
                tz = pytz.timezone(tz_name)

                ms_data = self.get_meteoswiss_data(lat, long, tz, forecast_days)
                template_params = self.parse_meteoswiss_data(ms_data, tz, units, time_format, lat, long)
                if settings.get('titleSelection', 'location') == 'location':
                    title = ms_data.get("location_name", "") or title
            else:
                raise RuntimeError(f"Unknown weather provider: {weather_provider}")

            template_params['title'] = title
        except Exception as e:
            logger.error(f"{weather_provider} request failed: {str(e)}")
            raise RuntimeError(f"{weather_provider} request failure, please check logs.")
       
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params["plugin_settings"] = settings

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        image = self.render_image(dimensions, "weather.html", "weather.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def parse_weather_data(self, weather_data, aqi_data, tz, units, time_format, lat):
        current = weather_data.get("current")
        daily_forecast = weather_data.get("daily", [])
        dt = datetime.fromtimestamp(current.get('dt'), tz=timezone.utc).astimezone(tz)
        current_icon = current.get("weather")[0].get("icon")
        icon_codes_to_preserve = ["01", "02", "10"]
        icon_code = current_icon[:2]
        current_suffix = current_icon[-1]

        if icon_code not in icon_codes_to_preserve:
            if current_icon.endswith('n'):
                current_icon = current_icon.replace("n", "d")
        data = {
            "current_date": dt.strftime("%A, %B %d"),
            "current_day_icon": self.get_icon_path({current_icon}),
            "current_temperature": str(round(current.get("temp"))),
            "feels_like": str(round(current.get("feels_like"))),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }
        data['forecast'] = self.parse_forecast(weather_data.get('daily'), tz, current_suffix, lat)
        data['data_points'] = self.parse_data_points(weather_data, aqi_data, tz, units, time_format)

        data['hourly_forecast'] = self.parse_hourly(weather_data.get('hourly'), tz, time_format, units, daily_forecast)
        return data

    def parse_open_meteo_data(self, weather_data, aqi_data, tz, units, time_format, lat):
        current = weather_data.get("current", {})
        daily = weather_data.get('daily', {})
        dt = datetime.fromisoformat(current.get('time')).astimezone(tz) if current.get('time') else datetime.now(tz)
        weather_code = current.get("weather_code", 0)
        is_day = current.get("is_day", 1)
        current_icon = self.map_weather_code_to_icon(weather_code, is_day)
        
        temperature_conversion = 273.15 if units == "standard" else 0.

        data = {
            "current_date": dt.strftime("%A, %B %d"),
            "current_day_icon": self.get_icon_path({current_icon}),
            "current_temperature": str(round(current.get("temperature", 0) + temperature_conversion)),
            "feels_like": str(round(current.get("apparent_temperature", current.get("temperature", 0)) + temperature_conversion)),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_open_meteo_forecast(weather_data.get('daily', {}), units, tz, is_day, lat)
        data['data_points'] = self.parse_open_meteo_data_points(weather_data, aqi_data, units, tz, time_format)
        
        data['hourly_forecast'] = self.parse_open_meteo_hourly(weather_data.get('hourly', {}), units, tz, time_format, daily.get('sunrise', []), daily.get('sunset', []))
        return data


    def get_icon_path(self, name):
        """Return SVG icon path if downloaded, otherwise PNG fallback."""
        svg_path = self.get_plugin_dir('icons/' + name + '.svg')
        if os.path.isfile(svg_path):
            return svg_path
        return self.get_plugin_dir('icons/' + name + '.png')

    def map_weather_code_to_icon(self, weather_code, is_day):

        icon = "01d" # Default to clear day icon
        
        if weather_code in [0]:   # Clear sky
            icon = "01d"
        elif weather_code in [1]: # Mainly clear
            icon = "022d"
        elif weather_code in [2]: # Partly cloudy
            icon = "02d"
        elif weather_code in [3]: # Overcast
            icon = "04d"
        elif weather_code in [51, 61, 80]: # Drizzle, showers, rain: Light
            icon = "51d"          
        elif weather_code in [53, 63, 81]: # Drizzle, showers, rain: Moderatr
            icon = "53d"
        elif weather_code in [55, 65, 82]: # Drizzle, showers, rain: Heavy
            icon = "09d"
        elif weather_code in [45]: # Fog
            icon = "50d"                       
        elif weather_code in [48]: # Icy fog
            icon = "48d"
        elif weather_code in [56, 66]: # Light freezing Drizzle
            icon = "56d"            
        elif weather_code in [57, 67]: # Freezing Drizzle
            icon = "57d"            
        elif weather_code in [71, 85]: # Snow fall: Slight
            icon = "71d"
        elif weather_code in [73]:     # Snow fall: Moderate
            icon = "73d"
        elif weather_code in [75, 86]: # Snow fall: Heavy
            icon = "13d"
        elif weather_code in [77]:     # Snow grain
            icon = "77d"
        elif weather_code in [95]: # Thunderstorm
            icon = "11d"
        elif weather_code in [96, 99]: # Thunderstorm with slight and heavy hail
            icon = "11d"

        if is_day == 0:
            if icon == "01d":
                icon = "01n"      # Clear sky night
            elif icon == "022d":
                icon = "022n"     # Mainly clear night
            elif icon == "02d":
                icon = "02n"      # Partly cloudy night                
            elif icon == "10d":
                icon = "10n"      # Rain night

        return icon

    def get_moon_phase_icon_path(self, phase_name: str, lat: float) -> str:
        """Determines the path to the moon icon, inverting it if the location is in the Southern Hemisphere."""
        # Waxing, Waning, First and Last quarter phases are inverted between hemispheres.
        if lat < 0: # Southern Hemisphere
            if phase_name == "waxingcrescent":
                phase_name = "waningcrescent"
            elif phase_name == "waxinggibbous":
                phase_name = "waninggibbous"
            elif phase_name == "waningcrescent":
                phase_name = "waxingcrescent"
            elif phase_name == "waninggibbous":
                phase_name = "waxinggibbous"
            elif phase_name == "firstquarter":
                phase_name = "lastquarter"
            elif phase_name == "lastquarter":
                phase_name = "firstquarter"
        
        return self.get_icon_path(phase_name)

    def parse_forecast(self, daily_forecast, tz, current_suffix, lat):
        """
        - daily_forecast: list of daily entries from One‑Call v3 (each has 'dt', 'weather', 'temp', 'moon_phase')
        - tz: your target tzinfo (e.g. from zoneinfo or pytz)
        """
        PHASES = [
            (0.0, "newmoon"),
            (0.25, "firstquarter"),
            (0.5, "fullmoon"),
            (0.75, "lastquarter"),
            (1.0, "newmoon"),
        ]

        def choose_phase_name(phase: float) -> str:
            for target, name in PHASES:
                if math.isclose(phase, target, abs_tol=1e-3):
                    return name
            if 0.0 < phase < 0.25:
                return "waxingcrescent"
            elif 0.25 < phase < 0.5:
                return "waxinggibbous"
            elif 0.5 < phase < 0.75:
                return "waninggibbous"
            else:
                return "waningcrescent"

        forecast = []
        icon_codes_to_apply_current_suffix = ["01", "02", "10"]
        for day in daily_forecast:
            # --- weather icon ---
            weather_icon = day["weather"][0]["icon"]  # e.g. "10d", "01n"
            icon_code = weather_icon[:2]
            if icon_code in icon_codes_to_apply_current_suffix:
                weather_icon_base = weather_icon[:-1]
                weather_icon = weather_icon_base + current_suffix
            else:
                if weather_icon.endswith('n'):
                    weather_icon = weather_icon.replace("n", "d")
            weather_icon = f"{icon_code}d"        
            weather_icon_path = self.get_icon_path(weather_icon)

            # --- moon phase & icon ---
            moon_phase = float(day["moon_phase"])  # [0.0–1.0]
            phase_name_north_hemi = choose_phase_name(moon_phase)
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)
            # --- true illumination percent, no decimals ---
            illum_fraction = (1 - math.cos(2 * math.pi * moon_phase)) / 2
            moon_pct = f"{illum_fraction * 100:.0f}"

            # --- date & temps ---
            dt = datetime.fromtimestamp(day["dt"], tz=timezone.utc).astimezone(tz)
            day_label = dt.strftime("%a")

            forecast.append(
                {
                    "day": day_label,
                    "high": int(day["temp"]["max"]),
                    "low": int(day["temp"]["min"]),
                    "icon": weather_icon_path,
                    "moon_phase_pct": moon_pct,
                    "moon_phase_icon": moon_icon_path,
                }
            )

        return forecast
        
    def parse_open_meteo_forecast(self, daily_data, units, tz, is_day, lat):
        """
        Parse the daily forecast from Open-Meteo API and calculate moon phase and illumination using the local 'astral' library.
        """
        times = daily_data.get('time', [])
        weather_codes = daily_data.get('weathercode', [])
        temp_max = daily_data.get('temperature_2m_max', [])
        temp_min = daily_data.get('temperature_2m_min', [])
        if units == "standard":
            temp_max = [T + 273.15 for T in temp_max]
            temp_min = [T + 273.15 for T in temp_min]

        forecast = []

        for i in range(0, len(times)): 
            dt = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc).astimezone(tz)
            day_label = dt.strftime("%a")

            code = weather_codes[i] if i < len(weather_codes) else 0
            weather_icon = self.map_weather_code_to_icon(code, is_day=1)
            weather_icon_path = self.get_icon_path(weather_icon)

            timestamp = int(dt.replace(hour=12, minute=0, second=0).timestamp())
            target_date: date = dt.date() + timedelta(days=1)

            try:
                phase_age = moon.phase(target_date)
                phase_name_north_hemi = get_moon_phase_name(phase_age)
                LUNAR_CYCLE_DAYS = 29.530588853
                phase_fraction = phase_age / LUNAR_CYCLE_DAYS
                illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
            except Exception as e:
                logger.error(f"Error calculating moon phase for {target_date}: {e}")
                illum_pct = 0
                phase_name_north_hemi = "newmoon"
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)

            forecast.append({
                "day": day_label,
                "high": int(temp_max[i]) if i < len(temp_max) else 0,
                "low": int(temp_min[i]) if i < len(temp_min) else 0,
                "icon": weather_icon_path,
                "moon_phase_pct": f"{illum_pct:.0f}",
                "moon_phase_icon": moon_icon_path
            })

        return forecast

    def parse_hourly(self, hourly_forecast, tz, time_format, units, daily_forecast):
        hourly = []
        icon_codes_to_preserve = ["01", "02", "10"]
        
        sun_map = {}
        for day in daily_forecast:
            day_date = datetime.fromtimestamp(day['dt'], tz=timezone.utc).astimezone(tz).date()
            sun_map[day_date] = (day['sunrise'], day['sunset'])
        
        for hour in hourly_forecast[:24]:
            dt_epoch = hour.get('dt')
            dt = datetime.fromtimestamp(dt_epoch, tz=timezone.utc).astimezone(tz)
            rain_mm = hour.get("rain", {}).get("1h", 0.0)
            snow_mm = hour.get("snow", {}).get("1h", 0.0)
            total_precip_mm = rain_mm + snow_mm
            sunrise, sunset = sun_map.get(dt.date(), (0, 0))
        
            is_day = sunrise <= dt_epoch < sunset
            suffix = 'd' if is_day else 'n'
        
            raw_icon = hour.get("weather", [{}])[0].get("icon", "01d")
            icon_base = raw_icon[:2]
            icon_name = f"{icon_base}{suffix}" if icon_base in icon_codes_to_preserve else f"{icon_base}d"
            
            if units == "imperial":
                precip_value = total_precip_mm / 25.4
            else:
                precip_value = total_precip_mm 
            hour_forecast = {
                "time": self.format_time(dt, time_format, hour_only=True),
                "temperature": int(hour.get("temp")),
                "precipitation": hour.get("pop"),
                "rain": round(precip_value, 2),
                "icon": self.get_icon_path({icon_name})
            }
            hourly.append(hour_forecast)
        return hourly

    def parse_open_meteo_hourly(self, hourly_data, units, tz, time_format, sunrises, sunsets):
        hourly = []
        times = hourly_data.get('time', [])
        temperatures = hourly_data.get('temperature_2m', [])
        if units == "standard":
            temperatures = [temperature + 273.15 for temperature in temperatures]
        precipitation_probabilities = hourly_data.get('precipitation_probability', [])
        rain = hourly_data.get('precipitation', [])
        codes = hourly_data.get('weather_code', [])
        
        sun_map = {}
        for sr_s, ss_s in zip(sunrises, sunsets):
            sr_dt = datetime.fromisoformat(sr_s).astimezone(tz)
            ss_dt = datetime.fromisoformat(ss_s).astimezone(tz)
            sun_map[sr_dt.date()] = (sr_dt, ss_dt)
        
        current_time_in_tz = datetime.now(tz)
        start_index = 0
        for i, time_str in enumerate(times):
            try:
                dt_hourly = datetime.fromisoformat(time_str).astimezone(tz)
                if dt_hourly.date() == current_time_in_tz.date() and dt_hourly.hour >= current_time_in_tz.hour:
                    start_index = i
                    break
                if dt_hourly.date() > current_time_in_tz.date():
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} in hourly data.")
                continue

        sliced_times = times[start_index:]
        sliced_temperatures = temperatures[start_index:]
        sliced_precipitation_probabilities = precipitation_probabilities[start_index:]
        sliced_rain = rain[start_index:]
        sliced_codes = codes[start_index:]

        for i in range(min(24, len(sliced_times))):
            dt = datetime.fromisoformat(sliced_times[i]).astimezone(tz)
            sunrise, sunset = sun_map.get(dt.date(), (None, None))
            is_day = 0
            if sunrise and sunset:
                is_day = 1 if sunrise <= dt < sunset else 0
            code = sliced_codes[i] if i < len(sliced_codes) else 0
            icon_name = self.map_weather_code_to_icon(code, is_day)
            hour_forecast = {
                "time": self.format_time(dt, time_format, True),
                "temperature": int(sliced_temperatures[i]) if i < len(sliced_temperatures) else 0,
                "precipitation": (sliced_precipitation_probabilities[i] / 100) if i < len(sliced_precipitation_probabilities) else 0,
                "rain": (sliced_rain[i]) if i < len(sliced_rain) else 0,
                "icon": self.get_icon_path(icon_name)
            }
            hourly.append(hour_forecast)
        return hourly

    def parse_data_points(self, weather, air_quality, tz, units, time_format):
        data_points = []
        sunrise_epoch = weather.get('current', {}).get("sunrise")

        if sunrise_epoch:
            sunrise_dt = datetime.fromtimestamp(sunrise_epoch, tz=timezone.utc).astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": self.get_icon_path('sunrise')
            })
        else:
            logger.error(f"Sunrise not found in OpenWeatherMap response, this is expected for polar areas in midnight sun and polar night periods.")

        sunset_epoch = weather.get('current', {}).get("sunset")
        if sunset_epoch:
            sunset_dt = datetime.fromtimestamp(sunset_epoch, tz=timezone.utc).astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": self.get_icon_path('sunset')
            })
        else:
            logger.error(f"Sunset not found in OpenWeatherMap response, this is expected for polar areas in midnight sun and polar night periods.")

        wind_deg = weather.get('current', {}).get("wind_deg", 0)
        wind_arrow = self.get_wind_arrow(wind_deg)
        data_points.append({
            "label": "Wind",
            "measurement": weather.get('current', {}).get("wind_speed"),
            "unit": UNITS[units]["speed"],
            "icon": self.get_icon_path('wind'),
            "arrow": wind_arrow
        })

        data_points.append({
            "label": "Humidity",
            "measurement": weather.get('current', {}).get("humidity"),
            "unit": '%',
            "icon": self.get_icon_path('humidity')
        })

        data_points.append({
            "label": "Pressure",
            "measurement": weather.get('current', {}).get("pressure"),
            "unit": 'hPa',
            "icon": self.get_icon_path('pressure')
        })

        data_points.append({
            "label": "UV Index",
            "measurement": weather.get('current', {}).get("uvi"),
            "unit": '',
            "icon": self.get_icon_path('uvi')
        })

        visibility = weather.get('current', {}).get("visibility")
        if units == "imperial":
            # convert from m to mi
            visibility /= 1609.
            at_max_visibility = visibility >= 6.2
        else:
            # convert from m to km
            visibility /= 1000.
            at_max_visibility = visibility >= 10
        visibility_str = f"{visibility:.1f}"
        if at_max_visibility:
            visibility_str = u"\u2265" + visibility_str
        data_points.append({
            "label": "Visibility",
            "measurement": visibility_str,
            "unit": UNITS[units]["distance"],
            "icon": self.get_icon_path('visibility')
        })

        aqi = air_quality.get('list', [])[0].get("main", {}).get("aqi")
        data_points.append({
            "label": "Air Quality",
            "measurement": aqi,
            "unit": ["Good", "Fair", "Moderate", "Poor", "Very Poor"][int(aqi)-1],
            "icon": self.get_icon_path('aqi')
        })

        return data_points

    def parse_open_meteo_data_points(self, weather_data, aqi_data, units, tz, time_format):
        """Parses current data points from Open-Meteo API response."""
        data_points = []
        daily_data = weather_data.get('daily', {})
        current_data = weather_data.get('current', {})
        hourly_data = weather_data.get('hourly', {})

        current_time = datetime.now(tz)

        # Sunrise
        sunrise_times = daily_data.get('sunrise', [])
        if sunrise_times:
            sunrise_dt = datetime.fromisoformat(sunrise_times[0]).astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": self.get_icon_path('sunrise')
            })
        else:
            logger.error(f"Sunrise not found in Open-Meteo response, this is expected for polar areas in midnight sun and polar night periods.")

        # Sunset
        sunset_times = daily_data.get('sunset', [])
        if sunset_times:
            sunset_dt = datetime.fromisoformat(sunset_times[0]).astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": self.get_icon_path('sunset')
            })
        else:
            logger.error(f"Sunset not found in Open-Meteo response, this is expected for polar areas in midnight sun and polar night periods.")

        # Wind
        wind_speed = current_data.get("windspeed", 0)
        wind_deg = current_data.get("winddirection", 0)
        wind_arrow = self.get_wind_arrow(wind_deg)
        wind_unit = UNITS[units]["speed"]
        data_points.append({
            "label": "Wind", "measurement": wind_speed, "unit": wind_unit,
            "icon": self.get_icon_path('wind'), "arrow": wind_arrow
        })

        # Humidity
        current_humidity = "N/A"
        humidity_hourly_times = hourly_data.get('time', [])
        humidity_values = hourly_data.get('relative_humidity_2m', [])
        for i, time_str in enumerate(humidity_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_humidity = int(humidity_values[i])
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for humidity.")
                continue
        data_points.append({
            "label": "Humidity", "measurement": current_humidity, "unit": '%',
            "icon": self.get_icon_path('humidity')
        })

        # Pressure
        current_pressure = "N/A"
        pressure_hourly_times = hourly_data.get('time', [])
        pressure_values = hourly_data.get('surface_pressure', [])
        for i, time_str in enumerate(pressure_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_pressure = int(pressure_values[i])
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for pressure.")
                continue
        data_points.append({
            "label": "Pressure", "measurement": current_pressure, "unit": 'hPa',
            "icon": self.get_icon_path('pressure')
        })

        # UV Index
        uv_index_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        uv_index_values = aqi_data.get('hourly', {}).get('uv_index', [])
        current_uv_index = "N/A"
        for i, time_str in enumerate(uv_index_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_uv_index = uv_index_values[i]
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for UV Index.")
                continue
        data_points.append({
            "label": "UV Index", "measurement": current_uv_index, "unit": '',
            "icon": self.get_icon_path('uvi')
        })

        # Visibility
        current_visibility = "N/A"
        visibility_hourly_times = hourly_data.get('time', [])
        visibility_values = hourly_data.get('visibility', [])
        if units == "imperial":
            visibility_conversion = 1/5280.     # ft to mi
            visibility_max = 6.2                # mi
        else:
            visibility_conversion = 0.001       # m to km
            visibility_max = 10.                # km
        for i, time_str in enumerate(visibility_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_visibility = visibility_values[i]*visibility_conversion
                    at_max_visibility = current_visibility >= visibility_max
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for visibility.")
                continue
        visibility_str = f"{current_visibility:.1f}"
        if at_max_visibility:
            visibility_str = u"\u2265" + visibility_str
        data_points.append({
            "label": "Visibility", 
            "measurement": visibility_str, 
            "unit": UNITS[units]["distance"],
            "icon": self.get_icon_path('visibility')
        })

        # Air Quality
        aqi_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        aqi_values = aqi_data.get('hourly', {}).get('european_aqi', [])
        current_aqi = "N/A"
        for i, time_str in enumerate(aqi_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_aqi = round(aqi_values[i], 1)
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for AQI.")
                continue
        scale = ""
        if current_aqi and current_aqi != "N/A":
            scale = ["Good","Fair","Moderate","Poor","Very Poor","Ext Poor"][min(current_aqi//20,5)]
        data_points.append({
            "label": "Air Quality", "measurement": current_aqi,
            "unit": scale, "icon": self.get_icon_path('aqi')
        })

        return data_points

    def get_wind_arrow(self, wind_deg: float) -> str:
        DIRECTIONS = [
            ("↓", 22.5),    # North (N)
            ("↙", 67.5),    # North-East (NE)
            ("←", 112.5),   # East (E)
            ("↖", 157.5),   # South-East (SE)
            ("↑", 202.5),   # South (S)
            ("↗", 247.5),   # South-West (SW)
            ("→", 292.5),   # West (W)
            ("↘", 337.5),   # North-West (NW)
            ("↓", 360.0)    # Wrap back to North
        ]
        wind_deg = wind_deg % 360
        for arrow, upper_bound in DIRECTIONS:
            if wind_deg < upper_bound:
                return arrow

        return "↑"

    def get_weather_data(self, api_key, units, lat, long):
        url = WEATHER_URL.format(lat=lat, long=long, units=units, api_key=api_key)
        response = requests.get(url, timeout=30)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve weather data: {response.content}")
            raise RuntimeError("Failed to retrieve weather data.")

        return response.json()

    def get_air_quality(self, api_key, lat, long):
        url = AIR_QUALITY_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url, timeout=30)

        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to get air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve air quality data.")

        return response.json()

    def get_location(self, api_key, lat, long):
        url = GEOCODING_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url, timeout=30)

        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to get location: {response.content}")
            raise RuntimeError("Failed to retrieve location.")

        location_data = response.json()[0]
        location_str = f"{location_data.get('name')}, {location_data.get('state', location_data.get('country'))}"

        return location_str

    def get_open_meteo_data(self, lat, long, units, forecast_days):
        unit_params = OPEN_METEO_UNIT_PARAMS[units]
        url = OPEN_METEO_FORECAST_URL.format(lat=lat, long=long, forecast_days=forecast_days) + f"&{unit_params}"
        response = requests.get(url, timeout=30)

        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve Open-Meteo weather data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo weather data.")
        
        return response.json()

    def get_open_meteo_air_quality(self, lat, long):
        url = OPEN_METEO_AIR_QUALITY_URL.format(lat=lat, long=long)
        response = requests.get(url, timeout=30)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve Open-Meteo air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo air quality data.")
        
        return response.json()
    
    def _safe_float(self, value):
        try:
            return float(value)
        except Exception:
            return None

    def get_ip_geolocation(self):
        try:
            response = requests.get(IP_GEO_URL, timeout=10)
            if not 200 <= response.status_code < 300:
                logger.warning(f"IP geolocation failed: {response.status_code}")
                return None
            data = response.json()
            lat = data.get("latitude") or data.get("lat")
            lon = data.get("longitude") or data.get("lon")
            if lat is None or lon is None:
                return None
            return {
                "lat": float(lat),
                "lon": float(lon),
                "city": data.get("city"),
                "region": data.get("region"),
                "country": data.get("country_name") or data.get("country"),
                "timezone": data.get("timezone")
            }
        except Exception as e:
            logger.warning(f"IP geolocation exception: {e}")
            return None

    def _meteoswiss_cache_path(self):
        cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, "meteoswiss_cache.json")

    def _load_meteoswiss_cache(self):
        try:
            path = self._meteoswiss_cache_path()
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("generated_at")
            if ts:
                age = datetime.utcnow() - datetime.fromisoformat(ts)
                if age.total_seconds() > METEOSWISS_CACHE_TTL_SECONDS:
                    return None
            return data
        except Exception:
            return None

    def _save_meteoswiss_cache(self, payload):
        try:
            payload["generated_at"] = datetime.utcnow().isoformat()
            path = self._meteoswiss_cache_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to write MeteoSwiss cache: {e}")

    def _haversine_km(self, lat1, lon1, lat2, lon2):
        r = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _find_nearest_point(self, lat, lon):
        response = requests.get(METEOSWISS_LOCAL_FORECAST_META_POINT_URL, timeout=30)
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Failed to retrieve MeteoSwiss point metadata.")
        response.encoding = "latin-1"
        reader = csv.DictReader(StringIO(response.text), delimiter=";")
        best = None
        best_dist = None
        for row in reader:
            try:
                p_lat = float(row.get("point_coordinates_wgs84_lat"))
                p_lon = float(row.get("point_coordinates_wgs84_lon"))
            except Exception:
                continue
            dist = self._haversine_km(lat, lon, p_lat, p_lon)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = row
        if not best:
            raise RuntimeError("Failed to resolve nearest MeteoSwiss point.")
        return best

    def _find_nearest_station(self, lat, lon):
        response = requests.get(METEOSWISS_SMN_META_STATIONS_URL, timeout=30)
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Failed to retrieve MeteoSwiss station metadata.")
        response.encoding = "latin-1"
        reader = csv.DictReader(StringIO(response.text), delimiter=";")
        best = None
        best_dist = None
        for row in reader:
            try:
                s_lat = float(row.get("station_coordinates_wgs84_lat"))
                s_lon = float(row.get("station_coordinates_wgs84_lon"))
            except Exception:
                continue
            dist = self._haversine_km(lat, lon, s_lat, s_lon)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = row
        return best

    def _get_local_forecast_assets(self):
        url = f"{METEOSWISS_STAC_BASE}/{METEOSWISS_LOCAL_FORECAST_COLLECTION}/items?limit=1"
        response = requests.get(url, timeout=30)
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Failed to retrieve MeteoSwiss STAC items.")
        data = response.json()
        features = data.get("features", [])
        if not features:
            raise RuntimeError("No MeteoSwiss STAC items found.")
        feature = features[0]
        assets = feature.get("assets", {})
        item_updated = feature.get("properties", {}).get("updated") or feature.get("properties", {}).get("datetime")
        return assets, item_updated

    def _get_asset_url(self, assets, param):
        suffix = f".{param}.csv"
        for key, asset in assets.items():
            if key.endswith(suffix):
                return asset.get("href")
        return None

    def _parse_local_forecast_param(self, url, point_id, point_type_id, param_name, tz):
        response = requests.get(url, timeout=60)
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Failed to retrieve MeteoSwiss parameter {param_name}.")
        response.encoding = "latin-1"
        reader = csv.DictReader(StringIO(response.text), delimiter=";")
        series = []
        pid = str(point_id)
        ptid = str(point_type_id)
        for row in reader:
            if row.get("point_id") != pid or row.get("point_type_id") != ptid:
                continue
            raw_time = row.get("Date")
            raw_value = row.get(param_name)
            if not raw_time or raw_value in (None, ""):
                continue
            try:
                dt = datetime.strptime(raw_time, "%Y%m%d%H%M")
                dt = tz.localize(dt)
                series.append((dt, float(raw_value)))
            except Exception:
                continue
        return series

    def _get_smn_current(self, station_abbr):
        if not station_abbr:
            return {}
        station = station_abbr.lower()
        url = f"https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/{station}/ogd-smn_{station}_h_now.csv"
        response = requests.get(url, timeout=30)
        if not 200 <= response.status_code < 300:
            logger.warning("Failed to retrieve MeteoSwiss station data.")
            return {}
        response.encoding = "latin-1"
        reader = csv.reader(StringIO(response.text), delimiter=";")
        header = next(reader, None)
        last_row = None
        for row in reader:
            if row and row[0]:
                last_row = row
        if not header or not last_row:
            return {}
        data = dict(zip(header, last_row))
        return data

    def _map_meteoswiss_icon(self, symbol_code, is_day=True):
        try:
            code = int(symbol_code)
        except Exception:
            return self.get_icon_path("01d")

        # Prefer official MeteoSwiss SVG icons (downloaded by install/download_icons.sh).
        # Day codes: 1-42 stored as msw_{code}.svg
        # Night codes: 101-142 stored as msw_{code}.svg
        # If not available, fall back through METEOSWISS_ICON_MAP to bundled icons.
        msw_code = code if is_day else (code + 100 if code <= 42 else code)
        msw_svg = self.get_plugin_dir(f"icons/msw_{msw_code}.svg")
        import os as _os
        if _os.path.isfile(msw_svg):
            return msw_svg

        # Fallback: internal OWM-style icon
        icon = METEOSWISS_ICON_MAP.get(code, "04d")
        if not is_day:
            icon = METEOSWISS_ICON_NIGHT_MAP.get(icon, icon)
        return self.get_icon_path(icon)

    def _convert_temperature(self, value_c, units):
        if value_c is None:
            return None
        if units == "imperial":
            return (value_c * 9 / 5) + 32
        if units == "standard":
            return value_c + 273.15
        return value_c

    def _convert_precip(self, value_mm, units):
        if value_mm is None:
            return None
        if units == "imperial":
            return value_mm / 25.4
        return value_mm

    def _convert_wind_speed(self, value_kmh, units):
        if value_kmh is None:
            return None
        if units == "imperial":
            return value_kmh * 0.621371
        return value_kmh

    def _get_sun_times(self, lat, lon, day, tz):
        try:
            observer = Observer(latitude=lat, longitude=lon)
            s = sun(observer, date=day, tzinfo=tz)
            return s.get("sunrise"), s.get("sunset")
        except Exception:
            return None, None

    def get_meteoswiss_data(self, lat, lon, tz, forecast_days):
        point = self._find_nearest_point(lat, lon)
        point_id = point.get("point_id")
        point_type_id = point.get("point_type_id")
        point_name = point.get("point_name")
        station_abbr = point.get("station_abbr") or ""
        station_name = None
        if not station_abbr:
            station_meta = self._find_nearest_station(lat, lon)
            if station_meta:
                station_abbr = station_meta.get("station_abbr") or ""
                station_name = station_meta.get("station_name")

        assets, item_updated = self._get_local_forecast_assets()
        cache = self._load_meteoswiss_cache()
        if cache and cache.get("point_id") == point_id and cache.get("item_updated") == item_updated:
            return cache.get("data", {})

        temp_url = self._get_asset_url(assets, "tre200h0")
        precip_url = self._get_asset_url(assets, "rre150h0")
        prob_url = self._get_asset_url(assets, "rp0003i0")
        symbol_url = self._get_asset_url(assets, "jww003i0")

        if not all([temp_url, precip_url, prob_url, symbol_url]):
            raise RuntimeError("Missing MeteoSwiss forecast parameters.")

        temp_series = self._parse_local_forecast_param(temp_url, point_id, point_type_id, "tre200h0", tz)
        precip_series = self._parse_local_forecast_param(precip_url, point_id, point_type_id, "rre150h0", tz)
        prob_series = self._parse_local_forecast_param(prob_url, point_id, point_type_id, "rp0003i0", tz)
        symbol_series = self._parse_local_forecast_param(symbol_url, point_id, point_type_id, "jww003i0", tz)

        temp_map = {dt: val for dt, val in temp_series}
        precip_map = {dt: val for dt, val in precip_series}
        prob_map = {dt: val for dt, val in prob_series}
        symbol_map = {dt: val for dt, val in symbol_series}

        now = datetime.now(tz)
        hourly = []
        for dt in sorted(temp_map.keys()):
            if dt < now:
                continue
            hourly.append({
                "time": dt,
                "temperature_c": temp_map.get(dt),
                "precip_mm": precip_map.get(dt),
                "precip_prob": prob_map.get(dt),
                "symbol": symbol_map.get(dt)
            })
            if len(hourly) >= 24:
                break

        # Determine current time slot — use closest slot to now (not just last <= now)
        current_slot = None
        min_diff = None
        for dt in sorted(temp_map.keys()):
            diff = abs((dt - now).total_seconds())
            if min_diff is None or diff < min_diff:
                min_diff = diff
                current_slot = dt

        current = {
            "time": current_slot or now,
            "temperature_c": temp_map.get(current_slot) if current_slot else None,
            "precip_mm": precip_map.get(current_slot) if current_slot else None,
            "precip_prob": prob_map.get(current_slot) if current_slot else None,
            "symbol": symbol_map.get(current_slot) if current_slot else None
        }

        # Daily min/max from hourly temps
        today = now.date()
        daily_map = {}
        for dt, temp in temp_series:
            if dt.date() < today:
                continue
            if temp is None:
                continue
            day = dt.date()
            if day not in daily_map:
                daily_map[day] = {"min": temp, "max": temp}
            else:
                daily_map[day]["min"] = min(daily_map[day]["min"], temp)
                daily_map[day]["max"] = max(daily_map[day]["max"], temp)

        # Daily icon (closest to 12:00)
        daily_symbol = {}
        for dt, code in symbol_series:
            if dt.date() < today:
                continue
            day = dt.date()
            target = datetime(dt.year, dt.month, dt.day, 12, 0, tzinfo=dt.tzinfo)
            diff = abs((dt - target).total_seconds())
            if day not in daily_symbol or diff < daily_symbol[day]["diff"]:
                daily_symbol[day] = {"code": code, "diff": diff}

        daily = []
        for day in sorted(daily_map.keys()):
            daily.append({
                "date": day,
                "min_c": daily_map[day]["min"],
                "max_c": daily_map[day]["max"],
                "symbol": daily_symbol.get(day, {}).get("code")
            })

        # Enrich with live station observations if available
        # SMN stations give real measurements; prefer them over forecast values
        station_data = self._get_smn_current(station_abbr)
        if station_data:
            obs_temp = self._safe_float(station_data.get("tre200h0"))
            if obs_temp is not None:
                current["temperature_c"] = obs_temp
            # fu3010h0 is in m/s — convert to km/h for consistency with MeteoSwiss display
            wind_ms = self._safe_float(station_data.get("fu3010h0"))
            if wind_ms is not None:
                current["wind_kmh"] = wind_ms * 3.6
            wind_dir = self._safe_float(station_data.get("dkl010h0"))
            if wind_dir is not None:
                current["wind_dir"] = wind_dir
            humidity = self._safe_float(station_data.get("ure200h0"))
            if humidity is not None:
                current["humidity"] = humidity
            pressure = (self._safe_float(station_data.get("pp0qffh0"))
                        or self._safe_float(station_data.get("prestah0")))
            if pressure is not None:
                current["pressure"] = pressure

        data = {
            "location_name": point_name or station_name or station_abbr,
            "current": current,
            "hourly": hourly,
            "daily": daily
        }

        self._save_meteoswiss_cache({
            "point_id": point_id,
            "item_updated": item_updated,
            "data": data
        })

        return data

    def parse_meteoswiss_data(self, data, tz, units, time_format, lat, lon):
        current = data.get("current", {})
        daily = data.get("daily", [])
        hourly = data.get("hourly", [])

        current_dt = current.get("time") or datetime.now(tz)
        sunrise_dt, sunset_dt = self._get_sun_times(lat, lon, current_dt.date(), tz)
        is_day = True
        if sunrise_dt and sunset_dt:
            is_day = sunrise_dt <= current_dt <= sunset_dt

        current_temp = self._convert_temperature(current.get("temperature_c"), units)
        current_feels = current_temp
        temp_unit = "°C" if units == "metric" else "°F" if units == "imperial" else "K"

        current_icon = self._map_meteoswiss_icon(current.get("symbol"), is_day)

        forecast = []
        for day_info in daily:
            dt = tz.localize(datetime.combine(day_info["date"], datetime.min.time()))
            day_label = dt.strftime("%a")
            tmax = self._convert_temperature(day_info.get("max_c"), units)
            tmin = self._convert_temperature(day_info.get("min_c"), units)
            icon = self._map_meteoswiss_icon(day_info.get("symbol"), True)

            try:
                phase_age = moon.phase(day_info["date"])
                phase_name_north_hemi = get_moon_phase_name(phase_age)
                LUNAR_CYCLE_DAYS = 29.530588853
                phase_fraction = phase_age / LUNAR_CYCLE_DAYS
                illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
            except Exception:
                illum_pct = 0
                phase_name_north_hemi = "newmoon"
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)

            forecast.append({
                "day": day_label,
                "high": int(tmax) if tmax is not None else 0,
                "low": int(tmin) if tmin is not None else 0,
                "icon": icon,
                "moon_phase_pct": f"{illum_pct:.0f}",
                "moon_phase_icon": moon_icon_path
            })

        # Ensure at least one forecast entry for today
        if not forecast:
            forecast.append({"day": current_dt.strftime("%a"), "high": 0, "low": 0, "icon": current_icon})

        hourly_forecast = []
        for hour in hourly:
            dt = hour.get("time")
            if not dt:
                continue
            sunrise_h, sunset_h = self._get_sun_times(lat, lon, dt.date(), tz)
            hour_is_day = True
            if sunrise_h and sunset_h:
                hour_is_day = sunrise_h <= dt <= sunset_h
            icon = self._map_meteoswiss_icon(hour.get("symbol"), hour_is_day)
            temp = self._convert_temperature(hour.get("temperature_c"), units)
            precip_prob = hour.get("precip_prob")
            precip_prob = (precip_prob / 100.0) if precip_prob is not None else 0
            rain = self._convert_precip(hour.get("precip_mm"), units) or 0
            hourly_forecast.append({
                "time": self.format_time(dt, time_format, True),
                "temperature": int(temp) if temp is not None else 0,
                "precipitation": precip_prob,
                "rain": rain,
                "icon": icon
            })

        # Data points
        data_points = []
        sunrise, sunset = self._get_sun_times(lat, lon, current_dt.date(), tz)
        if sunrise:
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise.strftime('%p'),
                "icon": self.get_icon_path('sunrise')
            })
        if sunset:
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset.strftime('%p'),
                "icon": self.get_icon_path('sunset')
            })

        wind_speed = self._convert_wind_speed(current.get("wind_kmh"), units)
        wind_dir = current.get("wind_dir")
        if wind_speed is not None:
            wind_unit = "mph" if units == "imperial" else "km/h"
            wind_arrow = self.get_wind_arrow(wind_dir or 0)
            data_points.append({
                "label": "Wind",
                "measurement": round(wind_speed, 1),
                "unit": wind_unit,
                "icon": self.get_icon_path('wind'),
                "arrow": wind_arrow
            })

        humidity = current.get("humidity")
        if humidity is not None:
            data_points.append({
                "label": "Humidity",
                "measurement": round(humidity, 0),
                "unit": '%',
                "icon": self.get_icon_path('humidity')
            })

        pressure = current.get("pressure")
        if pressure is not None:
            data_points.append({
                "label": "Pressure",
                "measurement": round(pressure, 1),
                "unit": 'hPa',
                "icon": self.get_icon_path('pressure')
            })

        template_params = {
            "current_date": current_dt.strftime("%A, %B %d"),
            "current_day_icon": current_icon,
            "current_temperature": str(round(current_temp)) if current_temp is not None else "0",
            "feels_like": str(round(current_feels)) if current_feels is not None else "0",
            "temperature_unit": temp_unit,
            "units": units,
            "time_format": time_format,
            "forecast": forecast,
            "data_points": data_points,
            "hourly_forecast": hourly_forecast
        }

        return template_params

    def format_time(self, dt, time_format, hour_only=False, include_am_pm=True):
        """Format datetime based on 12h or 24h preference"""
        if time_format == "24h":
            return dt.strftime("%H:00" if hour_only else "%H:%M")
        
        if include_am_pm:
            fmt = "%I %p" if hour_only else "%I:%M %p"
        else:
            fmt = "%I" if hour_only else "%I:%M"

        return dt.strftime(fmt).lstrip("0")
    
    def parse_timezone(self, weatherdata):
        """Parse timezone from weather data"""
        if 'timezone' in weatherdata:
            logger.info(f"Using timezone from weather data: {weatherdata['timezone']}")
            return pytz.timezone(weatherdata['timezone'])
        else:
            logger.error("Failed to retrieve Timezone from weather data")
            raise RuntimeError("Timezone not found in weather data.")
