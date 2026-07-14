import time
import board
import adafruit_bmp5xx

SEALEVELPRESSURE_HPA = 1013.25

# 1. Initialize the Linux I2C bus via Blinka
print("Initializing I2C bus...")
i2c = board.I2C()

# 2. Add a pause to let the bonnet power rails stabilize
print("Stabilizing power...")
time.sleep(2.0)

try:
    # 3. Use the corrected factory method for Blinka
    print("Connecting to BMP585...")
    bmp = adafruit_bmp5xx.BMP5XX.over_i2c(i2c)

    bmp.sea_level_pressure = SEALEVELPRESSURE_HPA

    print("Starting sensor loop...")
    while True:
        # 4. Official way to poll for data readiness
        if bmp.data_ready:
            temp_f = (bmp.temperature * (9 / 5)) + 32
            print(
                f"temp F: {temp_f:.2f} "
                f"pressure: {bmp.pressure:.2f} hPa "
                f"Approx altitude: {bmp.altitude:.2f} m"
            )
        time.sleep(0.5)  # Polling at 2Hz

except Exception as e:
    print(f"\nHardware communication failure: {e}")
    print("Tip: If you see [Errno 121], the physical sensor is not ACK-ing.")