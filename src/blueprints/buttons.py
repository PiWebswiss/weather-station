"""
blueprints/buttons.py — Routes for physical button configuration.

Register in inkypi.py:
    from blueprints.buttons import buttons_bp
    app.register_blueprint(buttons_bp)
"""
from flask import Blueprint, render_template, request, current_app, jsonify
from button_handler import BUTTON_PINS, AVAILABLE_ACTIONS

buttons_bp = Blueprint("buttons", __name__)


@buttons_bp.route("/settings/buttons", methods=["GET"])
def button_settings():
    device_config = current_app.config["DEVICE_CONFIG"]
    current = {
        btn: device_config.get_config(f"button_{btn}", default="nothing")
        for btn in BUTTON_PINS
    }
    return render_template(
        "button_settings.html",
        buttons=list(BUTTON_PINS.keys()),
        actions=AVAILABLE_ACTIONS,
        current=current,
    )


@buttons_bp.route("/settings/buttons/update", methods=["POST"])
def update_button_settings():
    device_config = current_app.config["DEVICE_CONFIG"]
    for btn in BUTTON_PINS:
        action = request.form.get(f"button_{btn}", "nothing")
        if action not in AVAILABLE_ACTIONS:
            action = "nothing"
        device_config.update_value(f"button_{btn}", action)

    device_config.write_config()

    # Notify refresh task of config change
    refresh_task = current_app.config.get("REFRESH_TASK")
    if refresh_task:
        refresh_task.signal_config_change()

    return jsonify({"status": "ok", "message": "Button settings saved."})
