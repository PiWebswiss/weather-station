import logging
import os
import socket
import subprocess

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

FONT_FAMILIES = {
    "Dogica": [{
        "font-weight": "normal",
        "file": "dogicapixel.ttf"
    },{
        "font-weight": "bold",
        "file": "dogicapixelbold.ttf"
    }],
    "Jost": [{
        "font-weight": "normal",
        "file": "Jost.ttf"
    },{
        "font-weight": "bold",
        "file": "Jost-SemiBold.ttf"
    }],
    "Napoli": [{
        "font-weight": "normal",
        "file": "Napoli.ttf"
    }],
    "DS-Digital": [{
        "font-weight": "normal",
        "file": os.path.join("DS-DIGI", "DS-DIGI.TTF")
    }]
}

FONTS = {
    "ds-gigi": "DS-DIGI.TTF",
    "napoli": "Napoli.ttf",
    "jost": "Jost.ttf",
    "jost-semibold": "Jost-SemiBold.ttf"
}

def resolve_path(file_path):
    src_dir = os.getenv("SRC_DIR")
    if src_dir is None:
        # Default to the src directory
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    src_path = Path(src_dir)
    return str(src_path / file_path)

def get_ip_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
    return ip_address

def get_wifi_name():
    try:
        output = subprocess.check_output(['iwgetid', '-r']).decode('utf-8').strip()
        return output
    except subprocess.CalledProcessError:
        return None

def is_connected():
    """Check if the Raspberry Pi has an internet connection."""
    try:
        # Try to connect to Google's public DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

def get_font(font_name, font_size=50, font_weight="normal"):
    if font_name in FONT_FAMILIES:
        font_variants = FONT_FAMILIES[font_name]

        font_entry = next((entry for entry in font_variants if entry["font-weight"] == font_weight), None)
        if font_entry is None:
            font_entry = font_variants[0]  # Default to first available variant

        if font_entry:
            font_path = resolve_path(os.path.join("static", "fonts", font_entry["file"]))
            return ImageFont.truetype(font_path, font_size)
        else:
            logger.warning(f"Requested font weight not found: font_name={font_name}, font_weight={font_weight}")
    else:
        logger.warning(f"Requested font not found: font_name={font_name}")

    return None

def get_fonts():
    fonts_list = []
    for font_family, variants in FONT_FAMILIES.items():
        for variant in variants:
            fonts_list.append({
                "font_family": font_family,
                "url": resolve_path(os.path.join("static", "fonts", variant["file"])),
                "font_weight": variant.get("font-weight", "normal"),
                "font_style": variant.get("font-style", "normal"),
            })
    return fonts_list

def get_font_path(font_name):
    return resolve_path(os.path.join("static", "fonts", FONTS[font_name]))

def generate_startup_image(dimensions=(800,480)):
    bg_color = (244, 239, 232)
    panel_color = (255, 252, 247)
    border_color = (217, 207, 195)
    text_color = (31, 27, 22)
    accent_color = (45, 105, 98)
    muted_color = (102, 95, 86)
    width, height = dimensions

    hostname = socket.gethostname()
    try:
        ip = get_ip_address()
    except OSError:
        ip = None

    try:
        wifi_name = get_wifi_name()
    except Exception:
        wifi_name = None

    local_url = f"http://{hostname}.local"
    ip_url = f"http://{ip}" if ip else "IP address unavailable"

    image = Image.new("RGBA", dimensions, bg_color)
    image_draw = ImageDraw.Draw(image)

    outer_margin_x = int(width * 0.08)
    outer_margin_y = int(height * 0.10)
    panel_box = (
        outer_margin_x,
        outer_margin_y,
        width - outer_margin_x,
        height - outer_margin_y,
    )
    corner_radius = max(22, int(min(width, height) * 0.045))
    stroke_width = max(2, width // 360)
    image_draw.rounded_rectangle(
        panel_box,
        radius=corner_radius,
        fill=panel_color,
        outline=border_color,
        width=stroke_width,
    )

    title_font_size = int(width * 0.085)
    subtitle_font_size = int(width * 0.032)
    label_font_size = int(width * 0.018)
    url_font_size = int(width * 0.029)
    footer_font_size = int(width * 0.022)

    image_draw.text(
        (width / 2, height * 0.24),
        "Welcome to InkyPi",
        anchor="mm",
        fill=text_color,
        font=get_font("Jost", title_font_size, "bold"),
    )

    image_draw.text(
        (width / 2, height * 0.34),
        "Your display is ready. Open the web interface from a browser on the same network.",
        anchor="mm",
        fill=muted_color,
        font=get_font("Jost", subtitle_font_size),
    )

    box_left = int(width * 0.16)
    box_right = int(width * 0.84)
    box_height = int(height * 0.12)
    first_box_top = int(height * 0.43)
    second_box_top = int(height * 0.60)

    def draw_link_box(top, label, value):
        image_draw.text(
            (box_left, top - int(height * 0.028)),
            label,
            anchor="ls",
            fill=muted_color,
            font=get_font("Jost", label_font_size, "bold"),
        )
        image_draw.rounded_rectangle(
            (box_left, top, box_right, top + box_height),
            radius=max(18, int(height * 0.03)),
            fill=bg_color,
            outline=border_color,
            width=stroke_width,
        )
        image_draw.text(
            ((box_left + box_right) / 2, top + box_height / 2),
            value,
            anchor="mm",
            fill=accent_color,
            font=get_font("Jost", url_font_size, "bold"),
        )

    draw_link_box(first_box_top, "LOCAL NAME", local_url)
    draw_link_box(second_box_top, "IP ADDRESS", ip_url)

    footer_text = f"Wi-Fi: {wifi_name}" if wifi_name else "Tip: if .local does not resolve, use the IP address above."
    image_draw.text(
        (width / 2, height * 0.84),
        footer_text,
        anchor="mm",
        fill=muted_color,
        font=get_font("Jost", footer_font_size),
    )

    return image

def parse_form(request_form):
    request_dict = request_form.to_dict()
    for key in request_form.keys():
        if key.endswith('[]'):
            request_dict[key] = request_form.getlist(key)
    return request_dict

def handle_request_files(request_files, form_data={}):
    allowed_file_extensions = {'pdf', 'png', 'avif', 'jpg', 'jpeg', 'gif', 'webp', 'heif', 'heic'}
    file_location_map = {}
    # handle existing file locations being provided as part of the form data
    for key in set(request_files.keys()):
        is_list = key.endswith('[]')
        if key in form_data:
            file_location_map[key] = form_data.getlist(key) if is_list else form_data.get(key)
    # add new files in the request
    for key, file in request_files.items(multi=True):
        is_list = key.endswith('[]')
        file_name = file.filename
        if not file_name:
            continue

        extension = os.path.splitext(file_name)[1].replace('.', '')
        if not extension or extension.lower() not in allowed_file_extensions:
            continue

        file_name = os.path.basename(file_name)

        file_save_dir = resolve_path(os.path.join("static", "images", "saved"))
        file_path = os.path.join(file_save_dir, file_name)

        # Open the image and apply EXIF transformation before saving
        if extension in {'jpg', 'jpeg'}:
            try:
                with Image.open(file) as img:
                    img = ImageOps.exif_transpose(img)
                    img.save(file_path)
            except Exception as e:
                logger.warning(f"EXIF processing error for {file_name}: {e}")
                file.save(file_path)
        else:
            # Directly save non-JPEG files
            file.save(file_path)

        if is_list:
            file_location_map.setdefault(key, [])
            file_location_map[key].append(file_path)
        else:
            file_location_map[key] = file_path
    return file_location_map
