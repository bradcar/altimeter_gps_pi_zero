# touch_zone_test.py
"""
Touch Quadrant & Coordinate Calibration Script
Tests GT911 touch coordinate mapping on Waveshare 2.13" E-Paper HAT (250x122)
"""

import time
from PIL import ImageFont
from lib.eink_ssd1680_gt911_utils import (
    init_eink_display,
    refresh_eink_display,
    check_touch_inputs,
    flush_touch_inputs,
)

SCREEN_WIDTH = 250
SCREEN_HEIGHT = 122
RAW_TOUCH_MAX_X = 122
RAW_TOUCH_MAX_Y = 250


def draw_test_grid(epd_draw, font_small, font_medium, last_touch_info="Touch anywhere to test"):
    """
    Draws quadrant boundaries, zone labels, and the last detected touch.
    """
    epd_draw.rectangle((0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), fill=255)

    # Draw quadrant dividing lines
    epd_draw.line((125, 0, 125, 122), fill=0, width=1)  # Vertical split (X = 125)
    epd_draw.line((0, 61, 250, 61), fill=0, width=1)  # Horizontal split (Y = 61)

    # Label Top-Left: Mode Toggle (Button 3)
    epd_draw.text((10, 10), "MODE (Btn 3)", font=font_small, fill=0)
    epd_draw.text((10, 28), "Upper Left", font=font_small, fill=0)

    # Label Bottom-Left: Calibrate / Adjust (Button 2)
    epd_draw.text((10, 71), "CALIB (Btn 2)", font=font_small, fill=0)
    epd_draw.text((10, 89), "Lower Left", font=font_small, fill=0)

    # Label Top-Right: Unit Toggle (Button 1)
    epd_draw.text((135, 10), "UNIT (Btn 1)", font=font_small, fill=0)
    epd_draw.text((135, 28), "Upper Right", font=font_small, fill=0)

    # Label Bottom-Right: Reserved
    epd_draw.text((135, 71), "RESERVED", font=font_small, fill=0)
    epd_draw.text((135, 89), "Lower Right", font=font_small, fill=0)

    # Status Bar / Touch Feedback at the bottom center or overlay
    epd_draw.rectangle((5, 105, 245, 120), fill=0)
    epd_draw.text((10, 106), last_touch_info, font=font_small, fill=255)


def process_touch_data():
    """
    GT911 mapping using measured hardware bounds:
    Raw Y (~0..85) -> Display X (0..250)
    Raw X (~120..220) -> Display Y (0..122)
    """
    touch_data = check_touch_inputs()
    if not touch_data:
        return None

    touch = touch_data[0]
    raw_x, raw_y = touch.x, touch.y

    # --- YOUR CALIBRATED SCALING ---
    # Invert raw_y so Left touch -> X near 0, Right touch -> X near 249
    x = int(((85.0 - raw_y) / 85.0) * (SCREEN_WIDTH - 1))

    # Scale raw_x (120..220) cleanly to Display Y (0..122)
    y = int(((raw_x - 120) / 100.0) * (SCREEN_HEIGHT - 1))

    # Clamp boundaries
    x = max(0, min(SCREEN_WIDTH - 1, x))
    y = max(0, min(SCREEN_HEIGHT - 1, y))

    # Clean, standard quadrant evaluation matching the screen display
    if x <= 125:
        zone = "Upper Left (Btn 3)" if y <= 61 else "Lower Left (Btn 2)"
    else:
        zone = "Upper Right (Btn 1)" if y <= 61 else "Lower Right (Reserved)"

    return x, y, raw_x, raw_y, zone


def main():
    print("=================================================")
    print("Starting Touch Zone Test Code...")
    print("=================================================")

    print("Initializing E-Ink Display...")
    epd_disp, epd_draw, font_small_default, epd_image = init_eink_display()
    print("E-Ink Initialized.")

    try:
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except IOError:
        font_small = font_small_default
        font_medium = font_small_default

    # Initial screen draw (Full Update)
    draw_test_grid(epd_draw, font_small, font_medium)
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=False)
    flush_touch_inputs()

    print("\nTouch screen quadrants to test mapping. ")

    last_touch_time = 0

    while True:
        touch_result = process_touch_data()

        if touch_result:
            x, y, raw_x, raw_y, zone = touch_result
            status_msg = f"Raw({raw_x},{raw_y}) -> Disp({x},{y}) | {zone}"

            print(f"\n[TOUCH DETECTED] {status_msg}")

            # Draw visual feedback box around touch area on E-Ink
            draw_test_grid(epd_draw, font_small, font_medium, last_touch_info=f"Disp({x},{y}) -> {zone}")

            # Draw a small 10x10 crosshair box at touch coordinates
            # TODO verify and debug this
            epd_draw.rectangle((x - 4, y - 4, x + 4, y + 4), fill=0)

            refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)
            flush_touch_inputs()

            time.sleep(0.2)  # Short pause to prevent over-triggering

        time.sleep(0.05)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest exited by user (Ctrl-C).")
    except Exception as e:
        print(f"\nTest crashed with error: {e}")
