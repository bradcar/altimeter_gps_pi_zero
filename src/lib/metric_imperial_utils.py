#!/usr/bin/env python3
"""
metric_imperial_utils.py

Methods:
    feet_to_meters - Converts imperial feet to meters.
    meters_to_feet - Converts meters to imperial feet.
    metric_format - Returns a conversion factor and unit suffix string based on whether metric or imperial.
    altitude_to_string - Formats altitude in meters into a rounded string with the appropriate unit symbol.
"""

def feet_to_meters(feet):
    return feet / 3.28083989501312


def meters_to_feet(meters):
    return meters * 3.28083989501312


def metric_format(is_metric):
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
        convert = 3.28083989501312
    return convert, unit


def altitude_to_string(altitude_m, digits, is_metric):
    if is_metric:
        unit = " m"
        convert = 1.0
    else:
        unit = "'"
        convert = 3.28083989501312
    altitude_string = f"{altitude_m * convert:.{digits}f}{unit}"
    return altitude_string
