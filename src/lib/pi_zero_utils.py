# pi_zero_utils.py
"""
General purpose Pi Zero functions

Temperature:
    pico_temperature(): get temperature of internal on-chip temperature.

Time-out:
    time_out(): wrapper to timeout number of seconds.
"""
import signal
from contextlib import contextmanager


def pico_temperature() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            # Read milli-celsius string ("43500")
            raw_temp = f.read().strip()
            return float(raw_temp) / 1000.0
    except (FileNotFoundError, ValueError, IOError):
        return 0.0


def scan_i2c_bus(i2c_primary):
    print("I2C device Scan...")
    lis3mdl_detected = None
    oled_detected = None
    bmp_detected = None
    bme_detected = None

    try:
        devices1 = i2c_primary.scan()
        if not devices1:
            print("Error: No I2C1 devices detected (primary). Check your wiring")
        else:
            print(f"\nFound I2C1 {len(devices1)} device(s):")
            for address in devices1:
                print(f" I2C1 Device: Hex: {hex(address)} ({address})")
                if address == 0x47 or address == 0x46:
                    print(" -> likely BMP585/581 pressure Sensor")
                    bmp_detected = True
                elif address == 0x7f or address == 0x7e:
                    print(" -> likely BMP390 pressure Sensor")
                    bmp_detected = True
                elif address == 0x77 or address == 0x76:
                    print(" -> likely BME680 or BMP280 or BME280 pressure Sensor")
                    bmp_detected = True
                    bme_detected = True
                elif address == 0x3C:
                    print(" -> likely SSD1305 OLED display")
                    oled_detected = True
                elif address == 0x1C or address == 0x1E:
                    print(" -> likely LIS3MDL Magnetometer")
                    lis3mdl_detected = address
                else:
                    print(f" -> unknown device")
    except RuntimeError as e:
        print(f"I2C Hardware Error: {e}")
    print("\n")
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
