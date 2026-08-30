#!/usr/bin/env python3
"""
calibrate_bmp585_known_alt_slp.py

Print-only calibration script to test and verify rotary encoder movement against BMP585.

Use sea level pressure at nearest airport
    * Portland updated hourly (7 min before the hour)
        https://www.weather.gov/wrh/timeseries?site=KPDX

    Benchmark locations in Portland
    https://gis-pdx.opendata.arcgis.com/datasets/benchmarks/explore?location=45.530100%2C-122.493300%2C11
    Airport
        https://www.portlandmaps.com/detail/benchmarks/10003-10201-NE-AIRPORT-WAY/R317068_did/
        * BM #4027  27.533 feet  ...on airport way
        * BM #4052  27.251 feet   (could not find)
        * BM #4051  40.73 feet  (could not find)
        * BM #4050  39.811 feet (could not find)
        * BM #4053  42.363 feet
        * BM #4053  42.239 feet
        https://www.portlandmaps.com/detail/benchmarks/NE-MARINE-DR/R316860_did/

    Sylvan Hill
        https://www.portlandmaps.com/detail/benchmarks/-13662910.76695894_5701969.972378978_xy/
        * BM #3758  805.436 feet
        * BM #3757  777.465 feet

References:
    https://github.com/bradcar/MicroPython_BMPxxx

"""

import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from barometer_utils import calc_sea_level_pressure
from metric_imperial_utils import meters_to_feet, feet_to_meters

# Import hardware instances & helpers directly from main_ws
from main_ws import (
    init_i2c_barameter_helper_for_calibration,
    metric_format,
    calc_altitude,
    encoder,  # Reusing initialized RotaryEncoder object
    rotary_switch,  # Reusing initialized Button object
)

# Guess at adjustment: the corrections are calculated by what to add to hPa, so that is subtracted here
INITIAL_SEA_LEVEL_PRESSURE = 1018.30 - (-1.12)
INITIAL_SEA_LEVEL_PRESSURE = 1018.30

MULTIPLIER_SMALL_STEP = 0.001
MULTIPLIER_BIG_STEP = 1.0
IS_METRIC = False


def write_slp_file(new_slp):
    """Save Sea Level Pressure (SLP) to file."""
    try:
        with open("last-sea-level-pressure.txt", "w") as data_file:
            data_file.write(f"{new_slp:.2f}")
        print("Successfully saved new SLP to last-sea-level-pressure.txt")
    except Exception as e:
        print(f"Failed to save Sea Level Pressure to file: {e}")


def print_updated_altitude_calibration(altitude_meter, new_slp_pressure, initial_slp, is_metric):
    """Prints formatted calibration metrics to standard output."""
    conversion, unit = metric_format(is_metric)
    alt_val = f"{(altitude_meter * conversion):.4f} {unit}"
    print(
        f" -> Adjusted Altitude: {alt_val:>12} | SLP: {new_slp_pressure:.4f} hPa    --> {initial_slp - new_slp_pressure:.4f} hPa")


def precision_adjust_altitude_slp(gps, is_metric, altitude_m, pressure_hpa, sea_level_pressure_hpa):
    """
    Prints formatted calibration metrics to standard out.

    Returns on  control-C (KeyboardInterrupt).

    """
    print("  Rotate knob to adjust. Press switch to toggle step size.")
    print("  Press Ctrl+C to exit.\n")

    new_alt = altitude_m

    # use initial slp as starting point for new_slp
    initial_slp = sea_level_pressure_hpa
    new_slp = sea_level_pressure_hpa

    #
    multiplier_small_step = MULTIPLIER_SMALL_STEP
    multiplier_big_step = MULTIPLIER_BIG_STEP
    rotary_multiplier = multiplier_small_step

    rotary_old = encoder.steps

    if is_metric:
        display_alt = new_alt
        metric_string = "meter"
    else:
        display_alt = meters_to_feet(new_alt)
        metric_string = "feet"
    print(f"\n* CALIBRATION in {metric_string.upper()} Started.\n")
    print(f"INITIAL State -> Alt: {display_alt:.3f} {metric_string} | SLP: {new_slp:.3f} hPa")
    print(f"Current step size: {rotary_multiplier:.3f} {metric_string}\n")

    try:
        while True:

            # Handle rotary switch toggle switch (small step vs big step)
            if rotary_switch.is_pressed:
                rotary_multiplier = (
                    multiplier_big_step
                    if rotary_multiplier == multiplier_small_step
                    else multiplier_small_step
                )
                if is_metric:
                    metric_string = "meter"
                else:
                    metric_string = "feet"
                print(f"\n>> Step size multiplier changed to: {rotary_multiplier}x {metric_string}")

                # Debounce wait for button release
                while rotary_switch.is_pressed:
                    time.sleep(0.01)

            # Check rotary encoder rotation
            rotary_new = encoder.steps

            if rotary_old != rotary_new:
                delta = rotary_new - rotary_old

                if is_metric:
                    new_alt += delta * rotary_multiplier
                else:
                    new_alt += feet_to_meters(delta * rotary_multiplier)

                new_slp = calc_sea_level_pressure(pressure_hpa, new_alt)
                rotary_old = rotary_new
                print_updated_altitude_calibration(new_alt, new_slp, initial_slp, is_metric)

            time.sleep(0.02)  # Polling interval

    except KeyboardInterrupt:
        print("\n\nStopping calibration loop...")

    # TODO update SLP at file - removed during debugging
    # write_slp_file(new_slp)

    return new_slp, pressure_hpa


# ***** MAIN METHOD ************************************************************
def run_calibration():
    print("\nBMP585 Sensor Calibration to know Altitude & Sea Level Pressure")
    print("===============================================================")

    timestamp = datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()
    print(f"Timestamp: {timestamp}\n")

    initial_slp_hpa = INITIAL_SEA_LEVEL_PRESSURE
    is_metric = IS_METRIC

    # Initialize Barometer using helper function
    i2c_bus, bme, bmp = init_i2c_barameter_helper_for_calibration()

    # set SLP for both barometers
    bmp.sea_level_pressure = initial_slp_hpa
    bme.sea_level_pressure = initial_slp_hpa

    if not bmp:
        print("ERROR: No BMP585 barometer detected on I2C bus. Exiting.")
        sys.exit(1)

    initial_bmp_hpa = bmp.pressure
    initial_bme_hpa = bme.pressure

    print(f"Current SLP Baseline BMP585: {initial_slp_hpa:.4f} hPa\n")

    print(f"Initial BMP585 pressure BMP585: {initial_bmp_hpa:.4f} hPa")
    print(f"Initial BME680 pressure BME680: {initial_bme_hpa:.4f} hPa\n")

    initial_bmp_alt = bmp.altitude
    initial_bme_alt = bme.altitude
    print(f"Initial BMP585 altitude BMP585: {initial_bmp_alt:.4f} meter, {meters_to_feet(initial_bmp_alt):.2f} feet")
    print(f"Initial BME680 altitude BME680: {initial_bme_alt:.4f} meter, {meters_to_feet(initial_bme_alt):.2f} feet\n")

    calc_alt_m = calc_altitude(initial_bmp_hpa, initial_slp_hpa)
    if calc_alt_m != initial_bmp_alt:
        print(f"calc_altitude method != bmp.altitude")
        print(f"calc_altitude={calc_alt_m:.4f} meter, {meters_to_feet(calc_alt_m):.2f} feet\n")

    # Run loop
    final_slp, final_hpa = precision_adjust_altitude_slp(
        gps=None,
        is_metric=is_metric,
        altitude_m=calc_alt_m,
        pressure_hpa=initial_bmp_hpa,
        sea_level_pressure_hpa=initial_slp_hpa,
    )

    # Set new SLP on BMP585
    bmp.sea_level_pressure = final_slp
    print(f"Resetting BMP585 SLP : {final_slp:.4f} hPa\n")

    print("\n==========================================")
    print(f" Calibration Complete")
    print(f" BMP585 START Sea Level Pressure:     {initial_slp_hpa:.4f} hPa")
    print(f" BMP585 Final New Sea Level Pressure: {final_slp:.4f} hPa")
    print(f" BMP585 Correction (Init - new): {initial_slp_hpa - final_slp:.4f} hpa\n")
    print(f" START BMP585 pressure : {initial_bmp_hpa:.4f} hPa")
    print(f" FINAL BMP585 pressure : {bmp.pressure:.4f} hPa, SLP: {bmp.sea_level_pressure:.4f} hPa")
    print(f" START BME680 pressure : {bme.pressure:.4f} hPa, SLP: {bme.sea_level_pressure:.4f} hPa\n")
    print(f" DIFF: BMP585 Correction (Init - new): {initial_slp_hpa - final_slp:.4f} hpa")
    print(f" DIFF: START BMP585 - START BMP680   : {initial_bmp_hpa - initial_bme_hpa:.4f} hpa\n")

    bme_total_offset = (initial_slp_hpa - final_slp) + (initial_bmp_hpa - initial_bme_hpa)
    print(f" DIFF: BMP680 total error   : {bme_total_offset:.4f} hpa\n")

    print("------------------------------------------\n")
    initial_meters = calc_altitude(final_hpa, initial_slp_hpa)
    final_meters = calc_altitude(final_hpa, final_slp)
    print(
        f"Alt with START  SLP predicts & final hPa: {initial_meters:.4f} m, {meters_to_feet(initial_meters):.2f} feet")
    print(f"Alt with FINAL  SLP predicts & final hPa: {final_meters:.4f} m, {meters_to_feet(final_meters):.2f} feet")
    difference_meters = final_meters - initial_meters
    print(f"Difference in meters = {difference_meters:.4f} m, {meters_to_feet(difference_meters):.4f} feet")
    print("==========================================\n")

    print(" -- Example of hPa day swing")
    s1 = 1010.20
    s2 = 1023.10
    m1 = calc_altitude(final_hpa, s1)
    m2 = calc_altitude(final_hpa, s2)
    print(f"    Alt with {s1} hPa slp predicts & final hPa: {m1:.4f} m")
    print(f"    Alt with {s2} hPa slp predicts & final hPa: {m2:.4f} m")

    return i2c_bus


if __name__ == "__main__":
    i2c_bus = None
    try:
        i2c_bus = run_calibration()
    except KeyboardInterrupt:
        print("\nCaught Ctrl-C. Calibration exit.")
    finally:
        print("\nExiting Program.")
        if i2c_bus:
            try:
                i2c_bus.close()
            except Exception as e:
                print(f"Failed to close I2C: {e}")

        print("Releasing GPIO devices (Rotary Encoder).")
        encoder.close()
        rotary_switch.close()
