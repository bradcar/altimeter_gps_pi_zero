# Raspberry Pi Zero 2 W: Altimeter = Elevation & sea level pressure adjust - Nov 2024
#
# Sensors used
#    - BMP585 highly accurate pressure & altitude
#    - rotary encoder to adjust alt & pressure
#      use sea level pressure at nearest airport
#    - ssd1309 SDI 128x64 OLED Display (SW is ssd1306) -> Replaced by 2.13" E-ink
#    - in/cm F/C changed with button #1
#    - buttons debounced with efficient rp2 interrupts -- nice! -> Adapted for Linux GPIO
#
# Use nearest airport for sea level pressure
#    Portland updated hourly (7 min before the hour)
#        https://www.weather.gov/wrh/timeseries?site=KPDX
#
#    my home office is
#        365.0 feet elevation, 111.25m
#    my dining room table
#        355 feet elevation (-10')
#    my garage is at <todo> feet elevation
#        339 feet elevation (-26')
#
# Key links
#     https://micropython.org/download/RPI_PICO2/ for latest .uf2 preview
#     https://docs.micropython.org/en/latest/esp8266/tutorial/ssd1306.html
#
# pycharm stubs
#    https://micropython-stubs.readthedocs.io/en/main/packages.html#mp-packages
#
# TODOs
#  * test error code of bmp with disconnected
#  * create known altitudes display
#
# Adapted from MicroPython code by bradcar

import time

import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
from adafruit_epd.ssd1680 import Adafruit_SSD1680
from gpiozero import Button

# Import your custom repository driver and the Linux bridge layer
from micropython_bmpxxx import bmpxxx
from src.vendor.bmpxxx_linux import LinuxI2CBridge

# Rotary encoder setup for Linux architecture
from gpiozero import RotaryEncoder

# for Monochrome E-ink 0 is black and 255 is white
FILL_WHITE = 255

# Native Hardware Configuration Mappings for 2.13" E-ink (Portrait State)
EPD_WIDTH = 122
EPD_HEIGHT = 250

# Virtual dimensions for Landscape mapping
VIRTUAL_WIDTH = 250
VIRTUAL_HEIGHT = 122

# === PINS ===
# Pi Zero GPIO Layout replacements using gpiozero Button structures
# Button 1: cm/in toggle (GPIO 6)
#           E-ink: "Up" Button: actually GPIO 6 NOT GPIO 5
# Button 2: Adjust altitude/SLP (GPIO 5)
#           E-ink: "Down" Button: actually GPIO 5 NOT GPIO 6
# Button 3: Detail/Summary layout toggle (GPIO 15)
button_1 = Button(6, pull_up=True, bounce_time=0.1)
button_2 = Button(5, pull_up=True, bounce_time=0.1)
button_3 = Button(13, pull_up=True, bounce_time=0.1)

# TODO Rotary gpio16 CLK, gpio20 DT, gpio21 for button
rotary = RotaryEncoder(16, 20, wrap=False)  # GPIO 6 (CLK), GPIO 7 (DT)
rotary_switch = Button(21, pull_up=True, bounce_time=0.1)

# TODO Buzzer pin 26
buzzer = digitalio.DigitalInOut(board.D26)
buzzer.direction = digitalio.Direction.OUTPUT

error_bmp585 = False

# ========================= globals & constants =========================
DWELL_MS_LOOP = 300
OVER_TEMP_WARNING = 70.0

show_env_details = False
set_known = False
buzzer_sound = True
metric = False
debug = True

button_1_pushed = False
button_2_pushed = False
button_3_pushed = False

debounce_1_time = 0
debounce_2_time = 0
debounce_3_time = 0

INIT_SEA_LEVEL_PRESSURE = 1010.70
SLP_CALIBRATION_BMP585 = -0.1931

warning_toggle = 0
rotary_multiplier = 1


# Buttons & Display setup
def cb_button_1():
    global button_1_pushed
    button_1_pushed = True
    print("Button 1 pushed")


def cb_button_2():
    global button_2_pushed
    button_2_pushed = True
    print("Button 2 pushed")


def cb_button_3():
    global button_3_pushed
    button_3_pushed = True


button_1.when_pressed = cb_button_1
button_2.when_pressed = cb_button_2
button_3.when_pressed = cb_button_3


def init_e_ink_display():
    """Initializes the E-ink display using SPI and creates the canvas."""
    spi = busio.SPI(board.SCK, board.MOSI)

    ecs = digitalio.DigitalInOut(board.CE0)  # Chip Select
    dc = digitalio.DigitalInOut(board.D22)  # Data/Command Control
    rst = digitalio.DigitalInOut(board.D27)  # Hardware Reset
    busy = digitalio.DigitalInOut(board.D17)  # Hardware Busy Line

    display = Adafruit_SSD1680(
        width=EPD_WIDTH,
        height=EPD_HEIGHT,
        spi=spi,
        cs_pin=ecs,
        dc_pin=dc,
        sramcs_pin=None,
        rst_pin=rst,
        busy_pin=busy
    )
    display.rotation = 0
    display.fill(0)
    display.display()

    image = Image.new("L", (VIRTUAL_WIDTH, VIRTUAL_HEIGHT))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=16)
    except IOError:
        font = ImageFont.load_default()
    return display, draw, font, image


# Functions =================================================

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


def pico_temperature():
    """
    Reads Linux system temperature as substitute for Pico ADC(4)
    """
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            celsius = float(f.read()) / 1000.0
        if debug: print(f"Pi Zero chip temp = {celsius:.3f}C")
        return celsius
    except Exception:
        return 25.0


def bmp585_sensor(sea_level_pressure):
    debug = True
    try:
        # Sync current loop value down to your driver profile state properties
        bmp.sea_level_pressure = sea_level_pressure

        celsius = bmp.temperature
        hpa_pressure = bmp.pressure
        meters = bmp.altitude

        if debug:
            print(f"BMP585 Temp °C = {celsius:.2f} C")
            print(f"BMP585 Pressure = {hpa_pressure:.2f} hPA")
            print(f"BMP585 Alt = {meters * 3.28084:.2f} feet\n")

    except Exception as e:
        print("BMP585: Failed to read sensor.")
        return None, None, None, "ERROR_BMP585:" + str(e)

    return celsius, hpa_pressure, meters, None


def display_details(draw, font, temp_c, temp_f, altitude_m, pressure_hpa):
    """display all measurement details in a standard font to the E-ink canvas"""
    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)  # Clear

    if metric:
        draw.text((10, 5), f"Alt = {altitude_m:.1f}m", font=font, fill=FILL_WHITE)
        draw.text((10, 25), f"Temp = {temp_c:.1f}C", font=font, fill=FILL_WHITE)
        draw.text((10, 45), f"Bar  ={pressure_hpa:.1f} hpa", font=font, fill=FILL_WHITE)
    else:
        draw.text((10, 5), f"Alt = {altitude_m * 3.28084:.0f}\'", font=font, fill=FILL_WHITE)
        draw.text((10, 25), f"Temp = {temp_f:.1f}F", font=font, fill=FILL_WHITE)
        draw.text((10, 45), f"Bar  = {pressure_hpa * 0.02953:.2f}\"", font=font, fill=FILL_WHITE)

    draw.text((10, 65), f"Hum  = no sensor", font=font, fill=FILL_WHITE)
    draw.text((10, 85), f"IAQ  = no sensor", font=font, fill=FILL_WHITE)


def display_big_num(draw, font, altitude_m, pressure_hpa):
    """display just alt & hpa readings to the E-ink canvas"""
    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)  # Clear
    draw.text((10, 5), "Altimeter", font=font, fill=FILL_WHITE)

    if metric:
        unit = " m"
        convert = 1.0
    else:
        unit = "\'"
        convert = 3.28084

    draw.text((10, 35), f"Alt: {(altitude_m * convert):.0f}{unit}", font=font, fill=FILL_WHITE)
    draw.text((10, 70), f"hPA: {pressure_hpa:.1f}", font=font, fill=FILL_WHITE)


def update_settings_display(draw, font, alt, press):
    """Invert layout style or provide feedback text mapping during adjustment routines"""
    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=FILL_WHITE)  # White back for "inverted"
    draw.text((10, 5), "Setting Alt...", font=font, fill=0)

    if metric:
        unit = " m"
        convert = 1.0
    else:
        unit = "\'"
        convert = 3.28084

    draw.text((10, 35), f"new Alt: {(alt * convert):.0f}{unit}", font=font, fill=0)
    draw.text((10, 70), f"Sea hPA: {press:.1f}", font=font, fill=0)


def adjust_altitude_slp(display, draw, font, image, bmp_update, altitude_m, pressure_hpa):
    global metric, sea_level_pressure, slp_hpa_bmp585, rotary_multiplier

    new_alt = altitude_m
    adjust = SLP_CALIBRATION_BMP585
    new_slp = slp_hpa_bmp585 - adjust

    print(f"Adjustment start: alt= {new_alt} m, {new_alt * 3.28084} ft")

    if buzzer_sound:
        buzzer.value = True
        time.sleep(0.2)
        buzzer.value = False

    update_settings_display(draw, font, altitude_m, new_slp)
    hardware_aligned_image = image.rotate(270, expand=True)
    display.image(hardware_aligned_image)
    display.display()

    # Clear button queue flags
    _ = button2()

    rotary_old = rotary.steps
    while not button2():
        if button1():
            metric = not metric

        new_alt_feet = new_alt * 3.28084
        rotary_new = rotary.steps

        if rotary_switch.is_pressed:
            rotary_multiplier = 1 if rotary_multiplier != 1 else 100
            time.sleep(0.3)  # basic switch wait

        if rotary_old != rotary_new:
            delta = rotary_new - rotary_old
            new_alt_feet = new_alt_feet + delta * rotary_multiplier
            rotary_old = rotary_new

        new_alt = new_alt_feet / 3.28084

        # Use your custom class arithmetic helper for new slp updates
        bmp.sea_level_pressure = sea_level_pressure
        new_slp = bmp.calc_sea_level_pressure(pressure_hpa, new_alt) - adjust

        update_settings_display(draw, font, new_alt, new_slp)
        hardware_aligned_image = image.rotate(270, expand=True)
        display.image(hardware_aligned_image)
        try:
            display.display(partial_refresh=True)
        except TypeError:
            display.display()

    if buzzer_sound:
        buzzer.value = True
        time.sleep(0.2)
        buzzer.value = False

    sea_level_pressure = new_slp
    print(f"Adjustment end:   alt= {new_alt} m, {new_alt * 3.28084} ft")

    with open("last-sea-level-pressure.txt", "w") as data_file:
        data_file.write(f"{new_slp}")

    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)
    hardware_aligned_image = image.rotate(270, expand=True)
    display.image(hardware_aligned_image)
    display.display()
    return sea_level_pressure


def main():
    global metric, show_env_details, sea_level_pressure, slp_hpa_bmp585, error_bmp585, bmp

    print("Starting Pi Zero 2 W Altitude Tracking...\n")

    # Initialize the hardware interface bridge targeting Linux /dev/i2c-1
    linux_i2c = LinuxI2CBridge(bus_number=1)

    # scan using that single bridge instance
    discovered = linux_i2c.scan()
    print(f"Scanning I2C Bus: Found devices at addresses: {[hex(a) for a in discovered]}")

    try:
        print("creating BMP585")
        bmp = bmpxxx.BMP585(linux_i2c)

        # Configure resolution parameters according to your GitHub instructions

        print("Setting bmp.pressure_oversample_rate")
        bmp.pressure_oversample_rate = bmp.OSR128
        print("Setting bmp.temperature_oversample_rate")
        bmp.temperature_oversample_rate = bmp.OSR8
        bmp.iir_coefficient = bmp.COEF_7

    except Exception as e:
        print(f"BMP585 custom configuration exception: {e}")
        error_bmp585 = True


    # set up SPI and the display after I2C
    print("initializing the SPI E-ink display")
    display, draw, font, image = init_e_ink_display()

    draw.text((10, 5), "Starting", font=font, fill=FILL_WHITE)
    draw.text((10, 25), "altimeter...", font=font, fill=FILL_WHITE)
    hardware_aligned_image = image.rotate(270, expand=True)
    display.image(hardware_aligned_image)
    display.display()

    try:
        with open("last-sea-level-pressure.txt", "r") as data_file:
            sea_level_pressure = float(data_file.read())
        print(f"Using previous sea level pressure = {sea_level_pressure}")
    except Exception:
        sea_level_pressure = INIT_SEA_LEVEL_PRESSURE
        print(f"Using program sea level pressure in constant ={sea_level_pressure}")

    slp_hpa_bmp585 = sea_level_pressure + SLP_CALIBRATION_BMP585

    if buzzer_sound:
        buzzer.value = True
        time.sleep(0.2)
        buzzer.value = False

    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)
    draw.text((2, 1), "Oregon Altitudes", font=font, fill=FILL_WHITE)
    draw.text((12, 20), "My Garage: 339'", font=font, fill=FILL_WHITE)
    draw.text((12, 35), "Sylvan Hill: 761'", font=font, fill=FILL_WHITE)
    draw.text((12, 50), "Benchmark: 6207'", font=font, fill=FILL_WHITE)

    draw.text((12, 70), "Meadows Main: 5003'", font=font, fill=FILL_WHITE)
    draw.text((12, 85), "Meadows HRM: 4540'", font=font, fill=FILL_WHITE)
    draw.text((12, 100), "Bachelor Main: 6207'", font=font, fill=FILL_WHITE)

    hardware_aligned_image = image.rotate(270, expand=True)
    display.image(hardware_aligned_image)
    display.display()
    time.sleep(5)

    print("start of main loop\n")
    first_run = True
    time_since_last_temp_update = time.time()

    temp_c, pressure_hpa, altitude_m, temp_f = 20.0, 1013.25, 111.0, 68.0

    try:
        while True:
            loop_start_time = time.time()
            elapsed_time = loop_start_time - time_since_last_temp_update

            if button1():
                metric = not metric

            if button2():
                sea_level_pressure = adjust_altitude_slp(display, draw, font, image, not error_bmp585, altitude_m,
                                                         pressure_hpa)
                print(f"Adjusted sea level pressure = {sea_level_pressure:.2f} hpa")
                slp_hpa_bmp585 = sea_level_pressure + SLP_CALIBRATION_BMP585

            if button3():
                show_env_details = not show_env_details

            if first_run or elapsed_time > 2.0:
                time_since_last_temp_update = time.time()
                temp = pico_temperature()
                if temp > OVER_TEMP_WARNING:
                    print(f"WARNING: Pi Pico Hi Temp = {temp:.1f}°C")

                slp_hpa_bmp585 = sea_level_pressure + SLP_CALIBRATION_BMP585

                if not error_bmp585:
                    temp_c_bmp585, hpa_bmp585, alt_m_bmp585, error_bmp585 = bmp585_sensor(slp_hpa_bmp585)

                if error_bmp585:
                    draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)
                    draw.text((10, 10), "Error: No Alt Sensor", font=font, fill=FILL_WHITE)
                    draw.text((10, 40), "BMP585 broken", font=font, fill=FILL_WHITE)
                    hardware_aligned_image = image.rotate(270, expand=True)
                    display.image(hardware_aligned_image)
                    display.display()
                    break

                if not error_bmp585:
                    temp_c = temp_c_bmp585
                    altitude_m = alt_m_bmp585
                    pressure_hpa = hpa_bmp585
                temp_f = (temp_c * 9.0 / 5.0) + 32.0
                first_run = False

            # --- Render current view matrix ---
            if show_env_details:
                display_details(draw, font, temp_c, temp_f, altitude_m, pressure_hpa)
            else:
                display_big_num(draw, font, altitude_m, pressure_hpa)

            hardware_aligned_image = image.rotate(270, expand=True)
            display.image(hardware_aligned_image)

            try:
                display.display(partial_refresh=True)
            except TypeError:
                display.display()

            execution_duration = time.time() - loop_start_time
            sleep_target = (DWELL_MS_LOOP / 1000.0) - execution_duration
            if sleep_target > 0:
                time.sleep(sleep_target)

    except KeyboardInterrupt:
        draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)
        hardware_aligned_image = image.rotate(270, expand=True)
        display.image(hardware_aligned_image)
        display.display()
        print("\nExit: ctrl-c")


if __name__ == "__main__":
    main()