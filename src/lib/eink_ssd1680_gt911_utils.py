#!/usr/bin/env python3
"""
eink_ssd1680_gt911_utils.py

Utils for Waveshare 2.13" E-Paper Touch Hat (epd2in13_V4)
Driver & canvas helpers

Features
    * Display 250px x 122px
        - Pillow: Y = Width/Horizontal, X = Height/Vertical
    * GT911 Touch Controller

Variable Name	Role in Demo Code	Pixel Range in Code	Physical Orientation
GT_Dev.X[0]	Short Axis (Height / Vertical)	0 to 121 (Clamped check: < 121)	Native Width
GT_Dev.Y[0]	Long Axis (Width / Horizontal)	0 to 249 (Clamped check: < 244)	Native Height


https://www.waveshare.com/wiki/2.13inch_Touch_e-Paper_HAT_Manual#Raspberry_Pi
wget https://files.waveshare.com/upload/4/4e/Touch_e-Paper_Code.zip
unzip Touch_e-Paper_Code.zip -d Touch_e-Paper_Code

"""
import gc
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

# Hardware Native Base Dimensions (0° Portrait)
TOUCH_NATIVE_W = 122  # Short Axis (x: 0 .. 121)
TOUCH_NATIVE_H = 250  # Long Axis  (y: 0 .. 249)

# Virtual Canvas / Target Screen Defaults
VIRTUAL_WIDTH = 250   # Horizontal / Y-axis
VIRTUAL_HEIGHT = 122  # Vertical / X-axis
FILL_WHITE = 255

DEBUG_TOUCH = True  # Set to True to print touch events to stdout


@dataclass
class TouchPoint:
    x: int
    y: int
    id: int = 0
    size: int = 0


def map_touch_to_display(raw_x: int, raw_y: int, rotation: int = 90) -> tuple[int, int]:
    """
    Transforms raw GT911 touch coordinates into logical display coordinates.
    Returns (disp_y, disp_x) where:
      - disp_y = Horizontal / Width Axis (0 .. 249)
      - disp_x = Vertical / Height Axis  (0 .. 121)
    """
    # 1. Clamp raw sensor ranges to hardware limits
    clamped_x = max(0, min(TOUCH_NATIVE_W - 1, raw_x))  # 0 .. 121
    clamped_y = max(0, min(TOUCH_NATIVE_H - 1, raw_y))  # 0 .. 249

    # 2. Map coordinates based on target rotation
    if rotation == 90:
        # Standard Landscape (Y = Horizontal 0..249, X = Vertical 0..121)
        disp_y = clamped_y
        disp_x = (TOUCH_NATIVE_W - 1) - clamped_x  # Invert short axis to match Pillow canvas
    elif rotation == 270:
        # Flipped Landscape
        disp_y = (TOUCH_NATIVE_H - 1) - clamped_y
        disp_x = clamped_x
    elif rotation == 180:
        # Flipped Portrait
        disp_y = (TOUCH_NATIVE_W - 1) - clamped_x
        disp_x = (TOUCH_NATIVE_H - 1) - clamped_y
    else:
        # 0° Native Portrait
        disp_y = clamped_x
        disp_x = clamped_y

    return disp_y, disp_x


def reset_gt911():
    """Forces hardware reset pulse on GT911 to set I2C address 0x14."""
    try:
        epdconfig.digital_write(RST_PIN, 0)
        time.sleep(0.02)
        epdconfig.digital_write(RST_PIN, 1)
        time.sleep(0.05)
        print(" * GT911 Eink Touch reset at I2C 0x14")
    except Exception as e:
        print(f"* GT911 Eink touch reset error: {e}")


class GT911Touch:
    def __init__(self, bus_num=1, reset_pin=22, int_pin=27):
        self.bus_num = bus_num
        self.reset_pin = reset_pin
        self.int_pin = int_pin
        self.address = GT911_ADDR_PRIMARY
        self.bus = None

        self.finger_down = False
        self.last_trigger_time = 0.0

        self._init_i2c()

    def _init_i2c(self):
        try:
            self.bus = smbus2.SMBus(self.bus_num)
            for addr in [GT911_ADDR_PRIMARY, GT911_ADDR_SECONDARY]:
                try:
                    msb = (GT911_PRODUCT_ID_ADDR >> 8) & 0xFF
                    lsb = GT911_PRODUCT_ID_ADDR & 0xFF
                    self.bus.i2c_rdwr(
                        smbus2.i2c_msg.write(addr, [msb, lsb]),
                        smbus2.i2c_msg.read(addr, 4)
                    )
                    self.address = addr
                    print(f" * GT911 Eink Touch detected at I2C address 0x{addr:02X}")
                    return
                except Exception:
                    continue
            print("GT911 WARNING: No Eink Touch responded at 0x14 or 0x5D")
        except Exception as e:
            print(f"GT911 ERROR: Failed to open I2C bus {self.bus_num}: {e}")
            self.bus = None

    def read_touch_points(self) -> list[TouchPoint]:
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

            if not buffer_ready or touch_count == 0:
                if buffer_ready:
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

                native_x = max(0, min(TOUCH_NATIVE_W - 1, raw_x))
                native_y = max(0, min(TOUCH_NATIVE_H - 1, raw_y))

                pt = TouchPoint(x=native_x, y=native_y, id=p_id, size=p_size)
                points.append(pt)

            self._clear_status_register()
            return points

        except Exception:
            return []

    def transform_touch_point(self, pt: TouchPoint, rotation: int = 90) -> tuple[int, int]:
        """Delegates transformation to map_touch_to_display."""
        return map_touch_to_display(pt.x, pt.y, rotation=rotation)

    def get_single_press(self, cooldown_sec: float = 0.3, rotation: int = 90) -> list[TouchPoint]:
        raw_points = self.read_touch_points()
        now = time.time()

        if raw_points:
            if not self.finger_down:
                self.finger_down = True
                if (now - self.last_trigger_time) >= cooldown_sec:
                    self.last_trigger_time = now
                    if DEBUG_TOUCH:
                        pt = raw_points[0]
                        ty, tx = self.transform_touch_point(pt, rotation=rotation)
                        print(f"[GT911 TOUCH] Raw({pt.x}, {pt.y}) -> Disp{rotation}°(Y={ty}, X={tx})")
                    return raw_points
            return []
        else:
            self.finger_down = False
            return []

    def flush_buffer(self):
        self._clear_status_register()
        self.finger_down = False

    def _clear_status_register(self):
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

    epd_disp = epd2in13_V4.EPD()
    epd_disp.init(epd_disp.FULL_UPDATE)
    epd_disp.Clear(0xFF)

    reset_gt911()
    _gt911_driver = GT911Touch(bus_num=1)

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
    """
    Partial and full E-Ink refresh. Full refresh also does gc (Garbage collection).
    """
    global partial_refresh_count, epd_disp

    if not partial or partial_refresh_count >= MAX_PARTIAL_REFRESHES:
        # Full refresh (1-3 seconds)
        epd_disp.init(epd_disp.FULL_UPDATE)
        epd_disp.displayPartBaseImage(get_rotated_buffer(img))
        epd_disp.init(epd_disp.PART_UPDATE)
        partial_refresh_count = 0
        gc.collect()
    else:
        # Fast partial update pass (~300ms)
        epd_disp.displayPartial(get_rotated_buffer(img))
        partial_refresh_count += 1


def check_touch_inputs(cooldown_sec: float = 0.3, rotation: int = 90) -> list[TouchPoint]:
    global _gt911_driver
    if _gt911_driver is None:
        reset_gt911()
        _gt911_driver = GT911Touch()

    return _gt911_driver.get_single_press(cooldown_sec=cooldown_sec, rotation=rotation)


def align_touch_point_to_display(pt: TouchPoint, rotation: int = 90) -> tuple[int, int]:
    """Module-level wrapper exposing coordinate translation."""
    return map_touch_to_display(pt.x, pt.y, rotation=rotation)


def flush_touch_inputs():
    global _gt911_driver
    if _gt911_driver is not None:
        _gt911_driver.flush_buffer()


def cleanup_eink(display=None, clear=False):
    global epd_disp
    target_epd = display if display is not None else epd_disp
    if target_epd:
        try:
            if clear:
                if hasattr(target_epd, 'FULL_UPDATE'):
                    target_epd.init(target_epd.FULL_UPDATE)
                else:
                    target_epd.init()
                target_epd.Clear(0xFF)

            target_epd.sleep()

            if hasattr(target_epd, 'Dev_exit'):
                target_epd.Dev_exit()

        except Exception as e:
            print(f"Warning during E-Ink cleanup: {e}")