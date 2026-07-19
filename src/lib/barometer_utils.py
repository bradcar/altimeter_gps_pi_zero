import time
from math import log

from bme680 import BME680_I2C
from bme680_utils import iaq_quality_to_string
from micropython_bmpxxx.bmpxxx import BMP585


def calc_sea_level_pressure(hpa, meters):
    sea_level_pressure = hpa / (1.0 - (meters / 44330.77)) ** (1 / 0.1902632)
    return sea_level_pressure


def calc_altitude(hpa, sea_level_pressure):
    meters = 44330.77 * (1.0 - (hpa / sea_level_pressure) ** 0.1902632)
    return meters


def bmp585_sensor(bmp, sea_level_pressure, debug=False):
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


def bme680_sensor(bme, sea_level_pressure, debug=False):
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


def bme_hpa_correction(bme: BME680_I2C, bmp: BMP585, num_samples=25):
    """
    Calc BME680 hPA adjustment use BMP585 as correct standard, block outliers > 5.0
    """
    valid_diffs = []
    for _ in range(num_samples):
        diff = bme.pressure - bmp.pressure
        if abs(diff) < 5.0:
            valid_diffs.append(diff)
        time.sleep(0.1)

    if not valid_diffs:
        print("Warning: All calibration samples were corrupted. Using 0.85 hpa.")
        return 0.85

    return sum(valid_diffs) / len(valid_diffs)
