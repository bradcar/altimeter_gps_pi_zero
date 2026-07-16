# altimeter_gps.py
"""
Raspberry Pi Zero: Altimeter = Elevation & sea level pressure adjust
"""

import time
from math import log
import os
import sys
from time import sleep as zzz

from gpiozero import Button, RotaryEncoder
from periphery import I2C

from lib.bme680_utils import iaq_quality_to_string
from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_i2c_bridge_utils import PiZeroI2CBridge
from lib.pi_zero_utils import pico_temperature, scan_i2c_bus
from lib.bme680 import BME680_I2C
from eink_utils import init_eink_display, blank_canvas_eink, refresh_eink_display
from PIL import ImageFont, ImageDraw, Image

DEBUG = True

DISP_WIDTH = 128
DISP_HEIGHT = 64
DWELL_MS_LOOP = 300
OVER_TEMP_WARNING = 70.0

implementation = [sys.implementation.name]


def uname():
    u = os.uname()
    return [u.sysname, u.nodename, u.release, u.version, u.machine]


# Buttons
# todo ignore Button 1: cm/in toggle (GPIO 6)
# Button 2: Adjust altitude/SLP (GPIO 5)
#           E-ink: "Up" Button: actually GPIO 6 NOT GPIO 5
# Button 3: Detail/Summary layout toggle (GPIO 15)
#           E-ink: "Down" Button: actually GPIO 5 NOT GPIO 6

button_1 = Button(16, pull_up=True, bounce_time=0.05)
button_2 = Button(5, pull_up=True, bounce_time=0.05)
button_3 = Button(6, pull_up=True, bounce_time=0.05)

encoder = RotaryEncoder(a=13, b=19, bounce_time=0.005)
rotary_switch = Button(26, pull_up=True, bounce_time=0.05)

button_1_pushed = False
button_2_pushed = False
button_3_pushed = False

# buzzer = ??

# Initialize the SSD1680 e-ink hardware & Pillow canvas
epd_disp, epd_draw, epd_font_small, epd_image = init_eink_display()

# Load custom font sizes using Pillow
try:
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
except IOError:
    # Fallback to default if DejaVu isn't installed on the system
    font_small = ImageFont.load_default()
    font_big = ImageFont.load_default()


# Mimick MicroPython millisecond timers
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
    if (ticks_ms() - debounce_1_time) > 500:
        button_1_pushed = True
        debounce_1_time = ticks_ms()


def button_2_handler():
    global button_2_pushed, debounce_2_time
    if (ticks_ms() - debounce_2_time) > 500:
        button_2_pushed = True
        debounce_2_time = ticks_ms()


def button_3_handler():
    global button_3_pushed, debounce_3_time
    if (ticks_ms() - debounce_3_time) > 500:
        button_3_pushed = True
        debounce_3_time = ticks_ms()


button_1.when_pressed = button_1_handler
button_2.when_pressed = button_2_handler
button_3.when_pressed = button_3_handler


def button1():
    global button_1_pushed
    if button_1_pushed:
        button_1_pushed = False
        return True
    else:
        return False


def button2():
    global button_2_pushed
    if button_2_pushed:
        button_2_pushed = False
        return True
    else:
        return False


def button3():
    global button_3_pushed
    if button_3_pushed:
        button_3_pushed = False
        return True
    else:
        return False


def calc_sea_level_pressure(hpa, meters):
    sea_level_pressure = hpa / (1.0 - (meters / 44330.77)) ** (1 / 0.1902632)
    return sea_level_pressure


def calc_altitude(hpa, sea_level_pressure):
    meters = 44330.77 * (1.0 - (hpa / sea_level_pressure) ** 0.1902632)
    return meters


def bmp585_sensor(sea_level_pressure):
    debug = True
    try:
        celsius = bmp.temperature
        hpa_pressure = bmp.pressure
        meters = calc_altitude(hpa_pressure, sea_level_pressure)

        if debug:
            print(f"BMP585 Temp °C = {celsius:.2f} C")
            print(f"BMP585 Pressure = {hpa_pressure:.2f} hPA")
            print(f"BMP585 Alt = {meters * 3.28084:.2f} feet\n")
    except OSError as e:
        print("BMP585: Failed to read sensor.")
        return None, None, None, "ERROR_BMP680:" + str(e)
    return celsius, hpa_pressure, meters, None


def calculate_iaq(gas_ohms, percent_humidity):
    if 0 <= percent_humidity <= 40:
        humidity_score = 25.0 * ((40 - percent_humidity) / 40) ** 2
    elif 40 < percent_humidity <= 60:
        humidity_score = 0.0
    elif 60 < percent_humidity <= 100:
        humidity_score = 25.0 * ((percent_humidity - 60) / 40) ** 2
    else:
        humidity_score = None

    ln_iaq = log(gas_ohms)
    iaq = (9.4751 * (ln_iaq) ** 2 - 316.31 * (ln_iaq) + 2524.0) + 6 * humidity_score
    return max(0, min(500.0, iaq))


def bme680_sensor(sea_level_pressure):
    debug = True
    try:
        celsius = bme.temperature
        percent_humidity = bme.humidity
        hpa_pressure = bme.pressure
        iaq_value = calculate_iaq(bme.gas, percent_humidity)
        meters = calc_altitude(hpa_pressure, sea_level_pressure)

        if debug:
            print(f"BME680 Temp °C = {celsius:.2f} C")
            print(f"BME680 Humidity = {percent_humidity:.1f} %")
            print(f"BME680 Pressure = {hpa_pressure:.2f} hPA")
            print(f"BME680 iaq = {iaq_value:.1f} {iaq_quality_to_string(iaq_value)}")
            print(f"BME680 Alt = {meters * 3.28084:.2f} feet\n")
    except OSError as e:
        print("BME680: Failed to read sensor.")
        return None, None, None, None, None, "ERROR_BME680:" + str(e)
    return celsius, percent_humidity, hpa_pressure, iaq_value, meters, None


def metric_format():
    """
    Metric format
    :return:
        conversion factor and string denotation
    """
    if is_metric:
        unit = " m"
        convert = 1.0
    else:
        unit = "'"
        convert = 3.28084
    return convert, unit


def altitude_to_string(altitude_m):
    if is_metric:
        unit = " m"
        convert = 1.0
    else:
        unit = "'"
        convert = 3.28084
    altitude_string = f"{altitude_m * convert:.0f}{unit}"
    return altitude_string


def altitude_reference_splash():
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    epd_draw.text((3, 5), "Oregon Altitudes", font=font_small, fill=0)
    epd_draw.line((5, 21, 240, 21), fill=0, width=1)  # Thin separator line

    b = 27
    y = 16
    x1 = 15
    x2 = 150
    x3 = 160
    epd_draw.text((x1, b + 0 * y), "Garage:", font=font_small, fill=0)
    epd_draw.text((x3, b + 0 * y), "339'", font=font_small, fill=0)
    epd_draw.text((x1, b + 1 * y), "Sylvan:", font=font_small, fill=0)
    epd_draw.text((x3, b + 1 * y), "761'", font=font_small, fill=0)
    epd_draw.text((x1, b + 2 * y), "Meadows Main:", font=font_small, fill=0)
    epd_draw.text((x2, b + 2 * y), "5003'", font=font_small, fill=0)
    epd_draw.text((x1, b + 3 * y), "Meadows HRM:", font=font_small, fill=0)
    epd_draw.text((x2, b + 3 * y), "4540'", font=font_small, fill=0)
    epd_draw.text((x1, b + 4 * y), "Bachelor Main:", font=font_small, fill=0)
    epd_draw.text((x2, b + 4 * y), "6207'", font=font_small, fill=0)
    epd_draw.text((x1, b + 5 * y), "Rock Gym Beav:", font=font_small, fill=0)
    epd_draw.text((x3, b + 5 * y), "122'", font=font_small, fill=0)
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=False)

    # Hold the splash screen list
    zzz(20)


def display_details(buzz):
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    if is_metric:
        epd_draw.text((10, 5), f"Alt: {altitude_m:.3f} m", font=font_small, fill=0)
        epd_draw.text((10, 25), f"Baro: {pressure_hpa:.2f} hPa", font=font_small, fill=0)
        epd_draw.text((10, 45), f"Temp: {temp_c:.1f} C", font=font_small, fill=0)

    else:
        epd_draw.text((10, 5), f"Alt: {altitude_m * 3.28084:.0f}'", font=font_small, fill=0)
        epd_draw.text((10, 25), f"Baro: {pressure_hpa * 0.02953:.2f}\"", font=font_small, fill=0)
        epd_draw.text((10, 45), f"Temp: {temp_f:.1f} F", font=font_small, fill=0)


    hum_str = f"Humidity: {humidity:.1f}%" if humidity else "Hum: No Sensor"
    iaq_str = f"IAQ: {iaq:.0f} ({iaq_quality_to_string(iaq)})" if iaq else "IAQ: No Sensor"

    epd_draw.text((10, 65), hum_str, font=font_small, fill=0)
    epd_draw.text((10, 85), iaq_str, font=font_small, fill=0)

    # Prepare for partial update
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)


def display_big_num(buzz):
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    epd_draw.text((10, 5), "ALTIMETER & GPS", font=font_small, fill=0)

    convert, unit = metric_format()

    # Display primary dashboard values
    alt_val = f"{altitude_m * convert:.0f}{unit}"
    press_val = f"{pressure_hpa:.1f} hPa"

    epd_draw.text((15, 30), f"ALT:  {alt_val}", font=font_big, fill=0)
    epd_draw.text((15, 65), f"PRES: {press_val}", font=font_big, fill=0)

    # Flash IAQ warning (black banner with white text in the top right)
    if iaq and iaq > 150.0:
        epd_draw.rectangle((180, 2, 240, 20), fill=0)
        epd_draw.text((192, 4), "IAQ!", font=font_small, fill=255)

    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)


def update_settings_display(alt, press):
    """
    Update settings
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=0)

    convert, unit = metric_format()

    epd_draw.text((10, 8), "SETTING ALTITUDE...", font=font_small, fill=255)
    epd_draw.line((10, 26, 240, 26), fill=255, width=1)

    # New Altitude Data
    # Small stacked labels on the left side
    epd_draw.text((15, 38), "NEW", font=font_small, fill=255)
    epd_draw.text((15, 52), "ALT", font=font_small, fill=255)
    # Big target value on the right side
    alt_val = f"{(alt * convert):.0f}{unit}"
    epd_draw.text((85, 38), alt_val, font=font_big, fill=255)

    # Sea Level Pressure Data
    # Small stacked labels on the left side
    epd_draw.text((15, 78), "SEA", font=font_small, fill=255)
    epd_draw.text((15, 92), "hPA", font=font_small, fill=255)
    # Big target value on the right side
    press_val = f"{press:.1f}"
    epd_draw.text((85, 78), press_val, font=font_big, fill=255)

    # Push visual updates (use partial refresh for fast response during rotation)
    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)
    return


def adjust_altitude_slp(buzz, bmp_update):
    global is_metric, sea_level_pressure, slp_hpa_bme680, slp_hpa_bmp585

    new_alt = altitude_m
    if bmp_update:
        adjust = SLP_CALIBRATION_BMP585
        new_slp = slp_hpa_bmp585 - adjust
    else:
        adjust = SLP_CALIBRATION_BME680
        new_slp = slp_hpa_bme680 - adjust

    print(f"Adjustment start: alt= {new_alt} m, {new_alt * 3.28084} ft")
    print(f"global slp values={slp_hpa_bmp585=}, {slp_hpa_bme680=}\n")
    print(f"updating: {'bmp585' if bmp_update else 'bme680'}")
    print(f"{new_slp=}: {new_slp=}")

    # if buzz:
    #     buzzer.on()
    #     zzz(.2)
    #     buzzer.off()
    update_settings_display(altitude_m, new_slp)

    rotary_multiplier = 1
    rotary_old = encoder.steps
    while not button2():

        if button1():
            is_metric = not is_metric

        new_alt_feet = new_alt * 3.28084

        rotary_new = encoder.steps
        if rotary_switch.is_pressed:
            rotary_multiplier = 1 if rotary_multiplier != 1 else 100
            while rotary_switch.is_pressed:
                zzz(0.01)

        if rotary_old != rotary_new:
            delta = rotary_new - rotary_old
            new_alt_feet = new_alt_feet + delta * rotary_multiplier
            rotary_old = rotary_new
            if DEBUG: print(f"{new_alt_feet=}")

        new_alt = new_alt_feet / 3.28084
        new_slp = calc_sea_level_pressure(pressure_hpa, new_alt) - adjust
        if DEBUG:
            print(f"{new_alt=}, {new_alt_feet=}")
            print(f"updating: {'bmp585' if bmp_update else 'bme680'}")
            print(f"{new_slp=}, {slp_hpa_bmp585=}, {slp_hpa_bme680=}")
        update_settings_display(new_alt, new_slp)

    # if buzz:
    #     buzzer.on()
    #     zzz(.2)
    #     buzzer.off()

    sea_level_pressure = new_slp
    print(f"Adjustment end:   alt= {new_alt} m, {new_alt * 3.28084} ft")
    print(f"At End: {new_slp=}\n")

    with open("last-sea-level-pressure.txt", "w") as data_file:
        data_file.write(f"{new_slp}")

    return


show_env_details = False
set_known = False
buzzer_sound = True
is_metric = True

INIT_SEA_LEVEL_PRESSURE = 1018.10
SLP_CALIBRATION_BMP585 = -0.1931
SLP_CALIBRATION_BME680 = 1.0147

warning_toggle = 0

print("Starting...")
print("=================================================")
print(implementation[0], uname()[3], "\nrun on", uname()[4])
temp = pico_temperature()
print(f"on-chip Pi Zero temp = {temp:.1f}°C")
print("=================================================")

i2c1 = PiZeroI2CBridge("/dev/i2c-1")
scan_i2c_bus(i2c1)

error_bme680 = False
error_bmp585 = False
try:
    bme = BME680_I2C(i2c=i2c1, address=0x77)
    print("BME680 initialized")
except Exception as e:
    error_bme680 = True
    print(f"ERROR: init BME680_I2C(i2c=i2c, address=0x77): {e}")

try:
    bmp = bmpxxx.BMP585(i2c=i2c1, address=0x47)
    bmp.pressure_oversample_rate = bmp.OSR128
    bmp.temperature_oversample_rate = bmp.OSR8
    bmp.iir_coefficient = bmp.COEF_7
    print("BMP585 initialized\n")

except Exception as e:
    error_bmp585 = True
    print(f"ERROR: init bmp58x.BMP585(i2c=i2c, address=0x47): {e}")

try:
    with open("last-sea-level-pressure.txt", "r") as data_file:
        sea_level_pressure = float(data_file.read().strip())
    print(f"Using previous sea level pressure = {sea_level_pressure}")
except Exception:
    sea_level_pressure = INIT_SEA_LEVEL_PRESSURE
    print(f"No previous sea level pressure stored in file")
    print(f"Using program sea level pressure in constant ={sea_level_pressure}")

slp_hpa_bmp585 = sea_level_pressure + SLP_CALIBRATION_BMP585
slp_hpa_bme680 = sea_level_pressure + SLP_CALIBRATION_BME680

# if buzzer_sound: buzzer.on()
# zzz(.2)
# buzzer.off()


altitude_reference_splash()

# main loop variables
last_eink_update = time.ticks_ms()
UPDATE_INTERVAL_MS = 5000  # Cap E-ink refresh to once every 5 seconds maximum

# Store previous values to detect actual changes
prev_alt = None
prev_press = None

# main loop
print("start of main loop\n")
first_run = True
time_since_last_temp_update = ticks_ms()
try:
    while True:
        dwell = DWELL_MS_LOOP
        loop_time = ticks_ms()
        elapsed_time = ticks_diff(ticks_ms(), time_since_last_temp_update)
        if DEBUG: print(f"Time since last temp ={elapsed_time}")

        if button1():
            is_metric = not is_metric

        if button2():
            adjust_altitude_slp(True, bmp_update=not error_bmp585)
            print(f"Adjusted sea level pressure = {sea_level_pressure:.2f} hpa")
            print(f"Calibrated BMP585 Sea level = {slp_hpa_bmp585:.2f} hpa")
            print(f"Calibrated BME680 Sea level = {slp_hpa_bme680:.2f} hpa\n")

        if button3():
            show_env_details = not show_env_details

        if first_run or elapsed_time > 2000:
            dwell = DWELL_MS_LOOP - 189
            time_since_last_temp_update = ticks_ms()

            temp = pico_temperature()
            if temp > OVER_TEMP_WARNING:
                print(f"WARNING: on-chip Pi Zero temp = {temp:.1f}° C")

            slp_hpa_bmp585 = sea_level_pressure + SLP_CALIBRATION_BMP585
            slp_hpa_bme680 = sea_level_pressure + SLP_CALIBRATION_BME680

            if error_bme680:
                print(f"No lower-precision Altitude BME680 sensor: {error_bme680}\n")
            else:
                temp_c_bme680, humidity_bme680, hpa_bme680, iaq_bme680, alt_m_bme680, error_bme680 = bme680_sensor(
                    slp_hpa_bme680)

            first_run = False

            if error_bmp585:
                print(f"No high-precision Altitude bmp585 sensor\n")
            else:
                temp_c_bmp585, hpa_bmp585, alt_m_bmp585, error_bmp585 = bmp585_sensor(slp_hpa_bmp585)

            temp_c, humidity, pressure_hpa, iaq, altitude_m, temp_f = (None,) * 6

            if error_bme680 and error_bmp585:
                print("Error, 0, 0, 1")
                print(f"OLED: No Alt Sensors:, 5, 12, 0")
                print(f"OLED: BMP585 & BME680, 5, 21, 0")
                break

            if not error_bme680:
                temp_c = temp_c_bme680
                humidity = humidity_bme680
                altitude_m = alt_m_bme680
                pressure_hpa = hpa_bme680
                iaq = iaq_bme680

            if not error_bmp585:
                temp_c = temp_c_bmp585
                altitude_m = alt_m_bmp585
                pressure_hpa = hpa_bmp585
            temp_f = (temp_c * 9.0 / 5.0) + 32.0
            first_run = False

        time.sleep_ms(dwell)

        # Check if we should push a screen refresh
        now = time.ticks_ms()
        time_since_refresh = time.ticks_diff(now, last_eink_update)

        # Determine if values changed significantly
        values_changed = False
        if prev_alt is None or abs(altitude_m - prev_alt) > 0.5 or abs(pressure_hpa - prev_press) > 0.2:
            values_changed = True

        # Check if a button was pressed (which requires instant visual feedback)
        button_pressed = button_1_pushed or button_2_pushed or button_3_pushed

        # Trigger refresh ONLY if interval has elapsed AND (data changed OR button was pressed)
        if time_since_refresh >= UPDATE_INTERVAL_MS and (values_changed or button_pressed):

            # Save state to prevent double fires
            prev_alt = altitude_m
            prev_press = pressure_hpa
            last_eink_update = now

            # todo buzzer_sound
            buzzer_sound = None
            if show_env_details:
                display_details(buzzer_sound)
            else:
                display_big_num(buzzer_sound)

except KeyboardInterrupt:
    # Clean visual exit and close Linux resources
    # oled.fill(0)
    # oled.show()
    i2c1.close()
    # oled_spi.close()
    print("Exit: ctrl-c")
