#!/usr/bin/env python3
"""
bme680_altitude.py

BME680 sensor test

Features:
    - temperature C
    - humidity
    - pressure hpa
    - IAQ (air quality)
    - altitude - defaults to world average Sea Level Pressure, Local estimate of sea level pressure
      can be input to the BME680 sensor driver
    - code will only print updates if the pressure has changed since last loop, the time in seconds
      is calculated. Previous test versions used (now_ns = time.perf_counter_ns()), the version uses
      lower accuracy time.monotonic which is more than sufficient for this test.

BME680 driver code:
    https://github.com/robert-hh/BME680-Micropython
    * This driver does not estimate IAQ form the K Ohms provided by the driver, This test code contains
      a conversion of K Ohms and humidity to make a guess at the proprietary Bosch IAQ calculation.

Portland - PDX airport sea level pressure updated every hour, howe er it is more accurate to use the airport station
pressure and the altitude of the station to calculate the sea level pressure.
    https://www.weather.gov/wrh/timeseries?site=KPDX

My home office is ~361 feet elevation, first BME680 says 303.5 feet (+57.5' correction needed)

by bradcar
"""
import time
import logging
from math import log

from bme680 import BME680_I2C
from lib.pi_zero_utils import pi_on_chip_temperature, scan_i2c_bus
from pi_zero_i2c_bridge_utils import PiZeroI2CBridge

# Calling script should setup:
#   logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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

    Previously this code used very crude IAQ calculation:
          iaq = log(gas_resistance) + 0.04 * percent_humidity

    :param gas_ohms: BME680 has range of  250,000 ohms (excellent) to 8,000 ohms (bad)
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


def bme_temp_humid_hpa_iaq_alt(bme, sea_level):
    """
    bme_temp_humid_hpa_iaq_alt collects and calculates primary measurements
    measurement takes ~189ms

    Direct Metrics:
        - temp - in Celsius
        - humidity - range 0.0 to 100.0 percent
        - pressure - hPA
    Derived Metrics:
        - Altitude - meters which is calculated from Gas Ohms & humidity
        - Indoor Air Quality (IAQ) - [0 to 500] which is calculated from Gas Ohms & humidity
            IAQ: 0- 50 good
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

    try:
        temp_c = bme.temperature
        percent_humidity = bme.humidity
        hpa_pressure = bme.pressure
        gas_resistance_ohms = bme.gas

        # Altitude & IAQ are derived from other measurements
        meters = 44330.0 * (1.0 - (hpa_pressure / sea_level) ** (1.0 / 5.255))
        iaq = calculate_iaq(gas_resistance_ohms, percent_humidity)

    except OSError as e:
        logging.error("BME680: Failed to read sensor.")
        return None, None, None, None, None, "ERROR_BME680:" + str(e)

    return temp_c, percent_humidity, hpa_pressure, iaq, gas_resistance_ohms, meters, None


# -------------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

    # Initialize the Pi Zero I2C bus bridge
    i2c1 = PiZeroI2CBridge("/dev/i2c-1")

    # Scan i2c devices
    scan_i2c_bus(i2c1)

    print("Example IAQ inputs and IAQ:")
    gas_resistance = 400_000.0
    humidity = 40.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}")
    gas_resistance = 200_000.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}")
    gas_resistance = 100_000.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}")
    gas_resistance = 50_000.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}")
    gas_resistance = 20_000.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}")
    gas_resistance = 15_000.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}")
    gas_resistance = 8_000.0
    print(f" %humidity: {humidity}, gas: {gas_resistance}, IAQ={calculate_iaq(gas_resistance, humidity)}\n")

    try:
        pi_celsius = pi_on_chip_temperature() or 0.0
        print(f"Pi Celsius = {pi_celsius:.1f}° C\n")

        print("Initializing I2C Bridge...")
        # Initialize the driver using hardware bridge compatibility layer
        # Note: BME680 default I2C address is usually 0x76 or 0x77
        bme = BME680_I2C(i2c=i2c1, address=0x77)
        print("Done initializing I2C Bridge\n")

        # Baseline settings
        sea_level_pressure_hpa = 1012.90
        print(f"Initial sea_level_pressure = {sea_level_pressure_hpa:.2f} hPa")

        # Set to known altitude
        home_office_alt_meters = 110.03  # ~361 feet elevation in meters
        bme.altitude = home_office_alt_meters
        print(f"Altitude set to = {bme.altitude:.2f} meters")

        # Retrieve the adjusted sea level pressure from the driver
        sea_level_pressure_hpa = bme.sea_level_pressure
        print(f"Adjusted SLP based on known altitude = {sea_level_pressure_hpa:.2f}")

        print("\nStart test Loop")

        last_timestamp_sec = time.monotonic()
        last_pressure = bme.pressure

        while True:
            pressure = bme.pressure
            now_timestamp_sec = time.monotonic()

            # Get BME680 Sensor data
            temp_c, percent_humidity, pressure_hpa, iaq, gas_resistance_ohms, meters, err = bme_temp_humid_hpa_iaq_alt(
                bme, sea_level_pressure_hpa
            )

            print(f"BME680 Temp °C = {temp_c:.1f}° C")
            print(f"BME680 Humidity = {percent_humidity:.1f}%")
            print(f"BME680 Pressure = {pressure_hpa:.2f} hPa")
            print(f"BME680 Gas resistance = {gas_resistance_ohms / 1000.0:.2f} KOhms")
            print(f"BME680 iaq = {iaq:.2f},  IAQ lower better [0 to 500]")
            print(f"BME680 Alt = {meters:.2f} meters ({meters * 3.28084:.2f} feet)\n")

            if err:
                print(f"Error during reading: {err}")

            # Sleep 1 sec, Note: 5 sec is standard for polling interval for environmental/air quality tests
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nExit on User Interrupt...")
    finally:
        i2c1.close()


if __name__ == "__main__":
    main()
