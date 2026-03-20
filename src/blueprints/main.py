from flask import Blueprint, request, jsonify, current_app, render_template, send_file
import os
import pytz
from datetime import datetime

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())

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

    last_refresh = refresh_info.refresh_time
    seconds_until_refresh = None
    if last_refresh:
        try:
            tz_str = device_config.get_config("timezone", default="UTC")
            now = datetime.now(pytz.timezone(tz_str))
            last_dt = datetime.fromisoformat(last_refresh)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=pytz.UTC)
            elapsed = (now - last_dt).total_seconds()
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

    tz_str = device_config.get_config("timezone", default="UTC")
    current_dt = datetime.now(pytz.timezone(tz_str))

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

    return jsonify({"success": True, "message": "Display updated"})


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