#!/usr/bin/env python3
"""
calibrate_bmp585_known_alt_slp.py

Print-only calibration script to test and verify rotary encoder movement against BMP585.
"""

import sys
import time

from barometer_utils import calc_sea_level_pressure

# Import hardware instances & helpers directly from main_ws
from main_ws import (
    init_i2c_barameter_helper_for_calibration,
    metric_format,
    calc_altitude,
    encoder,  # Reusing initialized RotaryEncoder object
    rotary_switch,  # Reusing initialized Button object
)

MULTIPLIER_SMALL_STEP = 0.1
MULTIPLIER_BIG_STEP = 10.0
IS_METRIC = False
INITIAL_SEA_LEVEL_PRESSURE = 1020.30


def write_slp_file(new_slp):
    """Save Sea Level Pressure (SLP) to file."""
    try:
        with open("last-sea-level-pressure.txt", "w") as data_file:
            data_file.write(f"{new_slp:.2f}")
        print("Successfully saved new SLP to last-sea-level-pressure.txt")
    except Exception as e:
        print(f"Failed to save Sea Level Pressure to file: {e}")


def print_updated_altitude_calibration(alt, press, is_metric):
    """Prints formatted calibration metrics to standard output."""
    convert, unit = metric_format(is_metric)
    alt_val = f"{(alt * convert):.4f} {unit}"
    print(f" -> Adjusted Altitude: {alt_val:>12} | SLP: {press:.3f} hPa")


def precision_adjust_altitude_slp(gps, is_metric, altitude_m, pressure_hpa, sea_level_pressure_hpa):
    new_alt = altitude_m
    new_slp = sea_level_pressure_hpa

    #
    multiplier_small_step = MULTIPLIER_SMALL_STEP
    multiplier_big_step =  MULTIPLIER_BIG_STEP
    rotary_multiplier = multiplier_small_step

    rotary_old = encoder.steps

    if is_metric:
        metric_string = "m"
        print(f"\n* CALIBRATION STARTED - in Meters")
    else:
        metric_string="'"
        print(f"\n* CALIBRATION STARTED - in Feet")


    print("Rotate knob to adjust. Press switch to toggle step size.")
    print(f"Initial State -> Alt: {new_alt:.3f} {metric_string} | SLP: {new_slp:.2f} hPa")
    print(f"Current step size: {rotary_multiplier:.2f} {metric_string}")
    print("Press Ctrl+C to exit.\n")

    try:
        while True:

            # Handle rotary switch toggle switch (small step vs big step)
            if rotary_switch.is_pressed:
                rotary_multiplier = (
                    multiplier_big_step
                    if rotary_multiplier == multiplier_small_step
                    else multiplier_small_step
                )
                print(f"\n>> Step size multiplier changed to: {rotary_multiplier}x")

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
                    new_alt += (delta * rotary_multiplier) / 3.28084

                new_slp = calc_sea_level_pressure(pressure_hpa, new_alt)
                rotary_old = rotary_new

                # Only print when values actually change
                print_updated_altitude_calibration(new_alt, new_slp, is_metric)

            time.sleep(0.02)  # Polling interval

    except KeyboardInterrupt:
        print("\n\nStopping calibration loop...")

    # write_slp_file(new_slp)

    return new_slp, pressure_hpa


def run_calibration():
    print("BMP585 Sensor Calibration to know Altitude & Sea Level Pressure")
    print("===============================================================")
    initial_slp_hpa = INITIAL_SEA_LEVEL_PRESSURE
    is_metric = IS_METRIC

    # Initialize Hardware using helper function
    i2c_bus, bme, bmp = init_i2c_barameter_helper_for_calibration()

    if not bmp:
        print("ERROR: No BMP585 barometer detected on I2C bus. Exiting.")
        sys.exit(1)

    starting_bmp_hpa = bmp.pressure
    starting_bme_hpa = bme.pressure
    current_alt_m = calc_altitude(starting_bmp_hpa, initial_slp_hpa)

    print(f"Current SLP Baseline : {initial_slp_hpa:.3f} hPa")
    print(f"Current Raw Pressure : {starting_bmp_hpa:.3f} hPa")
    print(f"Current Measured Alt : {current_alt_m:.4f} m")
    print(f"Starting BMP585 pressure : {starting_bmp_hpa:.3f} hPa")
    print(f"Starting BME pressure : {starting_bme_hpa:.3f} hPa")

    # Run loop
    final_slp, final_hpa = precision_adjust_altitude_slp(
        gps=None,
        is_metric=is_metric,
        altitude_m=current_alt_m,
        pressure_hpa=starting_bmp_hpa,
        sea_level_pressure_hpa=initial_slp_hpa,
    )

    print("\n==========================================")
    print(f" Calibration Complete")
    print(f" Final New Sea Level Pressure: {final_slp:.2f} hPa")
    print(f" Initial Sea Level Pressure:   {initial_slp_hpa:.3f} hPa")
    print(f" Correction (Init - new): {initial_slp_hpa - final_slp:.4f} hpa")

    print(f"Ending BMP585 pressure : {bmp.pressure:.3f} hPa")
    print(f"Ending BME pressure : {bme.pressure:.3f} hPa")
    print("------------------------------------------\n")
    initial_meters = calc_altitude(final_hpa, initial_slp_hpa)
    final_meters = calc_altitude(final_hpa, final_slp)
    print(f"Alt with initial slp predicts & final hPa: {initial_meters:.4f} m")
    print(f"Alt with FINAL   slp predicts & final hPa: {final_meters:.4f} m")
    print(f"Difference in meters = {initial_meters - final_meters:.4f} m")
    print("==========================================\n")

    return i2c_bus


if __name__ == "__main__":
    i2c_bus = None
    try:
        i2c_bus = run_calibration()
    except KeyboardInterrupt:
        print("\nCaught Ctrl-C. Calibration exit.")
    finally:
        if i2c_bus:
            try:
                i2c_bus.close()
            except Exception as e:
                print(f"Failed to close I2C: {e}")

        print("Releasing GPIO devices (Rotary Encoder).")
        encoder.close()
        rotary_switch.close()
