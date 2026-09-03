#!/usr/bin/env python3
"""
altimeter_gps_ws.py

Raspberry Pi Zero: Altimeter = Elevation & sea level pressure adjust

Sensors used
    - BMP585 highly accurate pressure & altitude
    - BME680 temp, humidity, pressure, IAQ, altitude
    - Rotary encoder to adjust alt and or pressure, switch toggle for larger increments
    - E-ink display 250px x 122px
        - WaveShare 20716: 2.13" Touch e-Paper HAT (with Pi Zero Case)
        - Adafruit E-ink 2.13" SSD1680
    - Touch display 5 points
    - Metric/Imperial switch

Functionality
    - set's system time after GPS fix established. Resets system to GPS time every 24 hours.
    - gc - garbage collection every 30min (at gas burn) and full E-Ink refresh.

Use sea level pressure at nearest airport
    * Portland updated hourly (7 min before the hour)
        https://www.weather.gov/wrh/timeseries?site=KPDX

Buttons & Touch:
The touch areas can be used as subsitutions for physical GPIO buttons
    Button 1: Cycle through display Summary and Details
              Upper left touch of display, or GPIO 6 (upper button if Adafruit E-ink 2.13" SSD1680)
    Button 2: Adjust altitude/SLP (GPIO 5)
              Upper left touch of display, or GPIO 5 (lower button if Adafruit E-ink 2.13" SSD1680)
    Button 3: metric/Imperial toggle (GPIO 16)
              upper right touch of display
    Button 4: Oregon reference
              lower right touch of display, no physical pin

Display
    - Started with Adafruit E-ink 2.13" SSD1680
        It has no partial refresh

    - Moving to Waveshare E-ink touch Hat 2.13" SSD1680 + GT911 (touch)
        20716: 2.13" Touch e-Paper HAT (with Pi Zero Case)
        Has partial updates
        https://www.waveshare.com/wiki/2.13inch_Touch_e-Paper_HAT_Manual

    - After several partial refreshes, you need to fully refresh EPD.
    - The screen cannot be powered on for a long time.
    - When the screen is not refreshed, please put the screen in sleep mode or power off it to avoid permanent damage.
    - The refresh interval is at least 180s, and refresh at least once every 24 hours.
    - If the Eink is not used for a long time, you should clear the screen before long term storage.

AIRPORTS:
    PDX - Portland
    Portland, Portland International Airport, OR (ASOS/AWOS - PQR)
    Elev: 20.0 ft; Lat/Lon: 45.59578/-122.60917


    Hawthorne Nevada
    Hawthorne Industrial Airport, NV (ASOS/AWOS - REV)
    Station Elev: 4230.0 ft; Lat/Lon: 38.54482/-118.63137
    https://www.weather.gov/wrh/timeseries?site=KHTH

    Buttons & Touch:

    Two paths
     * Physical GPIO Buttons / Rotary
       - GPIO 5, 6, 16)
       - trigger_button (num, "gpio")
       - 100ms Debounce

     * Waveshare GT911 Touch Screen
       - I2C Bus + SPI E-Paper
       - check_touch_buttons()
       - 250ms Debounce

     Then goes to
     1. _pending_button (Queue)
     2. get_button()
     3. main() Processing Loop


TODOS
    * TOdo why is Reading sensors @ 198.66s 	12:24:06 (clock wrong)
    * todo add warning the GPS altitude is diff than barometer
    * TODO test with other E-Ink display to minimize code overlap
    * TODO clean up library headers
    * TODO move E-Ink setup into main?
    * TODO put barometer metrics intro . structure like gps
"""

import gc
import os
import sys
import time

from adafruit_gps import GPS

from PIL import ImageFont
from gpiozero import Button, RotaryEncoder

from barometer_utils import calc_sea_level_pressure, bme_hpa_correction, calc_altitude
# from button_rotary_utils import process_inputs, check_rotary_switch_pressed
from gps_utils import initialize_gps
from lib.bme680 import BME680_I2C
from lib.bme680_utils import iaq_quality_to_string, calculate_iaq
# from lib.eink_ssd1680_utils import init_eink_display, refresh_eink_display
from lib.eink_ssd1680_gt911_utils import init_eink_display, refresh_eink_display, check_touch_inputs, \
    flush_touch_inputs, align_touch_point_to_display
from lib.gps_utils import get_time_from_gps, get_map_string, get_lat_string, get_lon_string, set_pi_system_time_from_gps
from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_utils import pi_on_chip_temperature, scan_i2c_bus
from metric_imperial_utils import feet_to_meters, metric_format, altitude_to_string, meters_to_feet
from micropython_bmpxxx.bmpxxx import BMP585
from pi_zero_i2c_bridge_utils import PiZeroI2CBridge

# Portland OR, PDX
PDX_STATION_STRING = "PDX - Portland, OR"
PDX_STATION_HPA = 1009.43
PDX_STATION_FEET = 20.

# big change night
# Altitude: 471.295'  (143.651m).  Barometer: 29.38"  (995.05 hPa). PDX_STATION_HPA = 1010.78
# Altitude: 351.643'  (107.181m).  Barometer: 29.38"  (995.03 hPa). PDX_STATION_HPA = 1006.38

#Altitude: 348.288'  (106.158m)  Barometer: 29.46"  (997.49 hPa)

# Hawthorne NV, HTH
HTH_STATION_HPA = 870.00
HTH_STATION_FEET = 4230.

FALLBACK_SEA_LEVEL_PRESSURE = 1019.00

DEBUG = True
OVER_TEMP_WARNING = 70.0

SCREEN_WIDTH = 250
SCREEN_HEIGHT = 122
DISPLAY_ROTATION = 90
TOUCH_DEBOUNCE_SEC = 0.35  # Ignore touch events within 350ms of the last trigger

# Timing Constants (in seconds)
LOOP_STRETCH_SLEEP = 0.2  # Small sleep each loop
GPS_INTERVAL_SEC = 1.0  # Read GPS metrics every 1 seconds
SENSOR_INTERVAL_SEC = 1.0  # Read core pressure, temp, & other metrics every 2 seconds
EINK_FULL_REFRESH_SEC = 180.0  # required Full refresh E-ink limit(3 minutes / 180 sec)
MAX_EINK_PARTIAL_REFRESH = 15  # count for partial refresh
EINK_PARTIAL_REFRESH_SEC = 1.0  # Partial E-ink refresh at least every second
GAS_INTERVAL_SEC = 30.0  # Read gas IAQ metrics every 30 seconds
SET_CLOCK_INTERVAL_SEC = 24 * 60 * 60  # Every 24 hours get GPS time to reset system time

implementation = [sys.implementation.name]


def uname():
    u = os.uname()
    return [u.sysname, u.nodename, u.release, u.version, u.machine]


# Unified button Physical and touch input handling
_pending_button = None
_last_gpio_input_time = 0.0
_last_touch_input_time = 0.0

GPIO_DEBOUNCE_SEC = 0.10  # Debounce physical buttons
TOUCH_DEBOUNCE_SEC = 0.25  # Touch gesture / e-ink timing window


def trigger_button(button_num, source):
    """
    Convert a physical GPIO button or E-ink touch into one logical pending button event.
    The input source determines debounce timing.
    source: string to determine button or touch source
    """
    global _pending_button, _last_gpio_input_time, _last_touch_input_time
    now = time.monotonic()

    if source == "gpio":
        if (now - _last_gpio_input_time) < GPIO_DEBOUNCE_SEC:
            return
        _last_gpio_input_time = now
    elif source == "touch":
        if (now - _last_touch_input_time) < TOUCH_DEBOUNCE_SEC:
            return
        _last_touch_input_time = now
    else:
        raise ValueError(f"Unknown button source: {source}")

    _pending_button = button_num
    print(f"* {source} accepted Button {button_num}")


def get_button():
    """ Return the pending button event and consume it. Returns None if no button is pending. """
    global _pending_button
    button = _pending_button
    _pending_button = None
    return button


def clear_pending_button():
    """ Flushes any queued pending button to prevent accidental double-execution across modes. """
    global _pending_button
    _pending_button = None


# Physical Hardware Pins
button_1 = Button(6, pull_up=True, bounce_time=0.05)
button_2 = Button(5, pull_up=True, bounce_time=0.05)
button_3 = Button(16, pull_up=True, bounce_time=0.05)

# Physical GPIO Callbacks
button_1.when_pressed = lambda: trigger_button(1, "gpio")
button_2.when_pressed = lambda: trigger_button(2, "gpio")
button_3.when_pressed = lambda: trigger_button(3, "gpio")

# Rotary encoder: a = clk, b = DT, max_steps is by default +/-16 steps, 0 means unlimited
encoder = RotaryEncoder(a=21, b=13, max_steps=0, bounce_time=0.005)
rotary_switch = Button(19, pull_up=True, bounce_time=0.05)

# Initialize the SSD1680 E-ink hardware & Pillow canvas
# TODO Add timeout from pi_zero_utils.py
print("Initialize E-ink...")
epd_disp, epd_draw, epd_font_small, epd_image = init_eink_display()
print("E-ink Initialization Done.")

# Load custom font sizes using Pillow
try:
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    font_biggest = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
except IOError:
    font_small = ImageFont.load_default()
    font_medium = ImageFont.load_default()
    font_large = ImageFont.load_default()
    font_biggest = ImageFont.load_default()


def check_touch_buttons(rotation: int = DISPLAY_ROTATION):
    """
    Checks GT911 touch inputs using aligned display coordinates. y=[0,250], x [0,122]

             y <= 125    y > 125
            +----------+----------+
    x <= 61 | Button 1 | Button 3 |
            +----------+----------+
    x > 61  | Button 2 | Button 4 |
            +----------+----------+
    """
    touch_data = check_touch_inputs(rotation=rotation)
    if not touch_data:
        return

    # Get active touch point, then Flush GT911 touch hardware buffer
    touch = touch_data[0]
    y, x = align_touch_point_to_display(touch, rotation=rotation)
    flush_touch_inputs()

    # Touch quadrant evaluation
    if x <= 61:
        button_num = 1 if y <= 125 else 3
    else:
        button_num = 2 if y <= 125 else 4

    trigger_button(button_num, "touch")


def i2c_initialize_bmp585_bme680(i2c1: PiZeroI2CBridge) -> tuple[BME680_I2C, BMP585, bool, bool]:
    """
    Initialize Barometers: BMP585, BME680

    :param i2c1: PiZeroI2CBridge, typically created with  i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    :return:
    bmp, bme, error_bmp585, error_bme680
    """
    error_bme680 = False
    error_bmp585 = False
    bme = None
    bmp = None

    try:
        bme = BME680_I2C(i2c=i2c1, address=0x77)
        print("BME680 initialized")
    except Exception as e:
        error_bme680 = True
        print(f"ERROR: BME680 not initialized: {e}")

    try:
        bmp = bmpxxx.BMP585(i2c=i2c1, address=0x47)
        bmp.pressure_oversample_rate = bmp.OSR128
        bmp.temperature_oversample_rate = bmp.OSR8
        bmp.iir_coefficient = bmp.COEF_7
        print("BMP585 initialized")

    except Exception as e:
        error_bmp585 = True
        print(f"ERROR: BMP585 not initialized: {e}")
    return bmp, bme, error_bmp585, error_bme680


def calibrate_bme_barometer(bme: BME680_I2C | None, bmp: BMP585 | None):
    """ Calibrate BME680 using BMP585 Barometer as golden source """
    average_diff = 1.0312750  # fallback hPa correction for BME680, if no BMP585
    if bmp is not None and bme is not None:
        average_diff = bme_hpa_correction(bme, bmp, 25)
        print(f" * BMP585 calibration for BME680 = {average_diff:.7f} hPa")
    elif bme is not None:
        print(f" * No BMP585 to calibrate BME680, using default {average_diff:.7f} hPa")

    # BME680 hPA amount over will be subtracted in calibration code.
    bme.hpa_calibration = average_diff
    if bme.hpa_calibration is not None:
        print(f" * BME680 calibrated with = {average_diff:.7f} hPa")
    else:
        print(f" * ERROR IN BME680 hpa_calibration = None!")

    print(" Barometers Initialization Done.")


def adjust_altitude_slp(gps, is_metric, altitude_m, pressure_hpa, sea_level_pressure_hpa):
    new_alt = altitude_m
    new_slp = sea_level_pressure_hpa
    multiplier_small_step = 1.0
    multiplier_big_step = 100.0
    rotary_multiplier = multiplier_small_step
    rotary_old = encoder.steps
    partial_refresh_count = 0  # method local count

    print(f"Adjustment start: alt = {new_alt:.3f} m")
    need_redraw = True

    # Clear left-over button presses before starting calibration loop
    clear_pending_button()

    while True:
        # Check GT911 touch and Retrieve next queued button press (from physical GPIO or touch)
        check_touch_buttons()
        button_state = get_button()

        # Button 2: Save / Exit calibration mode
        if button_state == 2:
            clear_pending_button()
            return new_slp

        # Button 3: Toggle metric / imperial units
        elif button_state == 3:
            is_metric = not is_metric
            need_redraw = True

        if gps is not None:
            gps.update()

        if rotary_switch.is_pressed:
            rotary_multiplier = multiplier_big_step if rotary_multiplier == multiplier_small_step else multiplier_small_step
            print(f"Rotary multiplier: {rotary_multiplier}")
            while rotary_switch.is_pressed:
                time.sleep(0.01)

        rotary_new = encoder.steps
        if rotary_old != rotary_new:
            delta = rotary_new - rotary_old

            if is_metric:
                new_alt += delta * rotary_multiplier
            else:
                new_alt += (delta * rotary_multiplier) / 3.28084

            new_slp = calc_sea_level_pressure(pressure_hpa, new_alt)
            rotary_old = rotary_new
            need_redraw = True

        if need_redraw:
            # Use Partial for fast feedback, but full after 5 to reduce ghosting
            if partial_refresh_count < 5:
                partial_refresh_count += 1
                display_updated_altitude_calibration(new_alt, new_slp, is_metric, partial=True)
            else:
                display_updated_altitude_calibration(new_alt, new_slp, is_metric, partial=False)
                partial_refresh_count = 0
            need_redraw = False

        time.sleep(0.03)


def display_list_names_values(altitude_data: list[tuple[str, str]], font_list, line_height: int,
                              start_y: int, left_margin_x: int, right_align_x: int):
    """ Display a list of names and values """
    for index, (location, elevation) in enumerate(altitude_data):
        current_y = start_y + (index * line_height)

        epd_draw.text((left_margin_x, current_y), location, font=font_list, fill=0)

        # Right align text
        text_width = font_small.getlength(elevation)
        elevation_x = right_align_x - text_width
        epd_draw.text((elevation_x, current_y), elevation, font=font_list, fill=0)


def display_altitude_reference(is_metric, partial=False):
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    epd_draw.text((3, 5), "Oregon Altitude Reference", font=font_small, fill=0)
    epd_draw.line((5, 21, 250, 21), fill=0, width=1)

    altitude_data = [
        ("Garage:", altitude_to_string(feet_to_meters(339), 0, is_metric)),
        ("Sylvan On-ramp:", altitude_to_string(feet_to_meters(761), 0, is_metric)),
        ("Meadows Main:", altitude_to_string(feet_to_meters(5003), 0, is_metric)),
        ("Meadows HRM:", altitude_to_string(feet_to_meters(4540), 0, is_metric)),
        ("Bachelor Main:", altitude_to_string(feet_to_meters(6207), 0, is_metric)),
        ("Rock Gym Beav:", altitude_to_string(feet_to_meters(122), 0, is_metric)),
    ]

    font_list = font_small
    start_y = 25
    line_height = 16
    if is_metric:
        left_margin_x = 25
        right_align_x = 225
    else:
        left_margin_x = 29
        right_align_x = 216

    display_list_names_values(altitude_data, font_list, line_height, start_y, left_margin_x, right_align_x)
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=partial)
    time.sleep(5)


def display_updated_altitude_calibration(alt, press, is_metric, partial=False):
    """
    Renders current calibration values to E-Ink display.
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=255)
    epd_draw.rectangle((0, 0, 250, 25), fill=0)
    epd_draw.text((34, 2), "Setting Altitude...", font=font_medium, fill=255)

    # New Altitude Data
    epd_draw.text((2, 33), "SET", font=font_medium, fill=0)
    epd_draw.text((2, 49), "Alt", font=font_medium, fill=0)

    # Formatted to 0 decimals so text fits  on screen
    # TODO Adjust this for more info on display
    convert, unit = metric_format(is_metric)
    alt_val = f"{(alt * convert):.0f}{unit}"
    epd_draw.text((60, 28), alt_val, font=font_biggest, fill=0)

    # Sea Level Pressure Data
    epd_draw.text((2, 80), "Sea", font=font_medium, fill=0)
    epd_draw.text((2, 96), "hPa", font=font_medium, fill=0)

    press_val = f"{press:.2f}"
    epd_draw.text((60, 74), press_val, font=font_large, fill=0)

    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=partial)


def print_altimeter_details(altitude_m, pressure_hpa, temp_c, humidity, iaq, is_metric):
    print("=" * 40)
    clock_string = time.strftime("%I:%M %p", time.localtime()).lower()

    if is_metric:
        altitude_string = f"{altitude_m:.3f}m"
        barometer_string = f"{pressure_hpa:.2f} hPa"
        temperature_string = f"{temp_c:.1f}° C"
    else:
        altitude_string = f"{meters_to_feet(altitude_m):.3f}'  ({altitude_m:.3f}m)"
        barometer_string = f"{pressure_hpa * 0.02953:.2f}\"  ({pressure_hpa:.2f} hPa)"
        temp_f = (temp_c * 9.0 / 5.0) + 32.0
        temperature_string = f"{temp_f:.1f}° F  ({temp_c:.1f}° C)"
    humidity_string = f"{humidity:.1f}%" if humidity is not None else "No Data"
    iaq_string = f"{iaq:.0f} ({iaq_quality_to_string(iaq)})" if iaq is not None else "No Data"

    print(f"Altitude: {altitude_string}")
    print(f"Barometer: {barometer_string}")
    print(f"Temperature: {temperature_string}")
    print(f"Humidity: {humidity_string}")
    print(f"IAQ {iaq_string}")


def display_altimeter_details(altitude_m, pressure_hpa, temp_c, humidity, iaq, is_metric, is_final=False,
                              full_refresh=False):
    epd_draw.rectangle((0, 0, 250, 122), fill=255)
    if not is_final:
        epd_draw.text((3, 3), "Altimeter Details", font=font_small, fill=0)
        clock_string = time.strftime("%I:%M %p", time.localtime()).lower()
        clock_width = font_small.getlength(clock_string)
        epd_draw.text((250 - clock_width, 3), clock_string, font=font_small, fill=0)
    else:
        epd_draw.text((3, 3), "Altimeter", font=font_small, fill=0)
        clock_string = "*SLEEP*  @ " + time.strftime("%I:%M %p", time.localtime()).lower()
        clock_width = font_small.getlength(clock_string)
        epd_draw.text((250 - clock_width, 3), clock_string, font=font_small, fill=0)

    epd_draw.line((0, 21, 250, 21), fill=0, width=1)

    if is_metric:
        barometer_string = f"{pressure_hpa:.2f} hPa"
        temperature_string = f"{temp_c:.1f}° C"
    else:
        barometer_string = f"{pressure_hpa * 0.02953:.2f}\""
        temp_f = (temp_c * 9.0 / 5.0) + 32.0
        temperature_string = f"{temp_f:.1f}° F"
    humidity_string = f"{humidity:.1f}%" if humidity is not None else "No Sensor"
    iaq_string = f"{iaq:.0f} ({iaq_quality_to_string(iaq)})" if iaq is not None else "No Sensor"

    sensor_data = [
        ("Altitude", altitude_to_string(altitude_m, 3, is_metric)),
        ("Barometer", barometer_string),
        ("Temp", temperature_string),
        ("Humidity", humidity_string),
        ("IAQ", iaq_string),
    ]

    font_list = font_medium
    start_y = 25
    line_height = 18
    if is_metric:
        left_margin_x = 3
        right_align_x = 220
    else:
        left_margin_x = 16
        right_align_x = 209
    display_list_names_values(sensor_data, font_list, line_height, start_y, left_margin_x, right_align_x)
    refresh_eink_display(epd_disp, epd_draw, epd_image, full_refresh=full_refresh)


def print_gps_metrics(gps: GPS, time_zone_hours: int):
    print("-" * 40)  # Print a separator line.

    if gps is not None and gps.has_fix:
        local_time = get_time_from_gps(gps, time_zone_hours)
        if local_time and getattr(local_time, "tm_hour", None) is not None:
            print(
                f"PDX DST: {local_time.tm_mon}/{local_time.tm_mday}/{local_time.tm_year} {local_time.tm_hour:02}:{local_time.tm_min:02}:{local_time.tm_sec:02}"
            )
        else:
            print("GPS: Waiting for satellite clock...")

        map_string = get_map_string(gps)

        if gps.horizontal_dilution is not None:
            accuracy_string = f"+/- {gps.horizontal_dilution * 2.5:.1f}m"
        else:
            accuracy_string = "accuracy unknown"

        print(f"Map string: {map_string}  (accuracy: {accuracy_string})")
    else:
        print("GPS: Waiting for satellite fix...")

    if gps.altitude_m is not None:
        if gps.vdop is not None:
            est_altitude_string = f"+/- {gps.vdop * 4:.1f}m"
        else:
            est_altitude_string = "N/A (Waiting for data)"
        print(f"Altitude: {gps.altitude_m} meters  (accuracy: {est_altitude_string})")

    if gps.speed_knots is not None:
        print(f"Speed: {gps.speed_knots * 1.15078:.1f} mph")
    if gps.speed_kmh is not None:
        print(f"Speed: {gps.speed_kmh} km/h")

    if gps.satellites is not None:
        print(f"# satellites: {gps.satellites}  (Fix quality: {gps.fix_quality})")

    if gps.track_angle_deg is not None:
        if gps.speed_knots < 2.0:
            print("Heading - Unreliable, speed too low")
        elif gps.speed_knots < 5.0:
            print(f"Heading: {gps.track_angle_deg}° (+/- 15°)")
        else:
            print(f"Heading: {gps.track_angle_deg}° (+/- 2°)")


def gps_clock_string(gps: GPS, time_zone_hours: int):
    if gps is not None:
        local_time = get_time_from_gps(gps, time_zone_hours)
        time_string = f"{local_time.tm_hour:02}:{local_time.tm_min:02}:{local_time.tm_sec:02}"
    return time_string


def display_gps_details(gps, last_gps_fix_time, full_refresh=False):
    """
    display GPS details on screen, protect for None values
    """
    if gps is not None:
        epd_draw.rectangle((0, 0, 250, 122), fill=255)

        # Show header with number of Satellites & quality
        sats = gps.satellites if gps.satellites is not None else 0
        qual = gps.fix_quality if gps.fix_quality is not None else 0
        if gps.has_fix:
            epd_draw.text((3, 2), f"GPS    ({sats} sats, q={qual})", font=font_small, fill=0)
        else:
            epd_draw.text((3, 2), "GPS", font=font_small, fill=0)
            if last_gps_fix_time is None:
                epd_draw.text((45, 0), "** NO FIX **", font=font_medium, fill=0)
            else:
                minutes_since_fix = int((time.monotonic() - last_gps_fix_time) / 60)
                epd_draw.text((45, 0), f"** NO FIX in {minutes_since_fix}min **", font=font_medium, fill=0)

        clock_string = time.strftime("%I:%M %p", time.localtime()).lower()
        clock_width = font_small.getlength(clock_string)
        epd_draw.text((250 - clock_width, 2), clock_string, font=font_small, fill=0)
        epd_draw.line((5, 21, 250, 21), fill=0, width=1)

        # List of GPS metrics
        accuracy_str = f"+/- {gps.vdop * 4:.1f}m" if gps.vdop is not None else "N/A"
        alt_str = f"{gps.altitude_m:.1f}m" if gps.altitude_m is not None else "N/A"
        speed_str = f"{gps.speed_knots * 1.15078:.1f} mph" if gps.speed_knots is not None else "0.0 mph"

        sensor_data = [
            ("Lat", get_lat_string(gps)),
            ("Long", get_lon_string(gps)),
            ("Accuracy", accuracy_str),
            ("Altitude", alt_str),
            ("Speed", speed_str),
        ]

        font_list = font_medium
        start_y = 25
        line_height = 18
        left_margin_x = 2
        right_align_x = 210
        display_list_names_values(sensor_data, font_list, line_height, start_y, left_margin_x, right_align_x)
        refresh_eink_display(epd_disp, epd_draw, epd_image, full_refresh=full_refresh)
        flush_touch_inputs()


def display_big_dashboard(altitude_m, pressure_hpa, iaq, gps, last_gps_fix_time, is_metric, full_refresh=False):
    """
    Display main dashboard
    :param last_gps_fix_time: Timestamp (monotonic) of last valid GPS fix
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    # title
    # epd_draw.text((1, 5), "Altimeter & GPS", font=font_small, fill=0)

    convert, unit = metric_format(is_metric)
    if is_metric:
        alt_string = f"{altitude_m * convert:.1f}"
        long_alt_num_width = font_biggest.getlength("9999.9")
    else:
        alt_string = f"{altitude_m * convert:.1f}"
        long_alt_num_width = font_biggest.getlength("99999.9")

    alt_num_width = font_biggest.getlength(alt_string)
    alt_metric_string = f"{unit}"
    press_string = f"{pressure_hpa:.2f}"

    epd_draw.text((2, 19), "Alt", font=font_small, fill=0)
    epd_draw.text((36 + long_alt_num_width - alt_num_width, 0), alt_string, font=font_biggest, fill=0)

    if is_metric:
        epd_draw.text((28 + long_alt_num_width, 25), alt_metric_string, font=font_medium, fill=0)
    else:
        epd_draw.text((28 + 2 + long_alt_num_width, 0), "'", font=font_biggest, fill=0)

    epd_draw.text((2, 60), "hPa", font=font_small, fill=0)
    epd_draw.text((36, 41), press_string, font=font_biggest, fill=0)

    if gps is not None:
        if gps.latitude is not None and gps.longitude is not None:
            if gps.has_fix:
                epd_draw.text((2, 90), "GPS", font=font_small, fill=0)
                sats = gps.satellites if gps.satellites is not None else 0
                epd_draw.text((2, 104), f"{sats} sats", font=font_small, fill=0)
            else:
                if last_gps_fix_time is not None and last_gps_fix_time > 0:
                    minutes_since_fix = int((time.monotonic() - last_gps_fix_time) / 60)
                    min_str = f"({minutes_since_fix}min)"
                else:
                    min_str = "(--min)"

                epd_draw.text((2, 90), "Last Fix", font=font_small, fill=0)
                epd_draw.text((2, 104), min_str, font=font_small, fill=0)

            lat_string = get_lat_string(gps)
            lon_string = get_lon_string(gps)
            lat_str_width = font_medium.getlength(lat_string)
            lon_str_width = font_medium.getlength(lon_string)
            lon_lat_diff = (lon_str_width - lat_str_width)
            epd_draw.text((64 + lon_lat_diff - 5, 86), lat_string, font=font_medium, fill=0)
            epd_draw.text((64, 104), lon_string, font=font_medium, fill=0)
        else:
            epd_draw.text((55, 95), "Acquiring GPS", font=font_medium, fill=0)
    else:
        epd_draw.text((55, 95), "NO GPS Sensor", font=font_medium, fill=0)

    # Display IAQ warning box, if poor or worse at bottom right of big display 0 mode
    if iaq and iaq > 100.0:
        epd_draw.rectangle((206, 90, 250, 122), fill=0)
        if iaq >= 200.0:
            epd_draw.text((216, 90), "vile", font=font_small, fill=255)
        elif iaq >= 150.0:
            epd_draw.text((214, 90), "bad", font=font_small, fill=255)
        elif iaq >= 100.0:
            epd_draw.text((209, 90), "poor", font=font_small, fill=255)
        epd_draw.text((210, 104), "IAQ !", font=font_small, fill=255)

    refresh_eink_display(epd_disp, epd_draw, epd_image, full_refresh=full_refresh)


# Main ============================================================================
def main():
    global i2c1, sea_level_pressure, slp_hpa_bmp585, slp_hpa_bme680, sys_meters, sys_hpa, sys_temp, sys_humidity, sys_iaq, is_metric

    is_metric = True
    warning_toggle = 0

    print("\nStarting...")
    print("=================================================")
    print(implementation[0], uname()[3], "\nrun on", uname()[4])
    temp = pi_on_chip_temperature()
    print(f"on-chip Pi Zero temp = {temp:.1f}°C")
    print("=================================================")

    i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    scan_i2c_bus(i2c1)
    bmp, bme, error_bmp585, error_bme680, = i2c_initialize_bmp585_bme680(i2c1)

    sea_level_pressure = FALLBACK_SEA_LEVEL_PRESSURE

    # calculate SLP based on nearest airport
    local_airport_string = PDX_STATION_STRING
    local_airport_hpa = PDX_STATION_HPA
    local_airport_meters = feet_to_meters(PDX_STATION_FEET)

    sea_level_pressure = calc_sea_level_pressure(local_airport_hpa, local_airport_meters)
    print(f"\n{local_airport_string}:")
    print(
        f" Local Airport Station: elevation={local_airport_meters:.2f}m, pressure={local_airport_hpa:.2f}, SLP={sea_level_pressure:.2f}")

    # Adjust SLP with calibration constant for BMP585
    sea_level_pressure -= (-0.6634)
    print(f"Corrected SLP with calibration: {sea_level_pressure:.2f}m")

    # try:
    #     with open("last-sea-level-pressure.txt", "r") as data_file:
    #         sea_level_pressure = float(data_file.read().strip())
    #     print(f" * Using previous sea level pressure = {sea_level_pressure:.2f}")
    # except Exception:
    #     print(f" * No previous sea level pressure stored in file")
    #     print(f" * Using fallback sea level pressure ={sea_level_pressure:.2f}")

    # Calibrate BME Barometer
    calibrate_bme_barometer(bme, bmp)

    # Start GPS, Pi Zero uses UART & pyserial library
    sys_meters = 0.0  # or None / default value
    gps = initialize_gps()
    if gps is None:
        print(f" GPS could not be initialized!")
    clock_string = None

    # Initialize state for loop
    first_run = True
    sync_time_requested = True  # True for first time, then every day, at next fix will set system clock

    current_time = time.monotonic()
    last_sensor_update = 0.0  # Force sensor update on the first loop
    # Initialize all update timers to current time
    last_gas_update = last_partial_refresh_eink_update = last_full_refresh_eink_update = last_gps_update = last_clock_set_update = current_time

    last_gps_fix_time = None

    # Initialize metrics
    sys_meters = 0.0
    sys_hpa = 1013.25
    sys_temp = 20.0
    bme_percent_humidity = None
    bme_iaq = None
    sys_iaq = None
    sys_humidity = None

    # GPS - PDX DST -7 hours
    time_zone_hours = -7
    time_zone_string = "PDX"
    day_light_savings_string = "DST"

    prev_alt = None
    prev_press = None

    # E-Ink Display
    display_mode = 0
    full_refresh_mode = None  # Tri-state: True = Full, False = Partial, None = No Refresh
    eink_partial_refresh_count = 0

    print("\nStart of main loop")
    gc.collect()
    while True:
        start_loop_tick = time.monotonic()
        current_time = time.monotonic()

        # Check touch quadrant inputs
        check_touch_buttons()

        # Consume queued button press (from either physical GPIO or touch GT911)
        button_state = get_button()
        eink_update_needed = False

        if button_state is not None:
            # Button 1: Display Mode Toggle (Big Dashboard -> Barometer Details -> GPS Details)
            if button_state == 1:
                display_mode = (display_mode + 1) % 3
                print(f"* Switched to Display Mode: {display_mode}")
                full_refresh_mode = True

            # Button 2: Altitude/SLP Calibration Mode
            elif button_state == 2:
                sea_level_pressure = adjust_altitude_slp(
                    gps=gps,
                    is_metric=is_metric,
                    altitude_m=sys_meters,
                    pressure_hpa=sys_hpa,
                    sea_level_pressure_hpa=sea_level_pressure,
                )
                # Flush residual buttons/touch queued this processing
                clear_pending_button()
                full_refresh_mode = True

            # Button 3: Metric / Imperial Unit Toggle
            elif button_state == 3:
                is_metric = not is_metric
                full_refresh_mode = True

            # Button 4: Oregon Altitude Reference Screen
            elif button_state == 4:
                display_altitude_reference(is_metric)
                # Clear pending inputs so touch inputs during modal display don't trigger actions upon return
                clear_pending_button()
                full_refresh_mode = True

        # Barometer, Temperature, humidity, IAQ (Every 2 seconds)
        if (current_time - last_sensor_update) >= SENSOR_INTERVAL_SEC or first_run:
            last_sensor_update = current_time

            temp = pi_on_chip_temperature()
            if temp > OVER_TEMP_WARNING:
                print(f"WARNING: Pi Zero on-chip temp = {temp:.1f}° C")

            if DEBUG:
                clock_string = time.strftime("%I:%M:%S", time.localtime())
                print(f"\nReading sensors @ {current_time:.2f}s \t{clock_string}")

            if error_bme680 or bme is None:
                print(f"No lower-precision Altitude BME680 sensor: {error_bme680}\n")
            else:
                # IAQ Readings (Every 30 seconds), heats chip substrate
                if (current_time - last_gas_update) >= GAS_INTERVAL_SEC:
                    last_gas_update = current_time
                    print(f"\nBME680 Gas update (every {GAS_INTERVAL_SEC:.0f}s)")
                    gas_ohms = bme.gas
                    bme_percent_humidity = bme.humidity
                    bme_iaq = calculate_iaq(gas_ohms, bme_percent_humidity)
                    print(f"IAQ = {bme_iaq:.1f} ({iaq_quality_to_string(bme_iaq)}), {gas_ohms / 1000.0} Kohms\n")
                    gc.collect()
                else:
                    # Trigger non-gas measurement to cache other BME metrics
                    bme_percent_humidity = bme.humidity

                bme_hpa = bme.pressure
                bme_temp = bme.temperature
                bme_meters = calc_altitude(bme_hpa, sea_level_pressure)
                # print(f"BME680: {bme_hpa} hpa, {bme_temp} °C, {bme_meters} m")

                # Update system with BME680 metrics
                sys_hpa = bme_hpa
                sys_temp = bme_temp
                sys_meters = bme_meters
                sys_humidity = bme_percent_humidity
                sys_iaq = bme_iaq

            if error_bmp585 or bmp is None:
                print(f"No high-precision Altitude bmp585 sensor\n")
            else:
                bmp_hpa = bmp.pressure
                bmp_temp = bmp.temperature
                bmp_meters = calc_altitude(bmp_hpa, sea_level_pressure)

                # Over-write BME680 values with more accurate BMP585 values
                sys_hpa = bmp_hpa
                sys_temp = bmp_temp
                sys_meters = bmp_meters

            print_altimeter_details(sys_meters, sys_hpa, sys_temp, sys_humidity, sys_iaq, is_metric)

            if first_run:
                # Start with Big Dashboard: Display modes: 0 = Big Dashboard, 1 = Altimeter Details, 2 = GPS Details
                first_run = False
                display_mode = 0
                full_refresh_mode = True  # First draw is a Full Refresh

        has_new_gps = gps.update()
        # GPS Refresh (Every 1 seconds)
        if (current_time - last_gps_update) >= GPS_INTERVAL_SEC:
            last_gps_update = current_time
            if gps.has_fix:
                last_gps_fix_time = time.monotonic()
                print_gps_metrics(gps, time_zone_hours)
                if sync_time_requested:
                    if set_pi_system_time_from_gps(gps):
                        last_clock_set_update = current_time
                        # only after successful Pi system time reset, turn off synch request flag
                        sync_time_requested = False
            else:
                if last_gps_fix_time is None:
                    print("...Waiting for GPS fix (no previous fix)")
                else:
                    minutes_since_fix = int((time.monotonic() - last_gps_fix_time) / 60)
                    print(f"...Waiting for GPS fix ({minutes_since_fix} min since last fix)")

            # Every day request that Pi's system time synchronized with GPS
            if (current_time - last_clock_set_update) >= SET_CLOCK_INTERVAL_SEC:
                sync_time_requested = True

            # E-ink Display Refresh: Evaluate timers if no button event forced full_refresh_mode
            time_since_partial = current_time - last_partial_refresh_eink_update
            time_since_full = current_time - last_full_refresh_eink_update

            if full_refresh_mode is None:
                if time_since_partial >= EINK_PARTIAL_REFRESH_SEC:
                    # Force full refresh if partial cycle threshold or time limit reached
                    if (eink_partial_refresh_count >= MAX_EINK_PARTIAL_REFRESH
                            or time_since_full >= EINK_FULL_REFRESH_SEC):
                        full_refresh_mode = True
                    else:
                        full_refresh_mode = False

            # E-Ink Display Render Execution
            if full_refresh_mode is not None:
                if full_refresh_mode:
                    eink_partial_refresh_count = 0
                    last_full_refresh_eink_update = current_time
                else:
                    eink_partial_refresh_count += 1

                last_partial_refresh_eink_update = current_time

                if display_mode == 0:
                    display_big_dashboard(
                        sys_meters, sys_hpa, sys_iaq, gps, last_gps_fix_time,
                        is_metric, full_refresh=full_refresh_mode
                    )
                elif display_mode == 1:
                    display_altimeter_details(
                        sys_meters, sys_hpa, sys_temp, sys_humidity, sys_iaq,
                        is_metric, is_final=False, full_refresh=full_refresh_mode
                    )
                elif display_mode == 2:
                    display_gps_details(
                        gps, last_gps_fix_time, full_refresh=full_refresh_mode
                    )

                # Reset flag and purge residual touch inputs registered during draw cycle
                full_refresh_mode = None
                flush_touch_inputs()
                gc.collect()

        # Sleep to reduce CPU utilization
        if LOOP_STRETCH_SLEEP > 0:
            time.sleep(LOOP_STRETCH_SLEEP)

        # Calculate loop execution time
        end_loop_tick = time.monotonic()
        loop_duration = end_loop_tick - start_loop_tick

        # Loop duration is 50 ms to 60 ms
        # if DEBUG:
        #     print(f"Loop cycle duration: {loop_duration * 1000:.2f} ms")


if __name__ == "__main__":
    import signal
    import atexit

    exit_reason = "Normal Exit"
    cleaned_up = False


    def perform_cleanup():
        global cleaned_up
        if cleaned_up:
            return
        cleaned_up = True

        print(f"\nPerforming teardown [{exit_reason}]...")

        # Render final barometer/altitude details screen before powering down
        try:
            print("Displaying final altitude details"
                  "...")
            display_altimeter_details(
                sys_meters, sys_hpa, sys_temp, sys_humidity, sys_iaq,
                is_metric, is_final=True, full_refresh=True
            )
        except Exception as e:
            print(f"Error drawing final display on exit: {e}")

        # Put E-Ink in Sleep Mode
        try:
            if 'epd_disp' in globals() and epd_disp is not None:
                epd_disp.sleep()
                if hasattr(epd_disp, 'epdconfig'):
                    epd_disp.epdconfig.module_exit()
        except Exception as e:
            print(f"Failed to sleep E-ink display: {e}")

        # I2C Teardown
        try:
            if 'i2c1' in globals() and i2c1 is not None:
                i2c1.close()
        except Exception as e:
            print(f"Failed to close I2C: {e}")

        # Release GPIO
        print("Releasing GPIO devices...")
        for dev_name in ('encoder', 'rotary_switch', 'button_1', 'button_2', 'button_3'):
            if dev_name in globals():
                try:
                    globals()[dev_name].close()
                except Exception as e:
                    print(f"Error closing {dev_name}: {e}")


    # Register exit hook for interpreter termination
    atexit.register(perform_cleanup)


    def handle_exit_signal(sig, frame):
        global exit_reason
        sig_names = {signal.SIGHUP: "SIGHUP (IDE/SSH Disconnect)", signal.SIGTERM: "SIGTERM (Termination Request)"}
        exit_reason = sig_names.get(sig, f"Signal {sig}")
        print(f"\nCaught signal: {exit_reason}")
        raise KeyboardInterrupt


    # Catch standard exit signals
    signal.signal(signal.SIGHUP, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)

    try:
        main()
    except KeyboardInterrupt:
        if exit_reason == "Normal Exit":
            exit_reason = "Ctrl-C (SIGINT)"

        # Ignore further signals during final display refresh
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    finally:
        perform_cleanup()
