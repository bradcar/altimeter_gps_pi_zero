# pi_zero_i2c_bridge_utils.py
"""
Raspberry Pi Zero I2C Bridge Object

Using i2c 1 Primary i2c on Pi Zero:
    i2c1 = PiZeroI2CBridge()
    or:
    i2c1 = PiZeroI2CBridge("/dev/i2c-1")
    SDA: GPIO 2 (Physical Pin 3)
    SCL: GPIO 3 (Physical Pin 2)

Using i2c 0 Secondary i2c on Pi Zero:
    i2c0 = PiZeroI2CBridge("/dev/i2c-0")
    SDA: GPIO 0 (Physical Pin 27)
    SCL: GPIO 1 (Physical Pin 28)

"""
from periphery import I2C


class PiZeroI2CBridge:
    def __init__(self, bus_path="/dev/i2c-1"):

        self.i2c = I2C(bus_path)

    def scan(self):
        """Scan the I2C bus and return a list 7-bit i2c addresses, 0x08 to 0x77 (8 to 119)"""
        active_devices = []
        for addr in range(0x08, 0x78):
            try:
                # Try a 0-byte write to ping the address
                self.writeto(addr, b"")
                active_devices.append(addr)
            except OSError:
                # No device responded (or NACK returned), skip it
                continue
        return active_devices

    def writeto(self, addr, buf):
        """Perform a raw write to an I2C device (no register address)"""
        msgs = [I2C.Message(list(buf))]
        self.i2c.transfer(addr, msgs)

    def readfrom(self, addr, nbytes):
        """Perform a raw read from an I2C device"""
        read_msg = I2C.Message([0] * nbytes, read=True)
        self.i2c.transfer(addr, [read_msg])
        return bytes(read_msg.data)

    def writeto_mem(self, addr, memaddr, buf):
        """Write to a specific register on the I2C device"""
        msgs = [I2C.Message([memaddr] + list(buf))]
        self.i2c.transfer(addr, msgs)

    def readfrom_mem(self, addr, memaddr, nbytes):
        """Read from a specific register on the I2C device"""
        write_msg = I2C.Message([memaddr])
        read_msg = I2C.Message([0] * nbytes, read=True)
        self.i2c.transfer(addr, [write_msg, read_msg])
        return bytes(read_msg.data)

    def readfrom_mem_into(self, addr, memaddr, buf):
        """Read from a specific register directly into a pre-allocated buffer"""
        write_msg = I2C.Message([memaddr])
        read_msg = I2C.Message([0] * len(buf), read=True)
        self.i2c.transfer(addr, [write_msg, read_msg])

        # Copy the retrieved data directly into the passed-in buffer slice
        buf[:] = read_msg.data

    def close(self):
        self.i2c.close()
