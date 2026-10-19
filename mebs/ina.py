"""INA226/INA231 register drivers and a register-level test double.

INA231 has no documented device-ID register. An explicit, independently checked
module model is required; an I2C ACK is never treated as identification.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import time


class SensorError(ValueError):
    pass


@dataclass(frozen=True)
class BatteryMeasurement:
    voltage: float
    current_a: float | None
    power_w: float | None
    shunt_v: float
    model: str
    source: str
    timestamp_utc: str
    sampled_monotonic: float


def word(bus, register, signed=False):
    data = bus.register(register)
    if len(data) != 2:
        raise SensorError('short INA register read')
    return int.from_bytes(data, 'big', signed=signed)


class INAMonitor:
    model = ''
    max_bus_v = 0.

    def __init__(self, bus, shunt_ohms=None, polarity=1, *, model_confirmed=False,
                 max_current_a=None, program_calibration=False):
        if shunt_ohms is not None and (type(shunt_ohms) not in (float, int)
                                        or not math.isfinite(shunt_ohms) or shunt_ohms <= 0):
            raise ValueError('positive measured shunt resistance required')
        if polarity not in (-1, 1):
            raise ValueError('invalid current polarity')
        if max_current_a is not None and (type(max_current_a) not in (float, int)
                                          or not math.isfinite(max_current_a) or max_current_a <= 0):
            raise ValueError('positive maximum current required')
        self.bus, self.shunt, self.polarity = bus, shunt_ohms, polarity
        self.max_current_a = max_current_a
        self.current_lsb = self.calibration = None
        if self.model == 'INA226':
            if word(bus, 0xFE) != 0x5449 or word(bus, 0xFF) & 0xFFF0 != 0x2260:
                raise SensorError('INA226 manufacturer/die ID mismatch')
        elif self.model == 'INA231':
            if not model_confirmed:
                raise SensorError('INA231 model must be confirmed from module documentation')
            # Register 00h exists on INA231, but is not a unique model ID.
            word(bus, 0x00)
        else:
            raise SensorError('unsupported INA model')
        if program_calibration:
            if shunt_ohms is None or max_current_a is None:
                raise ValueError('shunt and maximum current required for calibration')
            self.current_lsb = max_current_a / 32767
            self.calibration = math.floor(0.00512 / (self.current_lsb * shunt_ohms))
            if not 1 <= self.calibration <= 0x7FFF or max_current_a * shunt_ohms > 0.08192:
                raise ValueError('INA calibration/shunt range invalid')
            bus.write(bytes((0x05, self.calibration >> 8, self.calibration & 0xFF)))
            if word(bus, 0x05) != self.calibration:
                raise SensorError('INA calibration readback mismatch')

    def sample(self):
        shunt_v = word(self.bus, 0x01, signed=True) * 2.5e-6
        raw_bus = word(self.bus, 0x02)
        if raw_bus & 0x8000:
            raise SensorError('invalid INA bus voltage sign bit')
        voltage = raw_bus * 0.00125
        if not 0 <= voltage <= self.max_bus_v:
            raise SensorError('INA bus voltage out of range')
        current = self.polarity * shunt_v / self.shunt if self.shunt else None
        if current is not None and self.max_current_a is not None and abs(current) > self.max_current_a * 1.05:
            raise SensorError('INA current above configured maximum')
        source = 'SIMULATION' if getattr(self.bus, 'simulation', False) else 'REAL'
        return BatteryMeasurement(voltage, current, voltage * current if current is not None else None,
                                  shunt_v, self.model, source, datetime.now(timezone.utc).isoformat(),
                                  time.monotonic())

    def read(self):
        """Preserve the V2 voltage/current tuple API for existing callers."""
        measurement = self.sample()
        return measurement.voltage, measurement.current_a


class INA226(INAMonitor):
    model = 'INA226'
    max_bus_v = 36.


class INA231(INAMonitor):
    model = 'INA231'
    max_bus_v = 28.


class VirtualINARegisters:
    """Injected register responses; no host I2C/GPIO access."""
    simulation = True

    def __init__(self, model, shunt_ohms, *, clock=time.monotonic):
        if model not in ('INA226', 'INA231') or shunt_ohms <= 0:
            raise ValueError('virtual model and shunt required')
        self.model, self.shunt, self.clock = model, shunt_ohms, clock
        self.connected = True
        self.fail_next = False
        self.updated = None
        self.registers = {0x00: 0x4127, 0x01: 0, 0x02: 0, 0x05: 0}
        if model == 'INA226':
            self.registers.update({0xFE: 0x5449, 0xFF: 0x2260})

    def inject(self, voltage, current_a, *, updated=None):
        if not all(type(value) in (float, int) and math.isfinite(value)
                   for value in (voltage, current_a)):
            raise ValueError('finite injected values required')
        bus_raw = round(voltage / .00125)
        shunt_raw = round(current_a * self.shunt / 2.5e-6)
        if not 0 <= bus_raw <= 0x7FFF or not -32768 <= shunt_raw <= 32767:
            raise ValueError('virtual INA ADC range exceeded')
        self.registers[0x02] = bus_raw
        self.registers[0x01] = shunt_raw & 0xFFFF
        self.updated = self.clock() if updated is None else updated

    def register(self, register, count=2):
        if not self.connected or self.fail_next:
            self.fail_next = False
            raise OSError('virtual I2C device disconnected or NACK')
        if register in (0x01, 0x02) and (self.updated is None or self.clock() - self.updated > 2.5):
            raise SensorError('virtual INA sample stale')
        if count != 2 or register not in self.registers:
            raise OSError('virtual INA register unsupported')
        return self.registers[register].to_bytes(2, 'big')

    def write(self, data):
        if not self.connected or self.fail_next:
            self.fail_next = False
            raise OSError('virtual I2C write failed')
        if len(data) != 3 or data[0] != 0x05:
            raise SensorError('virtual INA accepts calibration writes only')
        self.registers[0x05] = int.from_bytes(data[1:], 'big')
