"""
button_handler.py — Physical button support for Pimoroni Inky displays.

Buttons A/B/C/D are mapped to GPIO pins (BCM numbering):
    A → GPIO 5
    B → GPIO 6
    C → GPIO 16
    D → GPIO 24

Each button can be configured to one of the AVAILABLE_ACTIONS.
Config keys stored in InkyPi device config: button_A, button_B, button_C, button_D.
Default action: "nothing".
"""
import logging
import threading

logger = logging.getLogger(__name__)

# GPIO pin number (BCM) for each physical button on Pimoroni Inky
BUTTON_PINS = {
    "A": 5,
    "B": 6,
    "C": 16,
    "D": 24,
}

# Human-readable labels shown in the settings UI
AVAILABLE_ACTIONS = {
    "nothing":     "Do nothing",
    "refresh":     "Force refresh display",
    "next_plugin": "Next plugin in playlist",
    "prev_plugin": "Previous plugin in playlist",
}


class ButtonHandler:
    """
    Listens for physical button presses and triggers configured actions.

    Usage (in inkypi.py, after creating refresh_task):

        from button_handler import ButtonHandler
        button_handler = ButtonHandler(device_config, refresh_task)
        button_handler.start()

    """

    def __init__(self, device_config, refresh_task):
        self.device_config = device_config
        self.refresh_task  = refresh_task
        self._gpio         = None

    def start(self):
        """Start listening for button presses. No-op if GPIO is unavailable (dev machine)."""
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            for btn, pin in BUTTON_PINS.items():
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(
                    pin,
                    GPIO.FALLING,
                    callback=lambda ch, b=btn: self._on_press(b),
                    bouncetime=300,
                )
            logger.info("Button handler started — A=%d B=%d C=%d D=%d",
                        BUTTON_PINS["A"], BUTTON_PINS["B"],
                        BUTTON_PINS["C"], BUTTON_PINS["D"])
        except (ImportError, RuntimeError) as e:
            logger.info("GPIO not available (%s) — button handler disabled.", e)

    def stop(self):
        """Release GPIO resources."""
        if self._gpio:
            try:
                self._gpio.cleanup()
            except Exception:
                pass

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_press(self, button: str):
        action = self.device_config.get_config(f"button_{button}", default="nothing")
        logger.info("Button %s pressed → action: %s", button, action)
        # Run in a separate thread so GPIO callback returns immediately
        threading.Thread(target=self._execute, args=(action,), daemon=True).start()

    def _execute(self, action: str):
        try:
            if action == "nothing":
                return

            if action == "refresh":
                self._do_refresh()

            elif action == "next_plugin":
                self._cycle_plugin(direction=1)

            elif action == "prev_plugin":
                self._cycle_plugin(direction=-1)

        except Exception:
            logger.exception("Error executing button action '%s'", action)

    def _do_refresh(self):
        """Force-refresh the current plugin."""
        playlist_mgr = self.device_config.get_playlist_manager()
        from datetime import datetime
        import pytz
        tz_str = self.device_config.get_config("timezone", default="UTC")
        current_dt = datetime.now(pytz.timezone(tz_str))

        playlist = playlist_mgr.determine_active_playlist(current_dt)
        if not playlist or not playlist.plugins:
            logger.info("Button refresh: no active playlist/plugin.")
            return

        plugin_instance = self._get_current_plugin_instance(playlist)
        if not plugin_instance:
            logger.info("Button refresh: no current plugin could be determined.")
            return

        try:
            playlist.current_plugin_index = playlist.plugins.index(plugin_instance)
        except ValueError:
            logger.info("Button refresh: current plugin is not present in the active playlist.")
            return

        from refresh_task import PlaylistRefresh
        self.refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))

    def _cycle_plugin(self, direction: int):
        """Advance (direction=1) or go back (direction=-1) in the playlist."""
        playlist_mgr = self.device_config.get_playlist_manager()
        from datetime import datetime
        import pytz
        tz_str = self.device_config.get_config("timezone", default="UTC")
        current_dt = datetime.now(pytz.timezone(tz_str))

        playlist = playlist_mgr.determine_active_playlist(current_dt)
        if not playlist or not playlist.plugins:
            logger.info("Button cycle: no active playlist/plugin.")
            return

        # Advance the playlist index
        if direction == 1:
            plugin_instance = playlist.get_next_plugin()
        else:
            # go back: step back 2 so get_next returns the previous one
            n = len(playlist.plugins)
            if n > 1:
                playlist.current_plugin_index = (
                    playlist.current_plugin_index - 2
                ) % n
            plugin_instance = playlist.get_next_plugin()

        from refresh_task import PlaylistRefresh
        self.refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))

    def _get_current_plugin_instance(self, playlist):
        """Return the plugin currently shown on the display for the active playlist."""
        refresh_info = self.device_config.get_refresh_info()
        if (
            refresh_info
            and refresh_info.playlist == playlist.name
            and refresh_info.plugin_id
            and refresh_info.plugin_instance
        ):
            current_plugin = playlist.find_plugin(refresh_info.plugin_id, refresh_info.plugin_instance)
            if current_plugin:
                return current_plugin

        if playlist.current_plugin_index is not None and playlist.plugins:
            return playlist.plugins[playlist.current_plugin_index % len(playlist.plugins)]

        return playlist.plugins[0] if playlist.plugins else None
