import inspect
import logging
from inky.auto import auto
from display.abstract_display import AbstractDisplay


logger = logging.getLogger(__name__)

class InkyDisplay(AbstractDisplay):

    """
    Handles the Inky e-paper display.

    This class initializes and manages interactions with the Inky display,
    ensuring proper image rendering and configuration storage.

    The Inky display driver supports auto configuration.
    """
   
    def initialize_display(self):
        
        """
        Initializes the Inky display device.

        Sets the display border and stores the display resolution in the device configuration.

        Raises:
            ValueError: If the resolution cannot be retrieved or stored.
        """
        
        self.inky_display = auto()
        self.inky_display.set_border(self.inky_display.BLACK)

        # store display resolution in device config
        if not self.device_config.get_config("resolution"):
            self.device_config.update_value(
                "resolution",
                [int(self.inky_display.width), int(self.inky_display.height)], 
                write=True)

    def display_image(self, image, image_settings=[]):
        
        """
        Displays the provided image on the Inky display.

        The image has been processed by adjusting orientation and resizing 
        before being sent to the display.

        Args:
            image (PIL.Image): The image to be displayed.
            image_settings (list, optional): Additional settings to modify image rendering.

        Raises:
            ValueError: If no image is provided.
        """

        logger.info("Displaying image to Inky display.")
        if not image:
            raise ValueError(f"No image provided.")

        # Display the image on the Inky display
        inky_saturation = self.device_config.get_config('image_settings').get("inky_saturation", 0.0)
        logger.info(f"Inky Saturation: {inky_saturation}")
        self.inky_display.set_image(image, saturation=inky_saturation)
        self.inky_display.show()

    def display_partial_image(self, image, image_settings=[]):
        """
        Displays the image using hardware partial refresh on supported Inky displays.

        Checks whether the Inky driver's show() method accepts an update_mode parameter
        and, if so, tries to use UPDATE_MODE_PARTIAL for a fast no-flicker update.
        Falls back to a full refresh if the driver does not support partial mode.

        Args:
            image (PIL.Image): The image to be displayed.
            image_settings (list, optional): Additional settings to modify image rendering.
        """
        logger.info("Attempting Inky partial refresh.")
        if not image:
            raise ValueError("No image provided.")

        inky_saturation = self.device_config.get_config('image_settings').get("inky_saturation", 0.0)
        self.inky_display.set_image(image, saturation=inky_saturation)

        # Check if this Inky driver supports update_mode (Pimoroni Inky >= 1.5 on compatible panels)
        try:
            sig = inspect.signature(self.inky_display.show)
            if "update_mode" in sig.parameters:
                from inky.inky_uc8159 import UPDATE_MODE_PARTIAL
                logger.info("Inky partial refresh supported — using UPDATE_MODE_PARTIAL.")
                self.inky_display.show(update_mode=UPDATE_MODE_PARTIAL)
                return
        except Exception as e:
            logger.warning(f"Inky partial mode not available: {e}. Falling back to full refresh.")

        # Fallback: full refresh
        logger.info("Inky partial refresh not supported, performing full refresh.")
        self.inky_display.show()
