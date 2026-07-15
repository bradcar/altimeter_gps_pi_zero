# bme680 sensor - temp, humidity, pressure, IAQ, altitude
#
# bme680 driver code:
#    https://github.com/robert-hh/BME680-Micropython
#
# IAQ (Indoor Air Quality) calculation:
#    IAQ value between 0 and 500, where lower values represent higher air quality.
#    https://github.com/thstielow/raspi-bme680-iaq
#      IAQ:     0- 50 good
#              51-100 average
#             101-150 poor
#             151-200 bad
#             201-300 worse
#             301-500 very bad
#
# Portland - PDX airport sea level pressure updated every hour
#     https://www.weather.gov/wrh/timeseries?site=KPDX
#
# my home office is ~361 feet elevation, first bme680 says 303.5 feet (+57.5' correction needed)
# my garage is at <todo> feet elevation
#
# by bradcar

import time
from math import log

from bme680 import BME680_I2C
from lib.pi_zero_utils import pico_temperature, scan_i2c_bus
from pi_zero_i2c_bridge import PiZeroI2CBridge


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
    debug = True
    try:
        temp_c = bme.temperature
        percent_humidity = bme.humidity
        hpa_pressure = bme.pressure
        gas_resist = bme.gas / 1000  # Updated to match the KOhms divisor in your blueprint

        # derived sensor data
        meters = 44330.0 * (1.0 - (hpa_pressure / sea_level) ** (1.0 / 5.255))
        iaq = log(gas_resist) + 0.04 * percent_humidity

        if debug:
            print(f"BME680 Temp °C = {temp_c:.1f}° C")
            print(f"BME680 Humidity = {percent_humidity:.1f}%")
            print(f"BME680 Pressure = {hpa_pressure:.2f} hPa")
            print(f"BME680 Gas resistance = {gas_resist:.2f} KOhms")
            print(f"BME680 iaq = {iaq:.2f},  IAQ lower better [0 to 500]")
            print(f"BME680 Alt = {meters * 3.28084:.2f} feet \n")

    except OSError as e:
        print("BME680: Failed to read sensor.")
        return None, None, None, None, None, "ERROR_BME680:" + str(e)

    return temp_c, percent_humidity, hpa_pressure, iaq, meters, None


# -------------------------------------------------------------------------
def main():
    # Initialize the Pi Zero I2C bus bridge
    i2c_bridge = PiZeroI2CBridge("/dev/i2c-1")

    #Scan i2c devices
    scan_i2c_bus(i2c_bridge)

    try:
        pi_celsius = pico_temperature() or 0.0
        print(f"Pi Celsius = {pi_celsius:.1f}° C\n")

        print("Initializing I2C Bridge...")
        # Initialize the driver using hardware bridge compatibility layer
        # Note: BME680 default I2C address is usually 0x76 or 0x77
        bme = BME680_I2C(i2c=i2c_bridge, address=0x77)
        print("Done initializing I2C Bridge\n")

        scan_i2c_bus(i2c_bridge)

        # Baseline settings
        sea_level_pressure_hpa = 1012.90
        print(f"Initial sea_level_pressure = {sea_level_pressure_hpa:.2f} hPa")

        # Set to known Altitude
        home_office_alt_meters = 110.03  # ~361 feet elevation in meters
        bme.altitude = home_office_alt_meters
        print(f"Altitude set to = {bme.altitude:.2f} meters")

        # Retrieve the dynamically adjusted sea level pressure from the driver
        sea_level_pressure_hpa = bme.sea_level_pressure
        print(f"Adjusted SLP based on known altitude = {sea_level_pressure_hpa:.2f}")

        print("\nStart test Loop")

        # State tracking variables
        last_ts_ns = time.perf_counter_ns()
        last_pressure = bme.pressure

        while True:
            pressure = bme.pressure
            now_ns = time.perf_counter_ns()

            if pressure != last_pressure:
                elapsed_ms = (now_ns - last_ts_ns) / 1_000_000.0
                print(
                    f"Sensor pressure change detected: last={last_pressure:.2f} hPa -> current={pressure:.2f} hPa, elapsed: {elapsed_ms:.1f} ms")

                # Update tracking states
                last_ts_ns = now_ns
                last_pressure = pressure

                # Execute core calculation routine
                temp_c, humidity, pressure_hpa, iaq, meters, err = bme_temp_humid_hpa_iaq_alt(
                    bme, sea_level_pressure_hpa
                )

                if err:
                    print(f"Error during reading: {err}")

            # Match standard polling interval for environmental/air quality tests
            time.sleep(5.0)

    except KeyboardInterrupt:
        print("\nExit on User Interrupt...")
    finally:
        # close bridge interface
        i2c_bridge.close()


if __name__ == "__main__":
    main()