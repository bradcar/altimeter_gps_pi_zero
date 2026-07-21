# eink_ssd1680_gt911.py
"""
General Utils for Waveshare 2.13" E-Paper Touch Hat (epd2in13_V4)

Waveshare E-ink touch Hat 2.13" SSD1680 + GT911 (touch)
        20716: 2.13" Touch e-Paper HAT (with Pi Zero Case)
        Has partial updates
        https://www.waveshare.com/wiki/2.13inch_Touch_e-Paper_HAT_Manual


"""
import sys
from pathlib import Path

# Add project root and vendors directory to Python search path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
VENDORS_DIR = PROJECT_ROOT / "vendor"

# Append vendors directory so 'import epd2in13_V4' works directly
if str(VENDORS_DIR) not in sys.path:
    sys.path.insert(0, str(VENDORS_DIR))

# Append project root so module imports across src work smoothly
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Direct import from vendors/epd2in13_V4.py
import epd2in13_V4

from PIL import Image, ImageDraw, ImageFont
import smbus2
import time
from dataclasses import dataclass

# GT911 I2C Address & Register Definitions
GT911_I2C_ADDR = 0x14  # Default I2C address for Waveshare 2.13" Touch HAT (can be 0x5D on some boards)
GT911_READ_COORD_ADDR = 0x814E  # Point status register

TOUCH_WIDTH = 250
TOUCH_HEIGHT = 122
E_INK_WIDTH = 122
E_INK_HEIGHT = 250
VIRTUAL_WIDTH = 250
VIRTUAL_HEIGHT = 122
FILL_WHITE = 255




@dataclass
class TouchPoint:
    x: int
    y: int
    id: int = 0
    size: int = 0


class GT911Touch:
    def __init__(self, bus_num=1, address=GT911_I2C_ADDR):
        self.bus_num = bus_num
        self.address = address
        self.bus = None
        self._init_i2c()

    def _init_i2c(self):
        try:
            self.bus = smbus2.SMBus(self.bus_num)
        except Exception as e:
            print(f"GT911: Failed to open I2C bus {self.bus_num}: {e}")
            self.bus = None

    def read_touch_points(self) -> list[TouchPoint]:
        """
        Reads touch data from GT911 registers.
        Returns a list of TouchPoint objects with coordinates matching
        the rotated 250x122 display layout.
        """
        if self.bus is None:
            return []

        try:
            # Read 1 byte from point status register (0x814E)
            reg_msb = (GT911_READ_COORD_ADDR >> 8) & 0xFF
            reg_lsb = GT911_READ_COORD_ADDR & 0xFF

            # Write register address to set read pointer
            write_msg = smbus2.i2c_msg.write(self.address, [reg_msb, reg_lsb])
            read_msg = smbus2.i2c_msg.read(self.address, 1)
            self.bus.i2c_rdwr(write_msg, read_msg)

            point_status = list(read_msg)[0]

            # Buffer status bit (Bit 7): 1 = data ready
            buffer_ready = (point_status & 0x80) != 0
            touch_count = point_status & 0x0F

            if not buffer_ready or touch_count == 0:
                # Clear buffer status flag if set with 0 touch count
                if buffer_ready:
                    self._clear_status_register()
                return []

            # Read 8 bytes per touch point starting at 0x814F
            points = []
            bytes_to_read = touch_count * 8

            coord_addr_msb = 0x81
            coord_addr_lsb = 0x4F

            write_coord = smbus2.i2c_msg.write(self.address, [coord_addr_msb, coord_addr_lsb])
            read_coords = smbus2.i2c_msg.read(self.address, bytes_to_read)
            self.bus.i2c_rdwr(write_coord, read_coords)

            data = list(read_coords)

            for i in range(touch_count):
                offset = i * 8
                p_id = data[offset]
                raw_x = data[offset + 1] | (data[offset + 2] << 8)
                raw_y = data[offset + 3] | (data[offset + 4] << 8)
                p_size = data[offset + 5] | (data[offset + 6] << 8)

                # Rotate 180 degrees to match your display orientation:
                # get_rotated_buffer(img) flips display by 180 degrees
                rotated_x = TOUCH_WIDTH - 1 - raw_x
                rotated_y = TOUCH_HEIGHT - 1 - raw_y

                # Clamp values to screen bounds
                final_x = max(0, min(TOUCH_WIDTH - 1, rotated_x))
                final_y = max(0, min(TOUCH_HEIGHT - 1, rotated_y))

                points.append(TouchPoint(x=final_x, y=final_y, id=p_id, size=p_size))

            # Clear status register (write 0 to 0x814E) so GT911 knows we read the buffer
            self._clear_status_register()
            return points

        except Exception as e:
            # Silence transient I2C read errors during rapid polling
            return []

    def _clear_status_register(self):
        """Clears the buffer status register by writing 0 to 0x814E."""
        try:
            reg_msb = (GT911_READ_COORD_ADDR >> 8) & 0xFF
            reg_lsb = GT911_READ_COORD_ADDR & 0xFF
            write_cmd = smbus2.i2c_msg.write(self.address, [reg_msb, reg_lsb, 0x00])
            self.bus.i2c_rdwr(write_cmd)
        except Exception:
            pass

epd_disp = None
epd_image = None
epd_draw = None
partial_refresh_count = 0
MAX_PARTIAL_REFRESHES = 15

epd = None

# Global singleton instance for utility function
_gt911_driver = None

# Internal refresh counter to enforce ghosting safeguards
_PARTIAL_COUNT = 0
MAX_PARTIAL_REFRESHES = 15


def init_eink_display():
    global epd_disp, epd_image, epd_draw

    # Initialize Waveshare display driver from vendors/epd2in13_V4.py
    epd_disp = epd2in13_V4.EPD()
    epd_disp.init(epd_disp.FULL_UPDATE)
    epd_disp.Clear(0xFF)

    # 250x122 Canvas (1 = White, 0 = Black)
    epd_image = Image.new('1', (250, 122), 255)
    epd_draw = ImageDraw.Draw(epd_image)

    # Store initial frame for partial refresh baseline
    epd_disp.displayPartBaseImage(get_rotated_buffer(epd_image))
    epd_disp.init(epd_disp.PART_UPDATE)

    return epd_disp, epd_draw, None, epd_image


def blank_canvas_eink(draw):
    """Fills the virtual landscape canvas with white."""
    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=FILL_WHITE)


def get_rotated_buffer(img):
    """180-degree flip to account for mounting orientation."""
    return epd_disp.getbuffer(img.rotate(180))


def refresh_eink_display(disp, draw, img, partial=True):
    """
    Handles partial updates and automatically executes a clean full update
    every 15 refreshes to clear ghosting.
    """
    global partial_refresh_count
    if not partial or partial_refresh_count >= MAX_PARTIAL_REFRESHES:
        epd_disp.init(epd_disp.FULL_UPDATE)
        epd_disp.displayPartBaseImage(get_rotated_buffer(epd_image))
        epd_disp.init(epd_disp.PART_UPDATE)
        partial_refresh_count = 0
    else:
        epd_disp.displayPartial(get_rotated_buffer(epd_image))
        partial_refresh_count += 1

def check_touch_inputs() -> list[TouchPoint]:
    """
    Utility wrapper function called from altimeter_gps.py.
    Initializes driver on first run and returns active touch points.
    """
    global _gt911_driver
    if _gt911_driver is None:
        _gt911_driver = GT911Touch(bus_num=1, address=GT911_I2C_ADDR)

    return _gt911_driver.read_touch_points()


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