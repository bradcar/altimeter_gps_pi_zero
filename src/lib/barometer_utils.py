#!/usr/bin/env python3
"""
barometer_utils.py

Module Highlights:
    * uses logging

Methods:
    calc_sea_level_pressure - Calculates sea level pressure (SLP) using local pressure readings and current altitude in meters.
    calc_altitude - Computes altitude in meters from sensor pressure and sea level pressure using the international barometric formula.
    bmp585_sensor - Reads temperature, pressure, and calculates altitude from a BMP585 sensor with optional debug logging and error handling.
    bme680_sensor - Reads temperature, humidity, pressure, gas resistance, calculates IAQ index and altitude from a BME680 sensor instance.
    bme_hpa_correction - Calculates pressure offset between BME680 and reference BMP585 over multiple samples, remove outliers > 2.0 hPa.
"""
import logging
import time

from bme680 import BME680_I2C
from bme680_utils import iaq_quality_to_string, calculate_iaq
from micropython_bmpxxx.bmpxxx import BMP585

# Calling script should setup:
#   logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calc_sea_level_pressure(hpa, meters):
    """
    Calculate sea level pressure from pressure and elevation.
    :param hpa:
    :param meters:
    :return: sea_level_pressure
    """
    sea_level_pressure = hpa / (1.0 - (meters / 44330.77)) ** (1 / 0.1902632)
    return sea_level_pressure


def calc_altitude(hpa, sea_level_pressure):
    """
    Calculate altitude from pressure and sea level pressure.
    :param hpa:
    :param sea_level_pressure:
    :return: altitude in meters
    """
    meters = 44330.77 * (1.0 - (hpa / sea_level_pressure) ** 0.1902632)
    return meters


def bmp585_sensor(bmp, sea_level_pressure):
    try:
        celsius = bmp.temperature
        hpa_pressure = bmp.pressure
        meters = calc_altitude(hpa_pressure, sea_level_pressure)

        logger.debug(f"BMP585 Temp °C = {celsius:.2f} C")
        logger.debug(f"BMP585 Pressure = {hpa_pressure:.2f} hPA")
        logger.debug(f"BMP585 Alt = {meters * 3.28084:.2f} feet\n")
    except OSError as e:
        logger.error("BMP585: Failed to read sensor: {e}")
        return None, None, None, "ERROR_BMP680:" + str(e)
    return celsius, hpa_pressure, meters, None


def bme680_sensor(bme, sea_level_pressure):
    try:
        celsius = bme.temperature
        percent_humidity = bme.humidity
        hpa_pressure = bme.pressure
        iaq_value = calculate_iaq(bme.gas, percent_humidity)
        meters = calc_altitude(hpa_pressure, sea_level_pressure)

        logger.debug(f"BME680 Temp °C = {celsius:.2f} C")
        logger.debug(f"BME680 Humidity = {percent_humidity:.1f} %")
        logger.debug(f"BME680 Pressure = {hpa_pressure:.2f} hPA")
        logger.debug(f"BME680 iaq = {iaq_value:.1f} {iaq_quality_to_string(iaq_value)}")
        logger.debug(f"BME680 Alt = {meters * 3.28084:.2f} feet")
    except OSError as e:
        logger.error(f"BME680: Failed to read sensor: {e}")
        return None, None, None, None, None, "ERROR_BME680:" + str(e)
    return celsius, percent_humidity, hpa_pressure, iaq_value, meters, None


def bme_hpa_correction(bme: BME680_I2C, bmp: BMP585, num_samples=25):
    """
    Calc BME680 hPA adjustment using BMP585 as correct standard, block outliers > 2.0 hPa
    """
    valid_diffs = []
    for _ in range(num_samples):
        try:
            diff = bme.pressure - bmp.pressure
            if abs(diff) < 2.0:
                valid_diffs.append(diff)
        except OSError as e:
            logger.warning(f"Error reading BME680 during calibration: {e}")
        time.sleep(0.1)

    if not valid_diffs:
        logger.warning("All calibration samples rejected as outliers. Using default offset of 0.85 hPa.")
        return 0.85

    offset = sum(valid_diffs) / len(valid_diffs)
    logger.info(f"BME680 pressure correction offset calculated: {offset:.3f} hPa across {len(valid_diffs)} valid samples")
    return offset
