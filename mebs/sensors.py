"""Optional, explicitly configured sensors. No guessed battery calibration.

I2C devices use separate fds: I2C_SLAVE will refuse a kernel-owned address.
No FORCE, bus scan, GPIO, ADC or charger writes. All measurements are injectable.
"""
from dataclasses import dataclass
import fcntl
import math
import os
from pathlib import Path

from .ina import INA226, INA231, BatteryMeasurement, SensorError, VirtualINARegisters


@dataclass
class Reading:
    cpu_c: float | None = None
    ram_percent: float | None = None
    voltage: float | None = None
    current_a: float | None = None
    power_w: float | None = None
    sensor_source: str = 'N/A'
    sensor_model: str = 'N/A'
    sampled_utc: str | None = None
    sampled_monotonic: float | None = None
    percent: float | None = None
    runtime_hours: float | None = None
    error: str = ''


class I2C:
    def __init__(self, bus, address):
        if not 0x08 <= address <= 0x77:
            raise ValueError('invalid 7-bit I2C address')
        self.fd = os.open(bus, os.O_RDWR | os.O_CLOEXEC)
        try:
            fcntl.ioctl(self.fd, 0x0703, address)  # I2C_SLAVE, never FORCE
        except BaseException:
            self.close()
            raise

    def write(self, data):
        if os.write(self.fd, data) != len(data):
            raise OSError('short I2C write')

    def read(self, count):
        value = os.read(self.fd, count)
        if len(value) != count:
            raise OSError('short I2C read')
        return value

    def register(self, register, count=2):
        self.write(bytes([register]))
        return self.read(count)

    def close(self):
        os.close(self.fd)


def estimate(voltage, current, curve, capacity_ah):
    """User-calibrated OCV estimate. Under-load voltage makes this approximate."""
    if not curve or not capacity_ah or capacity_ah <= 0:
        return None, None
    points = sorted(curve)
    if len(points) < 2 or any(points[i][0] >= points[i + 1][0] for i in range(len(points)-1)):
        raise ValueError('invalid OCV curve')
    pct = points[0][1] if voltage <= points[0][0] else points[-1][1]
    for (v0, p0), (v1, p1) in zip(points, points[1:]):
        if v0 <= voltage <= v1:
            pct = p0 + (p1 - p0) * (voltage - v0) / (v1 - v0)
            break
    pct = max(0, min(100, pct))
    return pct, (capacity_ah * pct / 100 / current if current is not None and current > .01 else None)


class BatteryGuard:
    def __init__(self, warn=None, block=None):
        if (warn is not None and block is None) or (block is not None and
                (not 0 < block or warn is not None and not block < warn)):
            raise ValueError('validated threshold required: 0 < block < optional warn')
        self.warn, self.block = warn, block

    def status(self, voltage):
        if self.block is None:
            return 'UNCONFIGURED'
        if voltage is None or not math.isfinite(voltage):
            return 'UNKNOWN'  # configured protection fails closed on missing measurement
        return 'BLOCK' if voltage <= self.block else 'WARN' if self.warn is not None and voltage <= self.warn else 'OK'

    def allows_start(self, voltage):
        return self.status(voltage) in ('OK', 'WARN', 'UNCONFIGURED')


def cpu_temperature(path='/sys/class/thermal/thermal_zone0/temp'):
    value = float(Path(path).read_text()) / 1000
    if not math.isfinite(value) or not -20 <= value <= 125:
        raise ValueError('invalid CPU temperature')
    return value


def ram_usage(path='/proc/meminfo'):
    fields = {}
    for line in Path(path).read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('MemTotal', 'MemAvailable'):
            fields[key] = int(value.strip().split()[0])
    total, available = fields['MemTotal'], fields['MemAvailable']
    if total <= 0 or not 0 <= available <= total:
        raise ValueError('invalid memory telemetry')
    return 100 * (total - available) / total


def validate_addresses(config):
    used = []
    for name, default in [('ina226', 0x40), ('ina231', 0x40), ('ds3231', 0x68)]:
        item = config.get(name, {})
        if item.get('enabled', False):
            address = item.get('address', default)
            if type(address) is not int or not 0x08 <= address <= 0x77:
                raise ValueError('invalid address: ' + name)
            used.append(address)
    if len(set(used)) != len(used):
        raise ValueError('I2C address collision')
