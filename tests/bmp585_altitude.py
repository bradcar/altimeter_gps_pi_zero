import time

from lib.micropython_bmpxxx import bmpxxx
from lib.pi_zero_utils import pi_on_chip_temperature, scan_i2c_bus
from lib.pi_zero_i2c_bridge_utils import PiZeroI2CBridge


# -------------------------------------------------------------------------
def main():
    i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    scan_i2c_bus(i2c1)

    try:
        pi_celsius = pi_on_chip_temperature() or 0.0
        print(f"Pi Celsius = {pi_celsius:.1f}° C\n")

        # Initialize the driver using hardware bridge compatibility layer
        bmp = bmpxxx.BMP585(i2c=i2c1, address=0x47)

        # Configure OverSampling and IIR filter settings
        bmp.pressure_oversample_rate = bmp.OSR4
        bmp.temperature_oversample_rate = bmp.OSR4
        bmp.iir_coefficient = bmp.COEF_1

        sea_level_pressure = bmp.sea_level_pressure
        print(f"Initial sea_level_pressure = {sea_level_pressure:.2f} hPa")

        # Set known reference altitude
        home_office_alt_meters = 110.03  # ~361 feet elevation in meters
        bmp.altitude = home_office_alt_meters
        print(f"Altitude set to = {bmp.altitude:.2f} meters")
        print(f"Adjusted SLP based on known altitude = {bmp.sea_level_pressure:.2f} hPa\n")

        print("\nStart test Loop")

        # State tracking variables
        last_ts_ns = time.perf_counter_ns()
        last_pressure = bmp.pressure

        while True:
            pressure = bmp.pressure
            now_ns = time.perf_counter_ns()

            if pressure != last_pressure:
                elapsed_ms = (now_ns - last_ts_ns) / 1_000_000.0
                print(f"Sensor pressure = {pressure:.4f} hPa last={last_pressure:.4f}, {elapsed_ms:.1f} ms")

                # Update tracking states
                last_ts_ns = now_ns
                last_pressure = pressure

                meters = bmp.altitude
                print(f"Altitude = {meters:.3f} meters")

                temp = bmp.temperature
                print(f"temp = {temp:.2f} C\n")

            # small sleep
            time.sleep(0.005)

    except KeyboardInterrupt:
        print("\nExit on User Interrupt...")
    finally:
        # close bridge interface
        i2c1.close()


if __name__ == "__main__":
    main()
