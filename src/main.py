# altimeter_gps.py
"""
Raspberry Pi Zero: Altimeter = Elevation & sea level pressure adjust
"""

import os
import sys
import time
from time import sleep as zzz

from PIL import ImageFont
from gpiozero import Button, RotaryEncoder

from barometer_utils import bmp585_sensor, bme680_sensor, calc_sea_level_pressure
from lib.bme680 import BME680_I2C
from lib.bme680_utils import iaq_quality_to_string
from lib.eink_ssd1680_utils import init_eink_display, refresh_eink_display
from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_i2c_bridge_utils import PiZeroI2CBridge
from lib.pi_zero_utils import pico_temperature, scan_i2c_bus
from metric_imperial_utils import feet_to_meters, metric_format, altitude_to_string

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
    font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
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


# Definition with parameters instead of global dependencies:
def adjust_altitude_slp(buzz, bmp_update, is_metric, altitude_m, pressure_hpa,
                        slp_hpa_bme680, slp_hpa_bmp585, cal_bme680, cal_bmp585):
    """
    Adjust the altitude in the desired metric, use it to return a new Sea Level Pressure (SLP)
    :param buzz:
    :param bmp_update:
    :param is_metric:
    :param altitude_m:
    :param pressure_hpa:
    :param slp_hpa_bme680:
    :param slp_hpa_bmp585:
    :param cal_bme680:
    :param cal_bmp585:
    :return:
    """
    new_alt = altitude_m
    if bmp_update:
        adjust = cal_bmp585
        new_slp = slp_hpa_bmp585 - adjust
    else:
        adjust = cal_bme680
        new_slp = slp_hpa_bme680 - adjust

    print(f"Adjustment start: alt= {new_alt} m, {new_alt * 3.28084} ft")
    update_settings_display(new_alt, new_slp, is_metric)

    rotary_multiplier = 1
    rotary_old = encoder.steps
    while not button2():
        if button1():
            is_metric = not is_metric

        new_alt_feet = new_alt * 3.28084
        rotary_new = encoder.steps

        if rotary_switch.is_pressed:
            rotary_multiplier = 100 if rotary_multiplier == 1 else 1
            while rotary_switch.is_pressed:
                zzz(0.01)

        if rotary_old != rotary_new:
            delta = rotary_new - rotary_old
            new_alt_feet = new_alt_feet + delta * rotary_multiplier
            rotary_old = rotary_new

        new_alt = new_alt_feet / 3.28084
        new_slp = calc_sea_level_pressure(pressure_hpa, new_alt) - adjust
        update_settings_display(new_alt, new_slp, is_metric)

    with open("last-sea-level-pressure.txt", "w") as data_file:
        data_file.write(f"{new_slp}")

    return new_slp


def update_settings_display(alt, press):
    """
    Update settings
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=0)

    convert, unit = metric_format(is_metric)

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




def display_altimeter_details(buzz, altitude_m, pressure_hpa, temp_c, humidity, iaq, is_metric):

    epd_draw.rectangle((0, 0, 250, 122), fill=255)
    epd_draw.text((3, 5), "Altimeter Details", font=font_small, fill=0)
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


def display_big_dashboard(buzz, altitude_m, pressure_hpa, iaq, is_metric):
    """
    Display main dashboard
    :param buzz:
    :return:
    """
    epd_draw.rectangle((0, 0, 250, 122), fill=255)

    epd_draw.text((1, 5), "Altimeter & GPS", font=font_small, fill=0)

    convert, unit = metric_format(is_metric)
    alt_string = f"{altitude_m * convert:.0f}"
    alt_num_width = font_big.getlength(alt_string)
    alt_metric_string = f"{unit}"
    press_string = f"{pressure_hpa:.2f}"
    press_num_width = font_big.getlength(press_string)
    press_metric_string = f"hpa"

    epd_draw.text((0, 35), f"Altitude", font=font_small, fill=0)
    epd_draw.text((74, 30), alt_string, font=font_big, fill=0)

    if is_metric:
        epd_draw.text((74 + alt_num_width, 30 + 9), alt_metric_string, font=font_medium, fill=0)
    else:
        epd_draw.text((74 + alt_num_width, 30), "'", font=font_big, fill=0)

    epd_draw.text((0, 70), f"Pressure", font=font_small, fill=0)
    epd_draw.text((74, 65), press_string, font=font_big, fill=0)
    epd_draw.text((74 + press_num_width + 3, 65 + 9), press_metric_string, font=font_medium, fill=0)

    # Flash IAQ warning (black banner with white text in the top right)
    if iaq and iaq > 150.0:
        epd_draw.rectangle((180, 2, 240, 20), fill=0)
        epd_draw.text((192, 4), "IAQ!", font=font_small, fill=255)

    refresh_eink_display(epd_disp, epd_draw, epd_image, partial=True)





def main():
    global SLP_CALIBRATION_BMP585, SLP_CALIBRATION_BME680, i2c1, sea_level_pressure, slp_hpa_bmp585, slp_hpa_bme680
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

    altitude_reference_splash(is_metric)

    # main loop variables
    last_eink_update = time.ticks_ms()
    UPDATE_INTERVAL_MS = 5000  # limit Eink refresh to once every 5 seconds

    # Store previous values to detect actual changes
    prev_alt = None
    prev_press = None

    # main loop
    print("start of main loop\n")
    first_run = True
    time_since_last_temp_update = ticks_ms()

    while True:
        dwell = DWELL_MS_LOOP
        loop_time = ticks_ms()
        elapsed_time = ticks_diff(ticks_ms(), time_since_last_temp_update)
        if DEBUG: print(f"Time since last temp ={elapsed_time}")

        if button1():
            is_metric = not is_metric

        if button2():
            sea_level_pressure = adjust_altitude_slp(
                buzz=True,
                bmp_update=not error_bmp585,
                is_metric=is_metric,
                altitude_m=altitude_m,
                pressure_hpa=pressure_hpa,
                slp_hpa_bme680=slp_hpa_bme680,
                slp_hpa_bmp585=slp_hpa_bmp585,
                cal_bme680=SLP_CALIBRATION_BME680,
                cal_bmp585=SLP_CALIBRATION_BMP585
            )
            # Recalculate local variables based on the new returned value
            slp_hpa_bmp585 = sea_level_pressure + SLP_CALIBRATION_BMP585
            slp_hpa_bme680 = sea_level_pressure + SLP_CALIBRATION_BME680

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
                    bme, slp_hpa_bme680, debug=DEBUG)

            first_run = False

            if error_bmp585:
                print(f"No high-precision Altitude bmp585 sensor\n")
            else:
                temp_c_bmp585, hpa_bmp585, alt_m_bmp585, error_bmp585 = bmp585_sensor(bmp, slp_hpa_bmp585, debug=DEBUG)

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

        # Check if we should refresh Eink
        now = time.ticks_ms()
        time_since_refresh = time.ticks_diff(now, last_eink_update)

        # todo: is this correct? Determine if values changed significantly
        values_changed = False
        if prev_alt is None or abs(altitude_m - prev_alt) > 0.05 or abs(pressure_hpa - prev_press) > 0.02:
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
                display_altimeter_details(buzzer_sound, altitude_m, pressure_hpa, temp_c, humidity, iaq, is_metric)

            else:
                display_big_dashboard(buzzer_sound, altitude_m, pressure_hpa, iaq, is_metric)




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