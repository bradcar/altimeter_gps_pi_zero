# bme680_utils.py
"""

"""
from math import log


def iaq_quality_to_string(iaq_value):
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
