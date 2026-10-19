"""Opt-in *real Pi4* clock qualification, run with MEBS service stopped.

Never runs during normal boot. A failed/interrupted test leaves no new PASS
record and restores the conservative 1.5 GHz cpufreq ceiling.
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time

from .performance import (BASE_KHZ, EXPLORER_KHZ, VIDEO_KHZ, THROTTLE_BITS,
                          board_serial, cpu_temperature, firmware_throttled)


def _burn(stop):
    block = b'MEBS CPU stability test' * 65536
    while not stop.is_set():
        hashlib.sha256(block).digest()


def validate(target_khz, *, seconds=1800, root='/sys/devices/system/cpu/cpufreq',
             output='/var/lib/mebs/performance-cpu-test.json',
             sleep=time.sleep, now=time.monotonic, temperature=cpu_temperature,
             throttled=firmware_throttled, serial=board_serial):
    if target_khz not in (EXPLORER_KHZ, VIDEO_KHZ) or seconds < 1800:
        raise ValueError('Only a 30-minute 1.8/2.0GHz real-board test is accepted')
    if os.geteuid() != 0 or not Path('/etc/mebs/appliance').is_file():
        raise RuntimeError('Run only as root on the dedicated MEBS Pi image')
    if Path('/run/mebs.pid').exists():
        raise RuntimeError('Stop the MEBS service safely before the stress test')
    board = serial()
    policies = sorted(Path(root).glob('policy[0-9]*'))
    if not policies:
        raise RuntimeError('cpufreq policy is unavailable')
    for folder in policies:
        if int((folder/'cpuinfo_max_freq').read_text()) < target_khz:
            raise RuntimeError('Boot firmware did not expose the requested clock')
    if throttled() & THROTTLE_BITS:
        raise RuntimeError('Power/thermal fault already recorded this boot')
    if temperature() >= 70:
        raise RuntimeError('Cool the Pi below 70C before testing')
    stop = mp.Event()
    processes = []
    highest = -100.0
    minimum_observed = target_khz
    started = now()
    try:
        for folder in policies:
            (folder/'scaling_max_freq').write_text(str(target_khz))
            if int((folder/'scaling_max_freq').read_text()) != target_khz:
                raise RuntimeError('cpufreq rejected the requested clock')
        for _ in range(min(4, os.cpu_count() or 4)):
            process = mp.Process(target=_burn, args=(stop,))
            process.start()
            processes.append(process)
        while now() - started < seconds:
            value = temperature()
            highest = max(highest, value)
            mask = throttled()
            if value >= 75 or mask & THROTTLE_BITS:
                raise RuntimeError(f'Thermal/power fault: {value:.1f}C, mask={mask:#x}')
            for folder in policies:
                current = int((folder/'scaling_cur_freq').read_text())
                minimum_observed = min(minimum_observed, current)
                if current < target_khz * .95:
                    raise RuntimeError(f'Clock below target under load: {current} kHz')
            if any(not p.is_alive() for p in processes):
                raise RuntimeError('Stress worker exited')
            sleep(1)
        if throttled() & THROTTLE_BITS:
            raise RuntimeError('Firmware reported throttling after test')
        if highest >= 75:
            raise RuntimeError('Temperature threshold exceeded')
        record = {'result': 'CPU_ONLY_PASS', 'hardware_tested': True,
                  'full_system_verified': False, 'board_serial': board,
                  'tested_khz': target_khz,
                  'duration_seconds': seconds, 'maximum_temperature_c': round(highest, 2),
                  'minimum_observed_khz': minimum_observed,
                  'throttled_or_undervoltage_mask': 0,
                  'note': 'Preliminary CPU test only. Does not enable runtime boost.'}
        destination = Path(output)
        if not destination.parent.is_mount():
            raise RuntimeError('OS settings partition is not mounted')
        fd, temporary = tempfile.mkstemp(prefix='.performance-cpu-', dir=destination.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return record
    finally:
        stop.set()
        for process in processes:
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
        for folder in policies:
            try:
                (folder/'scaling_max_freq').write_text(str(BASE_KHZ))
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mhz', type=int, choices=(1800, 2000), required=True)
    parser.add_argument('--minutes', type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(validate(args.mhz * 1000, seconds=args.minutes * 60), indent=2))


if __name__ == '__main__':
    main()
