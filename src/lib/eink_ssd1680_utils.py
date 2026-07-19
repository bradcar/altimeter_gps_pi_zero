# eink_SSD1680_utils.py
"""
General Utils for E-ink SSD1680
"""
from PIL import Image, ImageDraw, ImageFont
import board
import digitalio
import busio
from adafruit_epd.ssd1680 import Adafruit_SSD1680

E_INK_WIDTH = 122
E_INK_HEIGHT = 250
VIRTUAL_WIDTH = 250
VIRTUAL_HEIGHT = 122
FILL_WHITE = 255


def init_eink_display(spi=None):
    """Initializes the E-ink display using SPI and creates the canvas."""
    if spi is None:
        spi = busio.SPI(board.SCK, board.MOSI)

    dc = digitalio.DigitalInOut(board.D22)  # Data/Command Control
    rst = digitalio.DigitalInOut(board.D27)  # Hardware Reset
    busy = digitalio.DigitalInOut(board.D17)  # Hardware Busy Line

    display = Adafruit_SSD1680(
        width=E_INK_WIDTH,
        height=E_INK_HEIGHT,
        spi=spi,
        cs_pin=board.CE0,
        dc_pin=dc,
        sramcs_pin=None,
        rst_pin=rst,
        busy_pin=busy
    )

    display.rotation = 0
    display.fill(0)
    display.display()

    # Image canvas in "L" (8-bit pixels, black and white)
    image = Image.new("L", (VIRTUAL_WIDTH, VIRTUAL_HEIGHT))
    draw = ImageDraw.Draw(image)

    try:
        # Defaulting to 16 for better visibility on 2.13" E-ink
        font = ImageFont.load_default(size=14)
    except IOError:
        font = ImageFont.load_default()

    return display, draw, font, image


def blank_canvas_eink(draw):
    """Fill canvas with black"""
    draw.rectangle((0, 0, E_INK_HEIGHT, E_INK_WIDTH), fill=0)


def refresh_eink_display(display, draw, image, partial=True):
    """
    Handles the rotation from E-Ink default to Landscape and trigger the physical refresh.
    """
    # Rotate the image
    hardware_aligned_image = image.rotate(270, expand=True)
    display.image(hardware_aligned_image)

    # Refresh
    try:
        display.display(partial_refresh=partial)
    except TypeError:
        display.display()
