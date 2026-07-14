import time
import board
import busio

# --- MicroPython Time Compatibility Patch ---
if not hasattr(time, 'sleep_ms'):
    time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)
if not hasattr(time, 'sleep_us'):
    time.sleep_us = lambda us: time.sleep(us / 1000000.0)


# ==============================================================================
# Linux Hardware Interface Layer Bridge (Adafruit Blinka Bus Engine)
# ==============================================================================
class LinuxI2CBridge:
    def __init__(self, bus_number=1):
        print("[BMP-LINUX] Loading Adafruit Blinka hardware I2C engine...")
        # Initialize the shared global board I2C bus object
        self.i2c = board.I2C()
        print("[BMP-LINUX] Shared I2C hardware bus acquired successfully.")

    def open(self):
        pass

    def close(self):
        pass

    def scan(self):
        """Scans the bus safely using Adafruit's lock-aware protocol"""
        print("[I2C SCAN] Starting Adafruit bus lock probe...")
        while not self.i2c.try_lock():
            pass

        found_devices = []
        try:
            addresses = self.i2c.scan()
            for addr in addresses:
                print(f"[I2C SCAN] Device detected at address: 0x{addr:02X}")
                found_devices.append(addr)
        finally:
            self.i2c.unlock()

        print(f"[I2C SCAN] Scan complete. Found: {[hex(a) for a in found_devices]}")
        return found_devices

    def readfrom_mem(self, address, register, num_bytes):
        if num_bytes < 1:
            return bytearray()

        write_buf = bytes([register])
        read_buf = bytearray(num_bytes)

        # Acquire the hardware lock to guarantee an uninterrupted sequence
        while not self.i2c.try_lock():
            pass

        try:
            # writeto_then_readfrom executes a bit-perfect Repeated-Start
            # using Adafruit's robust underlying system backends
            self.i2c.writeto_then_readfrom(address, write_buf, read_buf)
            return read_buf
        except Exception as e:
            print(f"[I2C-CORE] Adafruit Hardware Bus Exception: {e}")
            raise e
        finally:
            self.i2c.unlock()

    def writeto_mem(self, address, register, data):
        if isinstance(data, int):
            data = bytes([data])
        elif isinstance(data, list):
            data = bytes(data)

        payload = bytes([register]) + data

        while not self.i2c.try_lock():
            pass

        try:
            self.i2c.writeto(address, payload)
        except Exception as e:
            print(f"[I2C-CORE] Adafruit Hardware Write Exception: {e}")
            raise e
        finally:
            self.i2c.unlock()