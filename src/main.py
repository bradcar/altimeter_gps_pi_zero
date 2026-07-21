# altimeter_gps.py
"""
Raspberry Pi Zero: Altimeter = Elevation & sea level pressure adjust

Sensors used
    - BMP585 highly accurate pressure & altitude
    - BME680 temp, humidity, pressure, IAQ, altitude
    - Rotary encoder to adjust alt and or pressure, switch toggle for larger increments
    - Eink display 240px x 122px
    - Touch display 5 points
    - Metric/Imperial switch

Use sea level pressure at nearest airport

Use nearest airport for sea level pressure
    Portland updated hourly (7 min before the hour)
        https://www.weather.gov/wrh/timeseries?site=KPDX

todo if press set altitude, before first display, altitude_m is undefined, check others
"""

import os
import sys
import serial
import time
from time import sleep as zzz

import adafruit_gps
from adafruit_gps import GPS

from PIL import ImageFont
from gpiozero import Button, RotaryEncoder

from barometer_utils import calc_sea_level_pressure, bme_hpa_correction, calc_altitude
from lib.bme680 import BME680_I2C
from lib.bme680_utils import iaq_quality_to_string, calculate_iaq
from lib.eink_ssd1680_utils import init_eink_display, refresh_eink_display
from lib.gps_utils import get_local_time, get_map_string, get_lat_string, get_lon_string, set_system_time_from_gps
from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_i2c_bridge_utils import PiZeroI2CBridge
from lib.pi_zero_utils import pi_on_chip_temperature, scan_i2c_bus
from metric_imperial_utils import feet_to_meters, metric_format, altitude_to_string

DEBUG = True
DISP_WIDTH = 128
DISP_HEIGHT = 64
OVER_TEMP_WARNING = 70.0

# Timing Constants (in seconds)
LOOP_STRETCH_SLEEP = 0.1  # Small sleep each loop
GPS_INTERVAL_SEC = 1.0  # Read GPS metrics every 1 seconds
SENSOR_INTERVAL_SEC = 2.0  # Read core pressure, temp, & other metrics every 2 seconds
EINK_INTERVAL_SEC = 5.0  # Limit E-ink refresh to every 5 seconds
GAS_INTERVAL_SEC = 30.0  # Read gas IAQ metrics every 30 seconds
SET_CLOCK_INTERVAL_SEC = 24 * 60 * 60  # Set system time every day based on GPS

INIT_SEA_LEVEL_PRESSURE = 1018.10

implementation = [sys.implementation.name]


def uname():
    u = os.uname()
    return [u.sysname, u.nodename, u.release, u.version, u.machine]


# Buttons
# TODO ignore Button 1: cm/in toggle (GPIO 6)
# Button 2: Adjust altitude/SLP (GPIO 5)
#           E-ink: "Up" Button: actually GPIO 6 NOT GPIO 5
# Button 3: Detail/Summary layout toggle (GPIO 15)
#           E-ink: "Down" Button: actually GPIO 5 NOT GPIO 6

button_1 = Button(16, pull_up=True, bounce_time=0.05)
button_2 = Button(5, pull_up=True, bounce_time=0.05)
button_3 = Button(6, pull_up=True, bounce_time=0.05)

# a = clk, b = DT
encoder = RotaryEncoder(a=21, b=13, bounce_time=0.005)
rotary_switch = Button(19, pull_up=True, bounce_time=0.05)

button_1_pushed = False
button_2_pushed = False
button_3_pushed = False

# buzzer = ??

# Initialize the SSD1680 e-ink hardware & Pillow canvas
print("Initialize Eink...")
epd_disp, epd_draw, epd_font_small, epd_image = init_eink_display()
print("Eink Initialized")

# Load custom font sizes using Pillow
try:
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
except IOError:
    font_small = ImageFont.load_default()
    font_medium = ImageFont.load_default()
    font_big = ImageFont.load_default()


# Mimic MicroPython millisecond timers
def ticks_ms():
    return int(time.monotonic() * 1000)


def ticks_diff(t1, t2):
    return t1 - t2


def sleep_ms(ms):
    time.sleep(ms / 1000.0)


time.sleep_ms = sleep_ms

debounce_1_time = 0
debounce_2_time = 0
debounce_3_time = 0


def button_1_handler():
    global button_1_pushed, debounce_1_time
    if (ticks_ms() - debounce_1_time) > 250:
        button_1_pushed = True
        debounce_1_time = ticks_ms()
        debounce_1_time = ticks_ms()


def button_2_handler():
    global button_2_pushed, debounce_2_time
    if (ticks_ms() - debounce_2_time) > 250:
        button_2_pushed = True
        debounce_2_time = ticks_ms()


def button_3_handler():
    global button_3_pushed, debounce_3_time
    if (ticks_ms() - debounce_3_time) > 250:
        button_3_pushed = True
        debounce_3_time = ticks_ms()


button_1.when_pressed = button_1_handler
button_2.when_pressed = button_2_handler
button_3.when_pressed = button_3_handler


def button1():
    global button_1_pushed
    if button_1_pushed:
        button_1_pushed = False
        print("* Button 1 Pushed")
        return True
    else:
        return False


def button2():
    global button_2_pushed
    if button_2_pushed:
        button_2_pushed = False
        print("* Button 2 Pushed")
        return True
    else:
        return False


def button3():
    global button_3_pushed
    if button_3_pushed:
        button_3_pushed = False
        print("* Button 3 Pushed")
        return True
    else:
        return False


def display_list_names_values(altitude_data: list[tuple[str, str]], font_list, line_height: int,
                              start_y: int, left_margin_x: int, right_align_x: int):
    for index, (location, elevation) in enumerate(altitude_data):
        current_y = start_y + (index * line_height)

        epd_draw.text((left_margin_x, current_y), location, font=font_list, fill=0)

        # Right align text
        text_width = font_small.getlength(elevation)
        elevation_x = right_align_x - text_width
        epd_draw.text((elevation_x, current_y), elevation, font=font_list, fill=0)


def altitude_reference_splash(is_metric):
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    epd_draw.text((3, 5), "Oregon Altitudes", font=font_small, fill=0)
    epd_draw.line((5, 21, 240, 21), fill=0, width=1)

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
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=False)
    zzz(5)


def adjust_altitude_slp(gps, is_metric, altitude_m, pressure_hpa, sea_level_pressure_hpa):
    """
    Adjust the altitude using the rotary encoder and update Sea Level Pressure (SLP).
    """
    new_alt = altitude_m
    new_slp = sea_level_pressure_hpa
    rotary_multiplier = 1
    rotary_old = encoder.steps

    print(f"Adjustment start: alt = {new_alt:.1f} m")

    # Initial draw
    need_redraw = True

    while not button2():
        # Keep GPS UART buffer clear in background
        if gps is not None:
            gps.update()

        # Handle unit toggle
        if button1():
            is_metric = not is_metric
            need_redraw = True

        # Handle multiplier toggle switch (press once to toggle x1 / x100)
        if rotary_switch.is_pressed:
            rotary_multiplier = 100 if rotary_multiplier == 1 else 1
            print(f"Rotary multiplier: {rotary_multiplier}")
            while rotary_switch.is_pressed:
                zzz(0.01)

        # Handle encoder movement
        rotary_new = encoder.steps
        if rotary_old != rotary_new:
            delta = rotary_new - rotary_old

            # Step in Meters (1m / 100m) or Feet (1ft / 100ft) based on active unit
            if is_metric:
                new_alt += delta * rotary_multiplier
            else:
                new_alt += (delta * rotary_multiplier) / 3.28084

            new_slp = calc_sea_level_pressure(pressure_hpa, new_alt)
            rotary_old = rotary_new
            need_redraw = True

        # Only refresh E-Ink when an actual state change occurred
        if need_redraw:
            show_updated_altitude_display(new_alt, new_slp, is_metric)
            need_redraw = False

        zzz(0.05)  # Yield CPU to keep utilization low

    # Save newly calculated SLP to disk on exit
    try:
        with open("last-sea-level-pressure.txt", "w") as data_file:
            data_file.write(f"{new_slp:.2f}")
    except Exception as e:
        print(f"Failed to save SLP to file: {e}")

    return new_slp


def show_updated_altitude_display(alt, press, is_metric):
    """
    Renders current calibration values to E-Ink display.
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=0)

    convert, unit = metric_format(is_metric)

    epd_draw.text((10, 5), "Setting Altitude...", font=font_small, fill=255)
    epd_draw.line((10, 23, 240, 23), fill=255, width=1)

    # New Altitude Data
    epd_draw.text((10, 32), "New", font=font_small, fill=255)
    epd_draw.text((10, 46), "Alt", font=font_small, fill=255)

    # Formatted to 0 decimals so text fits comfortably on screen
    # TODO Adjust this for more info on display
    alt_val = f"{(alt * convert):.0f}{unit}"
    epd_draw.text((60, 28), alt_val, font=font_big, fill=255)

    # Sea Level Pressure Data
    epd_draw.text((10, 78), "Sea", font=font_small, fill=255)
    epd_draw.text((10, 92), "hPa", font=font_small, fill=255)

    press_val = f"{press:.1f}"
    epd_draw.text((60, 74), press_val, font=font_big, fill=255)

    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)


def display_altimeter_details(buzz, altitude_m, pressure_hpa, temp_c, humidity, iaq, is_metric):
    epd_draw.rectangle((0, 0, 250, 122), fill=255)
    epd_draw.text((3, 5), "Altimeter Details", font=font_small, fill=0)
    clock_string = time.strftime("%I:%M:%S", time.localtime())
    clock_width = font_small.getlength(clock_string)
    epd_draw.text((240 - clock_width, 5), clock_string, font=font_small, fill=0)

    epd_draw.line((5, 21, 240, 21), fill=0, width=1)

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
    start_y = 27
    line_height = 18
    if is_metric:
        left_margin_x = 1
        right_align_x = 220
    else:
        left_margin_x = 16
        right_align_x = 209
    display_list_names_values(sensor_data, font_list, line_height, start_y, left_margin_x, right_align_x)
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)


def display_gps_details(gps):
    """
    display GPS details on screen, protect for None values

    """
    if gps is not None:
        epd_draw.rectangle((0, 0, 250, 122), fill=255)

        # #sats & quality values with fallbacks if lost or partial fix
        sats = gps.satellites if gps.satellites is not None else 0
        qual = gps.fix_quality if gps.fix_quality is not None else 0
        epd_draw.text((3, 5), f"GPS ({sats} sats, qual={qual})", font=font_small, fill=0)

        clock_string = time.strftime("%I:%M:%S", time.localtime())
        clock_width = font_small.getlength(clock_string)
        epd_draw.text((240 - clock_width, 5), clock_string, font=font_small, fill=0)
        epd_draw.line((5, 21, 240, 21), fill=0, width=1)

        # GPS Metrics
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
        start_y = 27
        line_height = 18
        left_margin_x = 1
        right_align_x = 210
        display_list_names_values(sensor_data, font_list, line_height, start_y, left_margin_x, right_align_x)
        refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)


def display_big_dashboard(buzz, altitude_m, pressure_hpa, iaq, gps, is_metric):
    """
    Display main dashboard
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    # epd_draw.text((1, 5), "Altimeter & GPS", font=font_small, fill=0)

    convert, unit = metric_format(is_metric)
    if is_metric:
        alt_string = f"{altitude_m * convert:.1f}"
        long_alt_num_width = font_big.getlength("9999.9")
    else:
        alt_string = f"{altitude_m * convert:.1f}"
        long_alt_num_width = font_big.getlength("99999.9")

    alt_num_width = font_big.getlength(alt_string)
    alt_metric_string = f"{unit}"
    press_string = f"{pressure_hpa:.2f}"
    press_num_width = font_big.getlength(press_string)
    press_metric_string = f"hpa"

    epd_draw.text((0, 6), f"Alt", font=font_small, fill=0)
    epd_draw.text((35 + long_alt_num_width - alt_num_width, 0), alt_string, font=font_big, fill=0)

    if is_metric:
        epd_draw.text((28 + long_alt_num_width, 25), alt_metric_string, font=font_medium, fill=0)
    else:
        epd_draw.text((28 + 2 + long_alt_num_width, 0), "'", font=font_big, fill=0)

    epd_draw.text((0, 48), f"hPa", font=font_small, fill=0)
    epd_draw.text((35, 41), press_string, font=font_big, fill=0)
    # epd_draw.text((35 + press_num_width + 3, 41 + 9), press_metric_string, font=font_medium, fill=0)

    epd_draw.text((0, 88), f"GPS", font=font_small, fill=0)
    if gps is not None:
        lat_string = get_lat_string(gps)
        lon_string = get_lon_string(gps)
        lat_str_width = font_medium.getlength(lat_string)
        lon_str_width = font_medium.getlength(lon_string)
        lon_lat_diff = (lon_str_width - lat_str_width)
        epd_draw.text((60 + lon_lat_diff - 5, 87), lat_string, font=font_medium, fill=0)
        epd_draw.text((60, 105), lon_string, font=font_medium, fill=0)
    else:
        epd_draw.text((60, 88), "Acquiring GPS", font=font_medium, fill=0)

    # Flash IAQ warning (black banner with white text in the top right)
    if iaq and iaq > 150.0:
        epd_draw.rectangle((180, 2, 240, 20), fill=0)
        epd_draw.text((192, 4), "IAQ!", font=font_small, fill=255)

    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)


def print_gps_metrics(gps: GPS, time_zone_hours: int):
    print()
    print("=" * 40)  # Print a separator line.

    if gps is not None and gps.has_fix:
        local_time = get_local_time(gps, time_zone_hours)
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

        print(f"Map string: {map_string} ({accuracy_string})")
    else:
        print("GPS: Waiting for satellite fix...")

    if gps.altitude_m is not None:
        if gps.vdop is not None:
            est_altitude_string = f"+/- {gps.vdop * 4:.1f}m"
        else:
            est_altitude_string = "N/A (Waiting for data)"
        print(f"Altitude: {gps.altitude_m} meters ({est_altitude_string})")

    if gps.speed_knots is not None:
        print(f"Speed: {gps.speed_knots * 1.15078:.1f} mph")
    if gps.speed_kmh is not None:
        print(f"Speed: {gps.speed_kmh} km/h")

    if gps.satellites is not None:
        print(f"# satellites: {gps.satellites} (Fix quality: {gps.fix_quality})")

    if gps.track_angle_deg is not None:
        if gps.speed_knots < 2.0:
            print("Heading: Unreliable (Speed too low)")
        elif gps.speed_knots < 5.0:
            print(f"Heading: {gps.track_angle_deg}° (+/- 15°)")
        else:
            print(f"Heading: {gps.track_angle_deg}° (+/- 2°)")


def gps_clock_string(gps: GPS, time_zone_hours: int):
    if gps is not None:
        local_time = get_local_time(gps, time_zone_hours)
        time_string = f"{local_time.tm_hour:02}:{local_time.tm_min:02}:{local_time.tm_sec:02}"
    return time_string


def main():
    global SLP_CALIBRATION_BMP585, SLP_CALIBRATION_BME680, i2c1, sea_level_pressure, slp_hpa_bmp585, slp_hpa_bme680

    is_metric = False
    warning_toggle = 0

    print("\nStarting...")
    print("=================================================")
    print(implementation[0], uname()[3], "\nrun on", uname()[4])
    temp = pi_on_chip_temperature()
    print(f"on-chip Pi Zero temp = {temp:.1f}°C")
    print("=================================================")

    i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    scan_i2c_bus(i2c1)

    # Initialize Barometers: BMP585, BME680
    error_bme680 = False
    error_bmp585 = False
    try:
        bme = BME680_I2C(i2c=i2c1, address=0x77)
        bme_exists = True
        print("BME680 initialized")
    except Exception as e:
        error_bme680 = True
        bme_exists = False
        print(f"ERROR: BME680 not initialized: {e}")

    try:
        bmp = bmpxxx.BMP585(i2c=i2c1, address=0x47)
        bmp_exists = True
        bmp.pressure_oversample_rate = bmp.OSR128
        bmp.temperature_oversample_rate = bmp.OSR8
        bmp.iir_coefficient = bmp.COEF_7
        print("BMP585 initialized\n")

    except Exception as e:
        bmp_exists = False
        error_bmp585 = True
        print(f"ERROR: BMP585 not initialized: {e}")

    try:
        with open("last-sea-level-pressure.txt", "r") as data_file:
            sea_level_pressure = float(data_file.read().strip())
        print(f"Using previous sea level pressure = {sea_level_pressure}")
    except Exception:
        sea_level_pressure = INIT_SEA_LEVEL_PRESSURE
        print(f"No previous sea level pressure stored in file")
        print(f"Using program sea level pressure in constant ={sea_level_pressure}")

    # Calibrate Barometers
    average_diff = 1.0312750  # fallback hPa correction for BME680, if no BMP585
    if bmp_exists and bme_exists:
        average_diff = bme_hpa_correction(bme, bmp, 25)
        print(f"BMP585 calibration for BME680 = {average_diff:.7f} hPa")
    elif bme_exists:
        print(f"No BMP585 to calibrate BME680, using default {average_diff:.7f} hPa")
        # the amount over will be subtracted in calibration code.

    bme.hpa_calibration = average_diff
    if bme.hpa_calibration is not None:
        print(f"BME680 calibrated with = {average_diff:.7f} hPa")
    else:
        print(f"ERROR IN BME680 hpa_calibration = None!")

    # Start GPS
    # GPS on Pi Zero uses UART with pyserial library
    print("Initialize GPS...")
    uart = serial.Serial("/dev/serial0", baudrate=9600, timeout=10)
    gps = adafruit_gps.GPS(uart, debug=False)

    # Turn on the basic GGA, RMC, GGA(Accuracy), update time 1sec, 1Hz (check UART timeout)
    gps.send_command(b"PMTK314,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
    gps.send_command(b"PMTK220,1000")
    clock_string = None
    print("GPS Initialized")

    # if buzzer_sound: buzzer.on()
    # zzz(.2)
    # buzzer.off()

    altitude_reference_splash(is_metric)

    # main loop variables

    # show_env_details = False

    # Display modes: 0 = Big Dashboard, 1 = Altimeter Details, 2 = GPS Details
    display_mode = 0

    buzzer_sound = True

    # Store previous values to detect actual changes
    prev_alt = None
    prev_press = None

    first_run = True
    sync_time_requested = True  # True for first time, then every day, at next fix will set system clock

    current_time = time.monotonic()
    last_sensor_time = 0.0  # Force instant execution on the first loop
    last_gas_time = current_time
    last_eink_time = current_time
    last_gps_time = current_time
    last_clock_set_time = current_time

    # Initialize metrics
    altitude_m = 0.0
    pressure_hpa = 1013.25
    temp_c = 20.0
    bme_percent_humidity = None
    bme_iaq = None
    iaq = None
    humidity = None

    # GPS
    # PDX DST -7 hours
    time_zone_hours = -7
    time_zone_string = "PDX"
    day_light_savings_string = "DST"

    prev_alt = None
    prev_press = None
    first_run = True

    print("\nstart of main loop")

    # main loop
    while True:
        start_loop_tick = time.monotonic()
        current_time = time.monotonic()

        if button1():
            is_metric = not is_metric

        if button2():
            sea_level_pressure = adjust_altitude_slp(
                gps=gps,
                is_metric=is_metric,
                altitude_m=altitude_m,
                pressure_hpa=pressure_hpa,
                sea_level_pressure_hpa=sea_level_pressure,
            )

        if button3():
            # show_env_details = not show_env_details
            display_mode = (display_mode + 1) % 3

        # Temperature and standard ambient metrics (Every 2 seconds)
        if (current_time - last_sensor_time) >= SENSOR_INTERVAL_SEC or first_run:
            last_sensor_time = current_time

            if DEBUG:
                print(f"Reading standard sensors at {current_time:.2f}s")

            temp = pi_on_chip_temperature()
            if temp > OVER_TEMP_WARNING:
                print(f"WARNING: Pi Zero on-chip temp = {temp:.1f}° C")

            if error_bme680:
                print(f"No lower-precision Altitude BME680 sensor: {error_bme680}\n")
            else:
                # IAQ Readings (Every 30 seconds), heats chip substrate
                if (current_time - last_gas_time) >= GAS_INTERVAL_SEC:
                    last_gas_time = current_time
                    print(f"\nBME680 Gas measurement (every {GAS_INTERVAL_SEC:.0f}s)")
                    gas_ohms = bme.gas
                    bme_percent_humidity = bme.humidity
                    bme_iaq = calculate_iaq(gas_ohms, bme_percent_humidity)
                    print(f"IAQ = {bme_iaq:.1f} ({iaq_quality_to_string(bme_iaq)}), {gas_ohms / 1000.0} Kohms")
                else:
                    # Trigger non-gas measurement to cache other BME metrics
                    bme_percent_humidity = bme.humidity

                bme_hpa = bme.pressure
                bme_temp = bme.temperature
                bme_meters = calc_altitude(bme_hpa, sea_level_pressure)
                print(f"BME680: {bme_hpa}, {bme_temp}, {bme_meters}")

                # Set all metrics with BME680
                pressure_hpa = bme_hpa
                temp_c = bme_temp
                altitude_m = bme_meters
                humidity = bme_percent_humidity

                iaq = bme_iaq

            if error_bmp585:
                print(f"No high-precision Altitude bmp585 sensor\n")
            else:
                bmp_hpa = bmp.pressure
                bmp_temp = bmp.temperature
                bmp_meters = calc_altitude(bmp_hpa, sea_level_pressure)

                # Over-write BME680 values with more accurate BMP585 values
                pressure_hpa = bmp_hpa
                temp_c = bmp_temp
                altitude_m = bmp_meters
                print(f"system: {pressure_hpa}, {temp_c}, {altitude_m}\n")

            if error_bme680 and error_bmp585:
                print("Critical Error: No altitude sensors available.")
                break

            first_run = False

        has_new_gps = gps.update()
        # GPS Refresh (Every 1 seconds)
        if (current_time - last_gps_time) >= GPS_INTERVAL_SEC:
            last_gps_time = current_time
            if gps.has_fix:
                print_gps_metrics(gps, time_zone_hours)
                if sync_time_requested:
                    if set_system_time_from_gps(gps):
                        last_clock_set_time = current_time
                        # only after successful time set, turn off sych request flag
                        sync_time_requested = False
            else:
                print("Waiting for fix...")

        # Every day request that systems time synchronized with GPS
        if (current_time - last_clock_set_time) >= SET_CLOCK_INTERVAL_SEC:
            sync_time_requested = True

        # E-ink Display Refresh (Every 5 seconds)
        if (current_time - last_eink_time) >= EINK_INTERVAL_SEC:
            # TODO validate need for values_changed (seems better to let Eink partial updates)
            values_changed = False
            if prev_alt is None or abs(altitude_m - prev_alt) > 0.05 or abs(pressure_hpa - prev_press) > 0.02:
                values_changed = True

            # Instant trigger if a button action set a flag
            button_pressed = button_1_pushed or button_2_pushed or button_3_pushed

            if values_changed or button_pressed:
                last_eink_time = current_time  # Reset timer if push pixels
                prev_alt = altitude_m
                prev_press = pressure_hpa

                buzzer_sound = None
                if display_mode == 0:
                    display_big_dashboard(buzzer_sound, altitude_m, pressure_hpa, iaq, gps, is_metric)
                elif display_mode == 1:
                    display_altimeter_details(buzzer_sound, altitude_m, pressure_hpa, temp_c, humidity, iaq, is_metric)
                elif display_mode == 2:
                    display_gps_details(gps)

        # Loop cadence control
        # Optional stretch sleep to keep CPU utilization reasonable
        if LOOP_STRETCH_SLEEP > 0:
            time.sleep(LOOP_STRETCH_SLEEP)

        # Calculate loop execution time
        end_loop_tick = time.monotonic()
        loop_duration = end_loop_tick - start_loop_tick

        # Loop duration is 50 ms to 60 ms
        # if DEBUG:
        #     print(f"Loop cycle duration: {loop_duration * 1000:.2f} ms")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit (Ctrl-C)")

    except Exception as e:
        print(f"\nProgram unexpected crash: {e}")

    finally:
        try:
            i2c1.close()
        except Exception as e:
            print(f"Failed to close I2C: {e}")
        try:
            # epd_disp.sleep()
            epd_disp.power_down()
        except Exception as e:
            print(f"Failed to sleep E-ink display: {e}")
