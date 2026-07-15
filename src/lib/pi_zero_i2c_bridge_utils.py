#pi_zero_i2c_bridge_utils.py
"""
Raspberry Pi Zero I2C Bridge Object
"""
from periphery import I2C


class PiZeroI2CBridge:
    def __init__(self, bus_path="/dev/i2c-1"):
        # Maps to default Pi Zero hardware I2C pins: SDA (GPIO2), SCL (GPIO3)
        self.i2c = I2C(bus_path)

    def scan(self):
        """Scan the I2C bus and return a list of responding 7-bit addresses."""
        active_devices = []
        # Standard 7-bit I2C address range is 0x08 to 0x77 (8 to 119)
        for addr in range(0x08, 0x78):
            try:
                # Try a raw, 0-byte write to ping the address
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
