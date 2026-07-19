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




BME IAQ:      0- 50 good
             51-100 average
            101-150 poor
            151-200 bad
            201-300 worse
            301-500 very bad
Orignal reference:
    https://github.com/thstielow/raspi-bme680-iaq
    I fit my own 2d surface to create an IAQ approximation

TODO: debug BME680 is nearly perfect 1.0 hPa higher than BMP585 sensors
    BME680 hpa_calibration = 1.0181000 hPa
    BMP585 Calibrated Pressure = 1005.9378125 hPa
    BME680 Calibrated Pressure = 1006.9600000 hPa

TODO: bmp680 code has calibration offset, how does this interact with SLP?

TODO: all calibarion offset to BMP585 code
"""

import time
import logging
from math import log

from barometer_utils import bme_hpa_correction
from bme680 import BME680_I2C
from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_utils import pico_temperature, scan_i2c_bus
from lib.bme680_utils import iaq_quality_to_string
from pi_zero_i2c_bridge_utils import PiZeroI2CBridge

DEBUG = False
GAS_INTERVAL_SEC = 30.0


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


# -------------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    scan_i2c_bus(i2c1)

    try:
        pi_celsius = pico_temperature() or 0.0
        print(f"Pi Zero chip Celsius = {pi_celsius:.1f}° C\n")

        try:
            bmp = bmpxxx.BMP585(i2c=i2c1, address=0x47)
            print("BMP585 initialized successfully.")
        except (RuntimeError, OSError) as e:
            raise SystemExit("Exiting script due to missing or non-responsive BMP585.")

        try:
            bme = BME680_I2C(i2c=i2c1, address=0x77)
            logger.info("BME680 initialized successfully.")
        except (RuntimeError, OSError) as e:
            raise SystemExit("Exiting script due to missing or non-responsive BME680.")

        # Configure OverSampling and IIR filter settings
        bmp.pressure_oversample_rate = bmp.OSR4
        bmp.temperature_oversample_rate = bmp.OSR4
        bmp.iir_coefficient = bmp.COEF_1

        bme_hpa = bme.pressure
        bmp_hpa = bmp.pressure

        print(f"BMP585 Pressure = {bmp_hpa:.7f} hPa")
        print(f"BME680 Pressure = {bme_hpa:.7f} hPa")
        diff = bme_hpa - bmp_hpa
        print(f"Diff = {diff:.7f} diff in hpa")

        print(f"\nBME un-calibrated Altitude  = {bme.altitude:.2f} meters")
        print(f"BMP un-calibrated Altitude = {bmp.altitude:.2f} meters\n")

        average_diff = bme_hpa_correction(bme, bmp, 25)
        print(f"AVE Diff = {average_diff:.7f} Average diff in hpa")

        bme.hpa_calibration = average_diff
        if bme.hpa_calibration is not None:
            print(f"BME680 hpa_calibration = {bme.hpa_calibration:.7f} hPa")
        else:
            print(f"ERROR IN BME680 hpa_calibration = None!")

        print(f"BMP585 Calibrated Pressure = {bmp_hpa:.7f} hPa")
        print(f"BME680 Calibrated Pressure = {bme_hpa:.7f} hPa")

        slp_bme_hpa = bme.sea_level_pressure
        slp_bmp_hpa = bmp.sea_level_pressure
        print(f"\nSLP BMP585 Pressure = {slp_bmp_hpa:.7f} hPa")
        print(f"SLP BME680 Pressure = {slp_bme_hpa:.7f} hPa")

        # Set to known altitude
        hundred_meters = 100.00
        print(f"\nSet to {hundred_meters}m altitude")
        bme.altitude = hundred_meters
        print(f"BME Altitude set to = {bme.altitude:.2f} meters")
        bmp.altitude = hundred_meters
        print(f"BMP Altitude set to = {bmp.altitude:.2f} meters")

        slp_bme_hpa = bme.sea_level_pressure
        slp_bmp_hpa = bmp.sea_level_pressure
        print(f"\nAdjusted SLP BMP585 Pressure = {slp_bmp_hpa:.7f} hPa")
        print(f"Adjusted SLP BME680 Pressure = {slp_bme_hpa:.7f} hPa")
        print(f"Adjusted Diff = {slp_bme_hpa - slp_bmp_hpa:.7f} diff in hpa\n")

        bme_hpa = bme.pressure

        bmp_hpa = bmp.pressure
        bme_temp = bme.temperature
        bmp_temp = bmp.temperature
        print(f"\nBMP585 Pressure = {bmp_hpa:.7f} hPa, {bmp_temp:.7f}°C")
        print(f"BME680 Pressure = {bme_hpa:.7f} hPa, {bme_temp:.7f}°C")
        print(f"Diff = {bme_hpa - bmp_hpa:.7f} diff in hpa\n")

        if DEBUG:
            bme_fp_hpa = bme.pressure_fp
            print(f"\nBME680 FP Pressure = {bme_fp_hpa:.7f} hPa, temp Diff = {bme_temp - bmp_temp:.7f}°C diff")
            print(f"INT vs. FP implementation Diff = {bme_hpa - bme_fp_hpa:.7f} diff in hpa\n")

        print("\n====================Start test Loop")

        last_gas_time = 0.0  # Set to 0 to force a baseline burn immediately on boot
        while True:
            current_time = time.monotonic()

            # Get BMP metrics
            bmp_hpa = bmp.pressure
            bmp_temp = bmp.temperature

            # Get BME metrics, Perform gas readings every 60 seconds, since measurement raises temp
            if (current_time - last_gas_time) >= GAS_INTERVAL_SEC:
                last_gas_time = current_time
                print(f"\nBME680 Gas measurement (every {GAS_INTERVAL_SEC:.0f}s)")
                gas_ohms = bme.gas
                percent_humidity = bme.humidity
                iaq = calculate_iaq(gas_ohms, percent_humidity)
                print(f"IAQ = {iaq:.1f} ({iaq_quality_to_string(iaq)}), {gas_ohms / 1000.0} Kohms")
            else:
                percent_humidity = bme.humidity  # Trigger one non-gas measurement, caches other BME metrics
            bme_hpa = bme.pressure
            bme_temp = bme.temperature

            print(f"\nBMP585 Pressure = {bmp_hpa:.7f} hPa, {bmp_temp:.1f}°C")
            print(f"BME680 Pressure = {bme_hpa:.7f} hPa, {bme_temp:.1f}°C [{bme_hpa - bmp_hpa:.4f} hPa diff]")
            print(f"BME Altitude = {bme.altitude:.3f} meters")
            print(f"BMP Altitude = {bmp.altitude:.3f} meters")
            print(f"BME Humidity = {percent_humidity:.1f}%")

            time.sleep(5.0)

    except KeyboardInterrupt:
        print("\nExit on User Interrupt...")
    finally:
        i2c1.close()


if __name__ == "__main__":
    main()
