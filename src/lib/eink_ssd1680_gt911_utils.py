# eink_ssd1680_gt911.py
"""
General Utils for Waveshare 2.13" E-Paper Touch Hat (epd2in13_V4)

Waveshare E-ink touch Hat 2.13" SSD1680 + GT911 (touch)
        20716: 2.13" Touch e-Paper HAT (with Pi Zero Case)
        Has partial updates
        https://www.waveshare.com/wiki/2.13inch_Touch_e-Paper_HAT_Manual


"""
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd2in13_V4

E_INK_WIDTH = 122
E_INK_HEIGHT = 250
VIRTUAL_WIDTH = 250
VIRTUAL_HEIGHT = 122
FILL_WHITE = 255

epd = None

# Internal refresh counter to enforce ghosting safeguards
_PARTIAL_COUNT = 0
MAX_PARTIAL_REFRESHES = 15

def init_eink_display():
    """
    Initializes the Waveshare 2.13" E-Paper display and creates the canvas.
    """
    global epd, _PARTIAL_COUNT

    epd = epd2in13_V4.EPD()
    epd.init()
    epd.Clear(0xFF)  # Wipe display to white
    epd.sleep()  # Immediately sleep to avoid leaving power on high-voltage lines

    _PARTIAL_COUNT = 0

    # Create off-screen buffer in Landscape orientation ("L" mode: 8-bit greyscale/mono)
    image = Image.new("L", (VIRTUAL_WIDTH, VIRTUAL_HEIGHT), FILL_WHITE)
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default(size=14)
    except (IOError, TypeError):
        font = ImageFont.load_default()

    return epd, draw, font, image


def blank_canvas_eink(draw):
    """Fills the virtual landscape canvas with white."""
    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=FILL_WHITE)


def refresh_eink_display(display, draw, image, partial=True):
    """
    Handles landscape rotation (270°), executes partial or full refresh,
    and puts the controller into deep sleep to protect hardware life.
    """
    global _PARTIAL_COUNT, epd

    # If display was passed as None or uninitialized, use global instance
    if display is None:
        display = epd

    # Rotate virtual landscape image back to the hardware's native vertical orientation
    hardware_aligned_image = image.rotate(270, expand=True)
    buffer = display.getbuffer(hardware_aligned_image)

    # Safeguard: Force full refresh if partial refresh limit reached
    if partial and _PARTIAL_COUNT >= MAX_PARTIAL_REFRESHES:
        partial = False

    if not partial:
        # Full Refresh (~2 seconds, removes ghosting/burn-in)
        display.init()
        display.display(buffer)
        display.sleep()
        _PARTIAL_COUNT = 0
    else:
        # Fast Partial Refresh (~0.3 seconds)
        display.init_fast()
        display.displayPartial(buffer)
        display.sleep()
        _PARTIAL_COUNT += 1


def cleanup_eink(display=None):
    """
    Optional helper: Clears the display and ensures deep sleep on program shutdown.
    """
    global epd
    target_epd = display if display is not None else epd
    if target_epd:
        target_epd.init()
        target_epd.Clear(0xFF)
        target_epd.sleep()