# metric_imperial_utils.py

def feet_to_meters(feet):
    return feet / 3.28084


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
        convert = 3.28084
    return convert, unit


def altitude_to_string(altitude_m, digits, is_metric):
    if is_metric:
        unit = " m"
        convert = 1.0
    else:
        unit = "'"
        convert = 3.28084
    altitude_string = f"{altitude_m * convert:.{digits}f}{unit}"
    return altitude_string
