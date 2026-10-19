"""Fail-closed Pi4 CPU frequency limits; never changes firmware boot clocks.

Only the live appliance creates this controller. QEMU/host previews have no
cpufreq policy or VideoCore status and therefore cannot enable boost modes.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import struct
from threading import Lock
import time

from .sensors import cpu_temperature


BASE_KHZ = 1_500_000
EXPLORER_KHZ = 1_800_000
VIDEO_KHZ = 2_000_000
THROTTLE_BITS = 0xF000F  # active or occurred: undervoltage, cap, throttle, soft temp
MAILBOX_IOCTL_ARM64 = 0xC0086400  # _IOWR(100, 0, char *) on the ARM64 image


def firmware_throttled(device='/dev/vcio', ioctl=fcntl.ioctl):
    """Query VideoCore's get_throttled through the firmware mailbox.

    Raspberry Pi's vcgencmd uses the same property tag (0x00030080).
    An unavailable device or malformed reply is an error, never a clean bill.
    """
    command = b'get_throttled\0'
    buffer = bytearray(24 + 4096 + 4)
    struct.pack_into('<6I', buffer, 0, len(buffer), 0, 0x00030080, 4096, 0, 0)
    buffer[24:24 + len(command)] = command
    with open(device, 'rb', buffering=0) as stream:
        ioctl(stream.fileno(), MAILBOX_IOCTL_ARM64, buffer, True)
    total, response, tag, allocated, returned = struct.unpack_from('<5I', buffer)
    if (total != len(buffer) or response != 0x80000000 or tag != 0x00030080
            or allocated != 4096 or not returned & 0x80000000):
        raise OSError('Invalid VideoCore mailbox reply')
    count = returned & 0x7fffffff
    if not 0 < count <= 4096:
        raise OSError('Invalid VideoCore reply size')
    message = bytes(buffer[24:24 + count]).split(b'\0', 1)[0].decode('ascii', 'strict')
    match = re.fullmatch(r'throttled=0x([0-9a-fA-F]+)', message)
    if not match:
        raise OSError('Invalid get_throttled response')
    return int(match.group(1), 16)


def board_serial(path='/proc/device-tree/serial-number'):
    value = Path(path).read_bytes().rstrip(b'\0').decode('ascii', 'strict').strip()
    if not re.fullmatch(r'[0-9a-fA-F]{8,32}', value):
        raise OSError('Pi board serial unavailable')
    return value.lower()


def validated_limits(path, serial):
    """Read a completed *hardware* test record, not an enable flag.

    The record is advisory evidence tied to one board. The controller also
    requires actual cpufreq support and a clean, current firmware reading.
    """
    try:
        record = json.loads(Path(path).read_text())
        if (record.get('result') != 'PASS' or record.get('board_serial') != serial
                or record.get('hardware_tested') is not True
                or record.get('full_system_verified') is not True
                or record.get('duration_seconds', 0) < 1800
                or record.get('maximum_temperature_c', 100) >= 75
                or record.get('throttled_or_undervoltage_mask') != 0):
            return set()
        allowed = record.get('validated_khz', [])
        return set(allowed) & {EXPLORER_KHZ, VIDEO_KHZ}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()


class ClockPolicy:
    def __init__(self, root='/sys/devices/system/cpu/cpufreq',
                 validation='/var/lib/mebs/performance-validation.json',
                 temperature=cpu_temperature, throttled=firmware_throttled,
                 serial=board_serial, clock=time.monotonic):
        self.root = Path(root)
        self.validation = Path(validation)
        self.lock = Lock()
        self.temperature, self.throttled, self.serial, self.clock = temperature, throttled, serial, clock
        self.policies = []
        self.allowed = set()
        self.fault_latched = False
        self.cool_since = None
        self.last_applied = {}
        self.external_ceiling = {}
        self.state = {'mode': 'UNAVAILABLE', 'limit_khz': None, 'reason': 'cpufreq unavailable',
                      'temperature_c': None, 'throttled_mask': None}
        for folder in sorted(self.root.glob('policy[0-9]*')):
            try:
                low = int((folder/'scaling_min_freq').read_text())
                high = int((folder/'cpuinfo_max_freq').read_text())
                current = int((folder/'scaling_max_freq').read_text())
                if low <= BASE_KHZ <= high and current >= low:
                    self.policies.append((folder, low))
                    self.external_ceiling[folder] = min(high, current)
            except (OSError, ValueError):
                continue
        try:
            self.allowed = validated_limits(self.validation, self.serial())
        except (OSError, ValueError):
            pass

    def _apply(self, limit):
        if not self.policies:
            raise OSError('cpufreq policy unavailable or cannot cap at 1.5GHz')
        actual = []
        for folder, low in self.policies:
            maximum = folder/'scaling_max_freq'
            observed = int(maximum.read_text())
            previous = self.last_applied.get(folder)
            if previous is not None and observed != previous:
                # Another actor tightened the policy; never override it upward.
                self.external_ceiling[folder] = min(self.external_ceiling[folder], observed)
            requested = min(limit, self.external_ceiling[folder])
            if requested < low:
                raise OSError('cpufreq policy minimum exceeds safe limit')
            if observed != requested:
                maximum.write_text(str(requested))
            readback = int(maximum.read_text())
            self.last_applied[folder] = readback
            if readback > requested or readback > BASE_KHZ and limit == BASE_KHZ:
                raise OSError('cpufreq rejected safe cap')
            actual.append(readback)
        return min(actual)

    def tick(self, *, explorer=False, video=False, backup=False):
        """Run once per second in the appliance loop; returns honest status."""
        with self.lock:
            return self._tick(explorer=explorer, video=video, backup=backup)

    def _tick(self, *, explorer=False, video=False, backup=False):
        wanted = 'BASE' if backup else 'VIDEO' if video else 'EXPLORER' if explorer else 'BASE'
        ceiling = {'BASE': BASE_KHZ, 'EXPLORER': EXPLORER_KHZ, 'VIDEO': VIDEO_KHZ}[wanted]
        reason = ''
        try:
            temp = float(self.temperature())
            if not -20 <= temp <= 125:
                raise ValueError('Invalid CPU temperature')
        except (OSError, ValueError):
            temp = None
            reason = 'CPU temperature unavailable'
        try:
            mask = int(self.throttled())
        except (OSError, ValueError, TypeError):
            mask = None
            reason = 'VideoCore power/throttle status unavailable'
        if mask is not None and mask & THROTTLE_BITS:
            self.fault_latched = True
            reason = 'Undervoltage or throttling detected'
        if temp is not None and temp >= 80:
            reason = 'CPU at or above 80C: base limit'
            self.cool_since = None
        elif temp is not None and temp >= 75:
            reason = 'CPU at or above 75C: boost disabled'
            self.cool_since = None
        elif temp is not None and temp <= 70:
            if self.cool_since is None:
                self.cool_since = self.clock()
        else:
            self.cool_since = None
        safe = (temp is not None and temp < 75 and mask == 0 and not self.fault_latched
                and self.cool_since is not None and self.clock() - self.cool_since >= 30)
        if wanted != 'BASE' and (not safe or ceiling not in self.allowed):
            if not reason:
                reason = 'Clock not hardware-validated or cooling interval incomplete'
            wanted, ceiling = 'BASE', BASE_KHZ
        if backup and not reason:
            reason = 'Backup stability mode'
        try:
            applied = self._apply(ceiling)
            if wanted != 'BASE' and applied < ceiling:
                applied = self._apply(BASE_KHZ)
                wanted, reason = 'BASE', 'Boot clock or cpufreq below requested mode'
            self.state = {'mode': wanted, 'limit_khz': applied, 'reason': reason,
                          'temperature_c': temp, 'throttled_mask': mask}
        except (OSError, ValueError) as exc:
            # A failure after changing one of several policies must not leave
            # that policy boosted while the controller reports unavailable.
            for folder, low in self.policies:
                try:
                    maximum = folder/'scaling_max_freq'
                    maximum.write_text(str(max(low, min(BASE_KHZ, self.external_ceiling[folder]))))
                except OSError:
                    pass
            self.state = {'mode': 'UNAVAILABLE', 'limit_khz': None,
                          'reason': str(exc), 'temperature_c': temp, 'throttled_mask': mask}
        return self.state
