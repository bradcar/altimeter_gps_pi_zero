"""
General Utils for Waveshare 2.13" E-Paper Touch Hat (epd2in13_V4)
Includes GT911 Touch Controller Driver & Canvas Helpers.
"""
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import smbus2
from PIL import Image, ImageDraw

# Add project root and vendor directory to Python search path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
VENDORS_DIR = PROJECT_ROOT / "vendor"

if str(VENDORS_DIR) not in sys.path:
    sys.path.insert(0, str(VENDORS_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vendor.epd2in13_V4 import epdconfig
import epd2in13_V4

# Touch Hardware Pin Definitions
RST_PIN = 22
INT_PIN = 27

# GT911 I2C Addresses
GT911_ADDR_PRIMARY = 0x14
GT911_ADDR_SECONDARY = 0x5D

# GT911 Registers
GT911_READ_COORD_ADDR = 0x814E
GT911_PRODUCT_ID_ADDR = 0x8140

TOUCH_WIDTH = 250
TOUCH_HEIGHT = 122
VIRTUAL_WIDTH = 250
VIRTUAL_HEIGHT = 122
FILL_WHITE = 255

DEBUG_TOUCH = True  # Set to True to print touch events to stdout


@dataclass
class TouchPoint:
    x: int
    y: int
    id: int = 0
    size: int = 0


def reset_gt911():
    """
    Forces hardware reset pulse on GT911 to set I2C address 0x14.
    Reuses Waveshare's epdconfig digital_write interface.
    """
    try:
        # Pulse RST (GPIO 22) low using epdconfig's active backend
        epdconfig.digital_write(RST_PIN, 0)
        time.sleep(0.02)

        # Drive RST (GPIO 22) high -> configures GT911 address to 0x14
        epdconfig.digital_write(RST_PIN, 1)
        time.sleep(0.05)

        print(" * GT911 Eink Touch reset at 0x14 (via epdconfig)")

    except Exception as e:
        print(f"* GT911 Eink touch reset error: {e}")


class GT911Touch:
    def __init__(self, bus_num=1, reset_pin=22, int_pin=27):
        self.bus_num = bus_num
        self.reset_pin = reset_pin
        self.int_pin = int_pin
        self.address = GT911_ADDR_PRIMARY
        self.bus = None

        # State tracking for debounce & edge detection
        self.finger_down = False
        self.last_trigger_time = 0.0

        self._init_i2c()

    def _init_i2c(self):
        try:
            self.bus = smbus2.SMBus(self.bus_num)
            for addr in [GT911_ADDR_PRIMARY, GT911_ADDR_SECONDARY]:
                try:
                    msb, lsb = (GT911_PRODUCT_ID_ADDR >> 8) & 0xFF, GT911_PRODUCT_ID_ADDR & 0xFF
                    self.bus.i2c_rdwr(
                        smbus2.i2c_msg.write(addr, [msb, lsb]),
                        smbus2.i2c_msg.read(addr, 4)
                    )
                    self.address = addr
                    print(f" * GT911: Eink Touch detected at I2C address 0x{addr:02X}")
                    return
                except Exception:
                    continue
            print("GT911 WARNING: No Eink Touch responded at 0x14 or 0x5D!")
        except Exception as e:
            print(f"GT911: Failed to open I2C bus {self.bus_num}: {e}")
            self.bus = None

    def read_touch_points(self) -> list[TouchPoint]:
        """Low-level register poll for raw touch points."""
        if self.bus is None:
            return []

        try:
            reg_msb = (GT911_READ_COORD_ADDR >> 8) & 0xFF
            reg_lsb = GT911_READ_COORD_ADDR & 0xFF

            write_msg = smbus2.i2c_msg.write(self.address, [reg_msb, reg_lsb])
            read_msg = smbus2.i2c_msg.read(self.address, 1)
            self.bus.i2c_rdwr(write_msg, read_msg)

            point_status = list(read_msg)[0]
            buffer_ready = (point_status & 0x80) != 0
            touch_count = point_status & 0x0F

            if not buffer_ready:
                return []

            if touch_count == 0:
                self._clear_status_register()
                return []

            bytes_to_read = touch_count * 8
            write_coord = smbus2.i2c_msg.write(self.address, [0x81, 0x4F])
            read_coords = smbus2.i2c_msg.read(self.address, bytes_to_read)
            self.bus.i2c_rdwr(write_coord, read_coords)

            data = list(read_coords)
            points = []

            for i in range(touch_count):
                offset = i * 8
                p_id = data[offset]
                raw_x = data[offset + 1] | (data[offset + 2] << 8)
                raw_y = data[offset + 3] | (data[offset + 4] << 8)
                p_size = data[offset + 5] | (data[offset + 6] << 8)

                # Rotate 180 degrees
                rotated_x = TOUCH_WIDTH - 1 - raw_x
                rotated_y = TOUCH_HEIGHT - 1 - raw_y

                final_x = max(0, min(TOUCH_WIDTH - 1, rotated_x))
                final_y = max(0, min(TOUCH_HEIGHT - 1, rotated_y))

                pt = TouchPoint(x=final_x, y=final_y, id=p_id, size=p_size)
                points.append(pt)

            self._clear_status_register()
            return points

        except Exception:
            return []

    def get_single_press(self, cooldown_sec: float = 0.8) -> list[TouchPoint]:
        """
        Returns touch points ONLY on the initial touch event (finger-down transition).
        Ignores continuous holding and enforces a cooldown period.
        """
        raw_points = self.read_touch_points()
        now = time.time()

        if raw_points:
            # Finger is currently on the screen
            if not self.finger_down:
                self.finger_down = True
                # Only register button press if cooldown period has elapsed
                if (now - self.last_trigger_time) >= cooldown_sec:
                    self.last_trigger_time = now
                    if DEBUG_TOUCH:
                        pt = raw_points[0]
                        print(f"[GT911 TOUCH] Press detected at ({pt.x}, {pt.y})")
                    return raw_points
            # Finger is still held down -> ignore repeating events
            return []
        else:
            # Finger lifted -> reset state
            self.finger_down = False
            return []

    def flush_buffer(self):
        """Flushes any accumulated/stale touches in the GT911 hardware register."""
        self._clear_status_register()
        self.finger_down = False

    def _clear_status_register(self):
        """Clears 0x814E by writing 0x00."""
        try:
            reg_msb = (GT911_READ_COORD_ADDR >> 8) & 0xFF
            reg_lsb = GT911_READ_COORD_ADDR & 0xFF
            write_cmd = smbus2.i2c_msg.write(self.address, [reg_msb, reg_lsb, 0x00])
            self.bus.i2c_rdwr(write_cmd)
        except Exception:
            pass


# E-Ink Display Globals
epd_disp = None
epd_image = None
epd_draw = None
partial_refresh_count = 0
MAX_PARTIAL_REFRESHES = 15

_gt911_driver = None


def init_eink_display():
    global epd_disp, epd_image, epd_draw, _gt911_driver

    # Initialize E-Paper Display hardware first
    epd_disp = epd2in13_V4.EPD()
    epd_disp.init(epd_disp.FULL_UPDATE)
    epd_disp.Clear(0xFF)

    # Reset and wake up GT911 Touch Chip
    reset_gt911()

    # Instantiate GT911 Driver
    _gt911_driver = GT911Touch(bus_num=1)

    # Canvas setup
    epd_image = Image.new('1', (VIRTUAL_WIDTH, VIRTUAL_HEIGHT), FILL_WHITE)
    epd_draw = ImageDraw.Draw(epd_image)

    epd_disp.displayPartBaseImage(get_rotated_buffer(epd_image))
    epd_disp.init(epd_disp.PART_UPDATE)

    return epd_disp, epd_draw, None, epd_image


def blank_canvas_eink(draw):
    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=FILL_WHITE)


def get_rotated_buffer(img):
    return epd_disp.getbuffer(img.rotate(180))


def refresh_eink_display(disp, draw, img, partial=True):
    global partial_refresh_count
    if not partial or partial_refresh_count >= MAX_PARTIAL_REFRESHES:
        epd_disp.init(epd_disp.FULL_UPDATE)
        epd_disp.displayPartBaseImage(get_rotated_buffer(epd_image))
        epd_disp.init(epd_disp.PART_UPDATE)
        partial_refresh_count = 0
    else:
        epd_disp.displayPartial(get_rotated_buffer(epd_image))
        partial_refresh_count += 1


def check_touch_inputs(cooldown_sec: float = 0.8) -> list[TouchPoint]:
    """Utility wrapper polled continuously from main loop."""
    global _gt911_driver
    if _gt911_driver is None:
        reset_gt911()
        _gt911_driver = GT911Touch()

    return _gt911_driver.get_single_press(cooldown_sec=cooldown_sec)


def flush_touch_inputs():
    """Flushes stale touch points from the GT911 buffer."""
    global _gt911_driver
    if _gt911_driver is not None:
        _gt911_driver.flush_buffer()


def cleanup_eink(display=None):
    global epd_disp
    target_epd = display if display is not None else epd_disp
    if target_epd:
        target_epd.init()
        target_epd.Clear(0xFF)
        target_epd.sleep()
