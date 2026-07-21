import time
import smbus2
import RPi.GPIO as GPIO

# Waveshare 2.13" Touch HAT GPIO Pinout
RST_PIN = 22
INT_PIN = 27

def reset_gt911():
    print("Pulsing GT911 Reset/INT GPIOs...")
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RST_PIN, GPIO.OUT)
    GPIO.setup(INT_PIN, GPIO.OUT)

    # Reset sequence forcing Address 0x14:
    # Set RST LOW and INT LOW for 20ms
    GPIO.output(RST_PIN, GPIO.LOW)
    GPIO.output(INT_PIN, GPIO.LOW)
    time.sleep(0.02)

    # Bring RST HIGH while holding INT LOW
    GPIO.output(RST_PIN, GPIO.HIGH)
    time.sleep(0.01)

    # Release INT pin (set back to input)
    GPIO.setup(INT_PIN, GPIO.IN)
    time.sleep(0.05)

def scan_i2c():
    bus = smbus2.SMBus(1)
    found = []
    print("Scanning I2C Bus 1...")
    for addr in range(0x03, 0x78):
        try:
            bus.write_quick(addr)
            found.append(hex(addr))
        except Exception:
            pass
    print(f"Active I2C Addresses Found: {found}")

if __name__ == "__main__":
    reset_gt911()
    scan_i2c()