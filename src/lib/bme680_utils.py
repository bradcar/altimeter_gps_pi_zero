#!/usr/bin/env python3
"""
bme680_utils.py

Indoor Air Quality (IAQ) calculation and qualitative assessment module for BME680 gas sensors.

Module Highlights:
    * Brad's Mathematical estimation of IAQ index combining logarithmic gas resistance measurements
      with humidity offset penalty calculations.
    * Standardization of numerical IAQ scores (0-500 scale) into descriptive quality categories.

Methods:
    * calculate_iaq: Calculates Indoor Air Quality (IAQ) score using raw gas sensor resistance in ohms and relative humidity percentage.
    * iaq_quality_to_string: Maps a numerical IAQ value to a descriptive qualitative string (e.g., 'warmup', 'best', 'poor', 'DANGER').
"""
import logging
from math import log

# Calling script should set up logging level, examples:
#   logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#   logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def iaq_quality_to_string(iaq_value):
    """
    iaq_quality_to_string
    assuming 0 is warmup
    all others by standard nomenclature.
    """
    if iaq_value == 0:
        return "warmup"
    if iaq_value < 50:
        return "best"
    elif iaq_value < 100:
        return "ave"
    elif iaq_value < 150:
        return "poor"
    elif iaq_value < 200:
        return "bad"
    elif iaq_value < 300:
        return "V Bad"
    else:
        return "DANGER"


def calculate_iaq(gas_ohms, percent_humidity):
    """
    IAQ (Indoor Air Quality) calculation:
        IAQ value between 0. and 500., where lower values represent higher air quality.
        https://github.com/thstielow/raspi-bme680-iaq
        IAQ:      0- 50 good
                 51-100 average
                101-150 poor
                151-200 bad
                201-300 worse
                301-500 very bad

    Example values:
        %humidity: 40.0, gas: 400000.0, IAQ=20.40845415066724
        %humidity: 40.0, gas: 200000.0, IAQ=74.77534464321434
        %humidity: 40.0, gas: 100000.0, IAQ=138.24691584011362
        %humidity: 40.0, gas: 50000.0, IAQ=210.82316774136598
        %humidity: 40.0, gas: 20000.0, IAQ=320.7368077020483
        %humidity: 40.0, gas: 15000.0, IAQ=358.5275148830442
        %humidity: 40.0, gas: 8000.0, IAQ=446.5608215462562

    Previous very crude IAQ calculation:
          iaq = log(gas_resistance) + 0.04 * percent_humidity

    :param gas_ohms: BME680 typical range of 250,000 ohms (excellent) to 8,000 ohms (bad)
    :param percent_humidity: 0.0 to 100.0 percent of humidity
    :return: iaq in 0 (excellent) to 500 (bad)
    """
    if percent_humidity is None or not (0.0 <= percent_humidity <= 100.0):
        logging.error(f"Error %humidity: {percent_humidity}%. Must be between 0.0 and 100.0")
        return 0.0  # Return 0 Humidity score on sensor fault

    if gas_ohms is None or gas_ohms <= 0:
        logging.error(f"Error: Invalid gas resistance: {gas_ohms} Ohms. value must > 0) for logarithmic calculation.")
        return 500.0  # Return max/hazardous IAQ score on sensor fault

    if 0 <= percent_humidity <= 40:
        humidity_score = 25.0 * ((40 - percent_humidity) / 40) ** 2
    elif 40 < percent_humidity <= 60:
        humidity_score = 0.0
    elif 60 < percent_humidity <= 100:
        humidity_score = 25.0 * ((percent_humidity - 60) / 40) ** 2
    else:
        humidity_score = None

    try:
        ln_iaq = log(gas_ohms)
        iaq = (9.4751 * ln_iaq ** 2 - 316.31 * ln_iaq + 2524.0) + 6 * humidity_score
        return max(0.0, min(500.0, iaq))
    except ValueError as e:
        logger.error(f"IAQ Math calculation (gas_ohms={gas_ohms}): {e}")
        return 500.0
