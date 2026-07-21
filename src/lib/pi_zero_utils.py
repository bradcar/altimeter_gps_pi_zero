# pi_zero_utils.py
"""
General purpose Pi Zero functions

Temperature:
    pico_temperature(): get temperature of internal on-chip temperature.

Time-out:
    time_out(): wrapper to timeout number of seconds.
"""
import logging
import signal
from contextlib import contextmanager

# Calling script should setup:
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def pi_on_chip_temperature() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            # Read milli-celsius string ("43500")
            raw_temp = f.read().strip()
            celsius = float(raw_temp) / 1000.0
            logger.info(f"Pi Zero on-chip Temperature: {celsius}° C")
            return celsius
    except (FileNotFoundError, ValueError, IOError):
        return 0.0


def scan_i2c_bus(i2c_primary):
    logger.info("I2C device Scan...")
    lis3mdl_detected = None
    oled_detected = None
    bmp_detected = None
    bme_detected = None

    try:
        devices1 = i2c_primary.scan()
        if not devices1:
            logger.error("No I2C1 devices detected (primary). Check your wiring.")
            return None

        logger.info(f"Found {len(devices1)} I2C1 {'device' if len(devices1) == 1 else 'devices'}:")
        for address in devices1:
            addr_hex = hex(address)

            if address in (0x47, 0x46):
                identity = "likely BMP585/581 pressure Sensor"
                bmp_detected = True
            elif address in (0x7f, 0x7e):
                identity = "likely BMP390 pressure Sensor"
                bmp_detected = True
            elif address in (0x77, 0x76):
                identity = "likely BME680 or BMP280/BME280 pressure Sensor"
                bmp_detected = True
                bme_detected = True
            elif address == 0x3C:
                identity = "likely SSD1305 OLED display"
                oled_detected = True
            elif address in (0x1C, 0x1E):
                identity = "likely LIS3MDL Magnetometer"
                lis3mdl_detected = address
            elif address in (0x14,):
                identity = "likely Waveshare Eink Touch "
                waveshare_touch_detected = address
            else:
                identity = "unknown device signature"

            logger.info(f"  Device: Hex: {addr_hex} ({address}) -> {identity}")

    except RuntimeError as e:
        logger.error(f"I2C Hardware Error during scan: {e}")

    return None


@contextmanager
def timeout(seconds, error_message="Timed out"):
    def signal_handler(signum, frame):
        raise TimeoutError(f"{error_message}")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
