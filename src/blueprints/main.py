from flask import Blueprint, request, jsonify, current_app, render_template, send_file
import os
import pytz
from datetime import datetime

main_bp = Blueprint("main", __name__)


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _get_timezone(device_config):
    timezone_name = device_config.get_config("timezone", default="UTC") or "UTC"
    try:
        return pytz.timezone(timezone_name)
    except Exception:
        return pytz.UTC


def _get_current_datetime(device_config):
    return datetime.now(_get_timezone(device_config))


def _resolve_last_update_datetime(device_config, fallback_dt=None):
    refresh_info = device_config.get_refresh_info()
    refresh_time = getattr(refresh_info, "refresh_time", None)
    if refresh_time:
        try:
            update_dt = datetime.fromisoformat(refresh_time)
            if update_dt.tzinfo is None:
                timezone = _get_timezone(device_config)
                if hasattr(timezone, "localize"):
                    update_dt = timezone.localize(update_dt)
                else:
                    update_dt = update_dt.replace(tzinfo=timezone)
            return update_dt
        except Exception:
            pass
    return fallback_dt or _get_current_datetime(device_config)


def _build_update_payload(device_config, message, updated_at=None):
    update_dt = _resolve_last_update_datetime(device_config, fallback_dt=updated_at)
    return {
        "success": True,
        "message": message,
        "updated_at": update_dt.isoformat(),
        "updated_at_display": update_dt.strftime("%H:%M"),
        "updated_at_long": update_dt.strftime("%A, %d %b %Y %H:%M"),
        "updated_timezone": getattr(update_dt.tzinfo, "zone", None) or (device_config.get_config("timezone", default="UTC") or "UTC"),
    }


def _get_clock_snapshot(device_config, current_dt=None):
    current_dt = current_dt or _get_current_datetime(device_config)
    offset = current_dt.utcoffset()
    timezone_name = getattr(current_dt.tzinfo, "zone", None) or (device_config.get_config("timezone", default="UTC") or "UTC")
    return {
        "timezone": timezone_name,
        "iso": current_dt.isoformat(),
        "timestamp_ms": int(current_dt.timestamp() * 1000),
        "offset_minutes": int(offset.total_seconds() // 60) if offset else 0,
        "hour": current_dt.hour,
        "minute": current_dt.minute,
        "second": current_dt.second,
        "weekday": current_dt.strftime("%A"),
        "day": current_dt.day,
        "month": current_dt.strftime("%b"),
        "year": current_dt.year,
    }


def _render_live_watch_image(device_config, face="analog", dark=False, show_seconds=True):
    from utils.image_utils import take_screenshot_html

    dimensions = device_config.get_resolution()
    if device_config.get_config("orientation") == "vertical":
        dimensions = dimensions[::-1]

    width, height = dimensions
    html = render_template(
        "live_render.html",
        width=width,
        height=height,
        config=device_config.get_config(),
        face=face,
        dark=dark,
        show_seconds=show_seconds,
        render_clock=_get_clock_snapshot(device_config),
    )
    image = take_screenshot_html(html, (width, height), timeout_ms=2500)
    if image is None:
        raise RuntimeError("Live watch render failed.")
    return image

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())

@main_bp.route('/live')
def live_watch():
    device_config = current_app.config['DEVICE_CONFIG']
    embed = request.args.get('embed', '').lower() in {'1', 'true', 'yes'}
    return render_template(
        'live.html',
        config=device_config.get_config(),
        embed=embed,
        server_clock=_get_clock_snapshot(device_config),
    )

@main_bp.route('/api/current_image')
def get_current_image():
    """Serve current_image.png with conditional request support (If-Modified-Since)."""
    image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'current_image.png')
    
    if not os.path.exists(image_path):
        return jsonify({"error": "Image not found"}), 404
    
    # Get the file's last modified time (truncate to seconds to match HTTP header precision)
    file_mtime = int(os.path.getmtime(image_path))
    last_modified = datetime.fromtimestamp(file_mtime)
    
    # Check If-Modified-Since header
    if_modified_since = request.headers.get('If-Modified-Since')
    if if_modified_since:
        try:
            # Parse the If-Modified-Since header
            client_mtime = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S %Z')
            client_mtime_seconds = int(client_mtime.timestamp())
            
            # Compare (both now in seconds, no sub-second precision)
            if file_mtime <= client_mtime_seconds:
                return '', 304
        except (ValueError, AttributeError):
            pass
    
    # Send the file with Last-Modified header
    response = send_file(image_path, mimetype='image/png')
    response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@main_bp.route('/api/status')
def get_status():
    """Return current display status and refresh countdown info."""
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_info = device_config.get_refresh_info()
    interval = device_config.get_config("plugin_cycle_interval_seconds", default=3600)
    current_dt = _get_current_datetime(device_config)
    current_clock = _get_clock_snapshot(device_config, current_dt=current_dt)

    last_refresh = refresh_info.refresh_time
    seconds_until_refresh = None
    if last_refresh:
        try:
            last_dt = datetime.fromisoformat(last_refresh)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=pytz.UTC)
            elapsed = (current_dt - last_dt).total_seconds()
            seconds_until_refresh = max(0, int(interval - elapsed))
        except Exception:
            pass

    return jsonify({
        "last_refresh_time": last_refresh,
        "plugin_cycle_interval_seconds": interval,
        "seconds_until_refresh": seconds_until_refresh,
        "current_plugin_id": refresh_info.plugin_id,
        "current_plugin_instance": refresh_info.plugin_instance,
        "active_playlist": refresh_info.playlist,
        "server_time_iso": current_clock["iso"],
        "server_time_epoch_ms": current_clock["timestamp_ms"],
        "server_time_offset_minutes": current_clock["offset_minutes"],
        "server_timezone": current_clock["timezone"],
    })


@main_bp.route('/api/refresh_now', methods=['POST'])
def refresh_now():
    """Force an immediate display refresh. Uses active playlist if configured,
    otherwise pushes the current preview image directly to the e-ink screen."""
    from refresh_task import PlaylistRefresh
    from PIL import Image
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']
    display_manager = current_app.config['DISPLAY_MANAGER']
    playlist_manager = device_config.get_playlist_manager()

    current_dt = _get_current_datetime(device_config)

    playlist = playlist_manager.determine_active_playlist(current_dt)
    if playlist and playlist.plugins:
        # Normal path: refresh via active playlist
        plugin_instance = playlist.get_next_plugin()
        try:
            refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        # No playlist configured — push whatever is in the current preview to the screen
        try:
            with Image.open(device_config.current_image_file) as img:
                display_manager.display_image(img.copy())
        except Exception as e:
            return jsonify({"error": f"Could not push image to display: {e}"}), 500

    return jsonify(_build_update_payload(device_config, "Display updated", updated_at=current_dt))


@main_bp.route('/api/render_live_watch', methods=['POST'])
def render_live_watch():
    from model import RefreshInfo
    from utils.image_utils import compute_image_hash

    device_config = current_app.config['DEVICE_CONFIG']
    display_manager = current_app.config['DISPLAY_MANAGER']
    payload = request.get_json(silent=True) or {}

    face = str(payload.get("face") or "analog").strip().lower()
    if face not in {"analog", "digital", "word"}:
        face = "analog"

    dark = _parse_bool(payload.get("dark"), default=False)
    show_seconds = _parse_bool(payload.get("seconds"), default=True)

    try:
        image = _render_live_watch_image(
            device_config,
            face=face,
            dark=dark,
            show_seconds=show_seconds,
        )
        display_manager.display_image(image.copy())

        current_dt = _get_current_datetime(device_config)
        device_config.refresh_info = RefreshInfo(
            refresh_type="Manual Update",
            plugin_id="live_watch",
            refresh_time=current_dt.isoformat(),
            image_hash=compute_image_hash(image),
        )
        device_config.write_config()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(_build_update_payload(device_config, "Live watch rendered to display", updated_at=current_dt))


@main_bp.route('/api/plugin_order', methods=['POST'])
def save_plugin_order():
    """Save the custom plugin order."""
    device_config = current_app.config['DEVICE_CONFIG']

    data = request.get_json() or {}
    order = data.get('order', [])

    if not isinstance(order, list):
        return jsonify({"error": "Order must be a list"}), 400

    device_config.set_plugin_order(order)

    return jsonify({"success": True})
