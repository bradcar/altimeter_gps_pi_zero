"""
Touch Quadrant & Coordinate Calibration Script
Tests GT911 touch coordinate mapping on Waveshare 2.13" E-Paper HAT (250x122)

Display coordinates - aligned with Pillow coordinates
Origin (0,0): Top-Left corner of the screen.
Y: Display Width (SCREEN_WIDTH): 250 pixels, 0 to 249 (Left → Right)
X: Display Height (SCREEN_HEIGHT): 122 pixels, 0 to 121 (Top → Bottom)

Display/Touch Zones:
    "Upper Left (Btn 3)"      y <= 125, x <= 61
    "Lower Left (Btn 2)"      y <= 125, x >  61
    "Upper Right (Btn 1)"     y >  125, x <= 61
    "Lower Right (Reserved)"  y >  125, x >  61
"""

import time
from PIL import ImageFont

# Fallback import handles running from root or from a parent script directory
try:
    from lib.eink_ssd1680_gt911_utils import (
        init_eink_display,
        refresh_eink_display,
        check_touch_inputs,
        flush_touch_inputs,
        align_touch_point_to_display,
        cleanup_eink,
    )
except ImportError:
    from eink_ssd1680_gt911_utils import (
        init_eink_display,
        refresh_eink_display,
        check_touch_inputs,
        flush_touch_inputs,
        align_touch_point_to_display,
        cleanup_eink,
    )

SCREEN_WIDTH = 250  # Y-axis extent (Horizontal)
SCREEN_HEIGHT = 122  # X-axis extent (Vertical)

# Target Display Rotation relative to Waveshare Native 0° Portrait:
#   90  = Standard Landscape (250x122)
#   270 = Flipped Landscape (250x122)
DISPLAY_ROTATION = 90


def draw_test_grid(epd_draw, font_small, last_touch_info="Touch anywhere to test"):
    """
    Draws quadrant boundaries, zone labels, and the last detected touch.
    Pillow ImageDraw takes coordinates in (horizontal_y, vertical_x) order.
    """
    epd_draw.rectangle((0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), fill=255)

    # Draw quadrant dividing lines
    epd_draw.line((125, 0, 125, 122), fill=0, width=1)  # Vertical split line at Y = 125
    epd_draw.line((0, 61, 250, 61), fill=0, width=1)    # Horizontal split line at X = 61

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

    # Status Bar / Touch Feedback at the bottom overlay
    epd_draw.rectangle((5, 100, 245, 120), fill=0)
    epd_draw.text((10, 103), last_touch_info, font=font_small, fill=255)


def process_touch_data(rotation: int = DISPLAY_ROTATION):
    """
    Reads hardware touch inputs and transforms them using the GT911 utility mapper.
    Maps transformed output so Y = Horizontal (Width) and X = Vertical (Height).
    """
    touch_data = check_touch_inputs(rotation=rotation)
    if not touch_data:
        return None

    touch = touch_data[0]
    raw_x, raw_y = touch.x, touch.y

    # transform_touch_point returns (disp_y, disp_x) where disp_y = Horizontal, disp_x = Vertical
    y, x = align_touch_point_to_display(touch, rotation=rotation)

    # Clean quadrant evaluation (Y = Width/Horizontal, X = Height/Vertical)
    if y <= 125:
        zone = "Up Left (Btn 3)" if x <= 61 else "Low Left (Btn 2)"
    else:
        zone = "Up Right (Btn 1)" if x <= 61 else "Low Right (Reserved)"

    return y, x, raw_x, raw_y, zone


def main():
    print("=====================================================")
    print("Starting Touch Zone Test Code...")
    print(f"Target Rotation: {DISPLAY_ROTATION}°")
    print("Axis Mapping: Y = Width (0..249), X = Height (0..121)")
    print("=====================================================")

    print("Initializing E-Ink Display...")
    epd_disp, epd_draw, font_small_default, epd_image = init_eink_display()
    print("E-Ink Initialized.")

    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)

    # Initial screen draw
    draw_test_grid(epd_draw, font_small)
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=False)
    flush_touch_inputs()

    print("\nTouch screen quadrants to test mapping.")

    try:
        while True:
            touch_result = process_touch_data(rotation=DISPLAY_ROTATION)

            if touch_result:
                y, x, raw_x, raw_y, zone = touch_result
                status_msg = f"Raw({raw_x},{raw_y}) -> Disp(Y={y},X={x}) | {zone}"

                print(f"\n[TOUCH DETECTED] {status_msg}")

                # Redraw test grid with updated info
                draw_test_grid(epd_draw, font_small, last_touch_info=f"Disp(Y={y},X={x}) -> {zone}")

                # Draw crosshair indicator at touch location: (horizontal_y, vertical_x)
                epd_draw.rectangle((y - 3, x - 3, y + 3, x + 3), fill=0)

                refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)
                flush_touch_inputs()
                time.sleep(0.2)  # Debounce delay

            time.sleep(0.05)

    finally:
        print("\nCleaning up display hardware...")
        cleanup_eink(epd_disp, clear=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest exited by user (ctrl-c).")
    except Exception as e:
        print(f"\nTest crashed with error: {e}")
