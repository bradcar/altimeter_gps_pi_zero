# bmp585_bme680_calibration.py
"""
Calibration of bmp585 & bme680 sensor - temp, humidity, pressure, IAQ, altitude

Calibration:
    https://community.bosch-sensortec.com/mems-sensors-forum-jrmujtaw/post/calibration-of-bmp280-bmp390-ByUrslPUgVrkMHA

Benchmark location in Portland
    Airport
        https://www.portlandmaps.com/detail/benchmarks/10003-10201-NE-AIRPORT-WAY/R317068_did/
    Sylvan Hill
        https://www.portlandmaps.com/detail/benchmarks/-13662910.76695894_5701969.972378978_xy/

Portland - PDX airport sea level pressure updated every hour
    https://www.weather.gov/wrh/timeseries?site=KPDX
    * Elevation Elev: 20.0 ft
    * Lat/Lon: 45.59578N 122.60917W
    Benchmarks:
    * https://www.portlandmaps.com/detail/benchmarks/-13648790.370985914_5715807.620158344_xy/
    * BM #4052 27.251'


bme680 driver code:
   https://github.com/robert-hh/BME680-Micropython

my home office is ~361 feet elevation, first bme680 says 303.5 feet (+57.5' correction needed)
my garage is at <todo> feet elevation

TODO: debug why nearly perfect 1.0HPA diff between sensors
BMP585 Pressure = 1004.3317188 hPa, 28.0820312°C
BME680 Pressure = 1005.4100000 hPa, 33.8528516°C
BME680 FP Pressure = 1005.3974894 hPa, temp Diff = 5.7708203°C diff

Diff = 1.0782812 diff in hpa

INT vs. FP implementation Diff = 0.0125106 diff in hpa


"""

import time
from math import log

from bme680 import BME680_I2C
from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_utils import pico_temperature, scan_i2c_bus
from pi_zero_i2c_bridge_utils import PiZeroI2CBridge

DEBUG = True


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
    iaq = (9.4751 * ln_iaq ** 2 - 316.31 * ln_iaq + 2524.0) + 6 * humidity_score
    return max(0, min(500.0, iaq))


def bme_temp_humid_hpa_iaq_alt(bme, sea_level):
    """
    read temp, humidity, pressure, Indoor Air Quality (IAQ) from the BME680 sensor
    measurement takes ~189ms
     IAQ:     0- 50 good
             51-100 average
            101-150 poor
            151-200 bad
            201-300 worse
            301-500 very bad
    todo: add code to not trust IAQ until 300 cycles or about 30mins.
          https://github.com/thstielow/raspi-bme680-iaq

    :param :sea_level: sea level hpa from closest airport
    :returns: temp_c, percent_humidity, hpa_pressure, iaq, meters, error string
    """

    try:
        hpa_pressure = bme.pressure
        temp_c = bme.temperature
        percent_humidity = bme.humidity
        gas_ohms = bme.gas  # Updated to match the Ohms divisor in your blueprint

        # derived sensor data
        meters = 44330.0 * (1.0 - (hpa_pressure / sea_level) ** (1.0 / 5.255))
        iaq = calculate_iaq(gas_ohms, percent_humidity)

        if DEBUG:
            print(f"BME680 Pressure = {hpa_pressure:.2f} hPa")
            print(f"BME680 Temp °C = {temp_c:.1f}° C")
            print(f"BME680 Humidity = {percent_humidity:.1f}%")
            print(f"BME680 Gas resistance = {gas_resist:.2f} Ohms")
            print(f"BME680 iaq = {iaq:.2f},  IAQ lower better [0 to 500]")
            print(f"BME680 Alt = {meters * 3.28084:.2f} feet \n")

    except OSError as e:
        print("BME680: Failed to read sensor.")
        return None, None, None, None, None, "ERROR_BME680:" + str(e)

    return temp_c, percent_humidity, hpa_pressure, iaq, meters, None


# -------------------------------------------------------------------------
def main():
    i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    scan_i2c_bus(i2c1)

    try:
        pi_celsius = pico_temperature() or 0.0
        print(f"Pi Celsius = {pi_celsius:.1f}° C\n")

        bme = BME680_I2C(i2c=i2c1, address=0x77)
        bmp = bmpxxx.BMP585(i2c=i2c1, address=0x47)

        # Configure OverSampling and IIR filter settings
        bmp.pressure_oversample_rate = bmp.OSR4
        bmp.temperature_oversample_rate = bmp.OSR4
        bmp.iir_coefficient = bmp.COEF_1

        bme_hpa= bme.pressure
        bmp_hpa = bmp.pressure

        print(f"BMP585 Pressure = {bmp_hpa:.7f} hPa")
        print(f"BME680 Pressure = {bme_hpa:.7f} hPa")
        diff = bme_hpa - bmp_hpa
        print(f"Diff = {diff:.7f} diff in hpa")

        print(f"\nBME Altitude set to = {bme.altitude:.2f} meters")
        print(f"BMP Altitude set to = {bmp.altitude:.2f} meters\n")


        max_diff = diff
        min_diff = diff
        num = 25
        print(f"Test {num} Iterations ")
        for _ in range(25):
            bme_hpa = bme.pressure
            bmp_hpa = bmp.pressure
            diff = bme_hpa - bmp_hpa
            max_diff = max(max_diff, diff)
            min_diff = min(min_diff, diff)
            print(f"Diff = {diff:.7f} diff in hpa")
            time.sleep(0.1)

        print(f"\nMAX Diff = {max_diff:.7f} Maximum diff in hpa")
        print(f"MIN Diff = {min_diff:.7f} Minimum diff in hpa")

        slp_bme_hpa = bme.sea_level_pressure
        slp_bmp_hpa = bmp.sea_level_pressure
        print(f"\nSLP BMP585 Pressure = {slp_bmp_hpa:.7f} hPa")
        print(f"SLP BME680 Pressure = {slp_bme_hpa:.7f} hPa")

        # Set to known altitude
        hundred_meters = 100.00
        print(f"\nSet to know altitude of {hundred_meters}m")

        bme.altitude =  hundred_meters
        print(f"\nBME Altitude set to = {bme.altitude:.2f} meters")
        bmp.altitude =  hundred_meters
        print(f"BMP Altitude set to = {bmp.altitude:.2f} meters")

        slp_bme_hpa = bme.sea_level_pressure
        slp_bmp_hpa = bmp.sea_level_pressure
        print(f"\nAdjusted SLP BMP585 Pressure = {slp_bmp_hpa:.7f} hPa")
        print(f"Adjusted SLP BME680 Pressure = {slp_bme_hpa:.7f} hPa")
        print(f"Adjusted Diff = {slp_bme_hpa - slp_bmp_hpa:.7f} diff in hpa\n")

        bme_hpa = bme.pressure
        bme_fp_hpa = bme.pressure_fp
        bmp_hpa = bmp.pressure
        bme_temp = bme.temperature
        bmp_temp = bmp.temperature
        print(f"\nBMP585 Pressure = {bmp_hpa:.7f} hPa, {bmp_temp:.7f}°C")
        print(f"BME680 Pressure = {bme_hpa:.7f} hPa, {bme_temp:.7f}°C")
        print(f"BME680 FP Pressure = {bme_fp_hpa:.7f} hPa, temp Diff = {bme_temp- bmp_temp:.7f}°C diff \n")

        print(f"Diff = {bme_hpa - bmp_hpa:.7f} diff in hpa\n")
        print(f"INT vs. FP implementation Diff = {bme_hpa - bme_fp_hpa:.7f} diff in hpa\n")



        print("\n====================Start test Loop")
        while True:
            bme_hpa = bme.pressure
            bmp_hpa = bmp.pressure
            bme_temp = bme.temperature
            bmp_temp = bmp.temperature
            print(f"\nBMP585 Pressure = {bmp_hpa:.7f} hPa, {bmp_temp:.1f}°C")
            print(f"BME680 Pressure = {bme_hpa:.7f} hPa, {bme_temp:.1f}°C")

            percent_humidity = bme.humidity
            gas_ohms = bme.gas
            iaq = calculate_iaq(gas_ohms, percent_humidity)
            print (f"iaq = {iaq:.1f}, humidity = {percent_humidity:.1f}%")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nExit on User Interrupt...")
    finally:
        i2c1.close()


if __name__ == "__main__":
    main()
