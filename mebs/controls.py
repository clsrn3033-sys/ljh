"""Display-independent controls; worker and UI share one lock, never copy inline."""
from dataclasses import replace
import json
import os
from pathlib import Path
from threading import RLock
import time

from .settings import Settings, SettingsStore
from .sensors import BatteryGuard, Reading

BUSY = {'MOUNTING', 'SCANNING', 'COPYING', 'VERIFYING', 'FINAL_CHECK', 'UNMOUNTING'}


class Controls:
    def __init__(self, store, clock=time.monotonic, guard=None):
        self.lock = RLock()
        self.store, self.clock = store, clock
        self.settings = store.load()
        self.state = {'state': 'READY', 'error': store.error}
        self.reading = Reading()
        self.guard = guard or BatteryGuard()
        self.panel = self.locked = self.screen_off = self.confirm_power = False
        self.shutdown_pending = self.shutting_down = False
        self.worker_active = False
        self.shutdown_requires_safe = False
        self.last_touch = clock()
        self.notice = store.error
        self.effective_brightness = self.settings.brightness

    def update(self, state):
        with self.lock:
            self.state = dict({k: v for k, v in self.state.items() if k in ('free_bytes', 'needed_bytes')}, **state)
            if state.get('state') in ('ERROR', 'CANCELLED', 'AMBIGUOUS', 'RECOVERY_REQUIRED'):
                self.screen_off = False
                self.shutdown_pending = False  # failed job never triggers queued shutdown
                self.notice = state.get('error', '장치 연결을 확인하세요.')

    def configure(self, **changes):
        candidate = replace(self.settings, **changes)
        try:
            self.store.save(candidate)
        except OSError as exc:
            self.notice = '설정 저장 실패: ' + str(exc)
            return False
        self.settings = candidate
        return True

    def begin_job(self):
        with self.lock:
            if self.shutting_down or self.shutdown_pending or self.worker_active:
                return False
            if self.battery_status() in ('BLOCK', 'UNKNOWN'):
                self.notice = '배터리 보호: 전압 측정/충전 상태를 확인하세요.'
                self.screen_off = False
                return False
            self.worker_active = True
            return True

    def battery_status(self):
        """Fail closed when configured pack protection loses fresh telemetry."""
        with self.lock:
            if self.guard.block is None:
                return 'UNCONFIGURED'
            stamp = self.reading.sampled_monotonic
            if stamp is None or self.clock() - stamp > 2.5 or stamp > self.clock() + 1:
                return 'UNKNOWN'
            return self.guard.status(self.reading.voltage)

    def battery_stop_required(self):
        return self.battery_status() in ('BLOCK', 'UNKNOWN')

    def finish_job(self, state):
        with self.lock:
            self.update(state)
            self.worker_active = False

    def request_shutdown(self):
        with self.lock:
            self.confirm_power = True
            self.screen_off = False

    def confirm_shutdown(self):
        with self.lock:
            if not self.confirm_power:
                return
            self.confirm_power = False
            self.shutdown_pending = True
            self.shutdown_requires_safe = self.worker_active
            self.notice = '백업 성공·안전 분리 후 종료 예약' if self.worker_active else '안전 종료 준비'

    def shutdown_ready(self):
        return (self.shutdown_pending and not self.worker_active and not self.shutting_down
                and self.state.get('state') not in BUSY
                and (not self.shutdown_requires_safe or (self.state.get('state') == 'SAFE_TO_REMOVE'
                                                       and self.state.get('safe_to_remove') is True)))

    def perform_shutdown(self, flush, save_log, poweroff):
        # Serialized against begin_job. Backups are unmounted by run_job before ready.
        with self.lock:
            if not self.shutdown_ready():
                return False
            self.shutting_down = True
            try:
                flush()
                save_log(dict(self.state))
                flush()  # include final log/metadata writes
                poweroff()
                self.shutdown_pending = False
                return True
            except Exception as exc:
                self.shutting_down = self.shutdown_pending = False
                self.notice = '종료 실패: ' + str(exc)
                self.screen_off = False
                return False

    def tick(self):
        with self.lock:
            now = self.clock()
            if (self.state.get('state') not in ('ERROR', 'CANCELLED', 'AMBIGUOUS') and self.settings.screen_timeout
                    and now - self.last_touch >= self.settings.screen_timeout):
                self.screen_off = True
            self.effective_brightness = self.settings.brightness
            if self.settings.night_mode:
                self.effective_brightness = min(30, self.effective_brightness)
            status = self.battery_status()
            if status in ('BLOCK', 'UNKNOWN', 'WARN'):
                self.notice = '배터리 보호: ' + status
                self.screen_off = False

    def gesture(self, start, end, duration=0):
        """One release gesture, pixel coordinates on 800x480. Wake consumes touch.

        Locked mode allows power and errors; hold top-left >=2s to unlock.
        """
        with self.lock:
            self.last_touch = self.clock()
            if self.screen_off:
                self.screen_off = False
                return 'wake'
            x, y = end
            if self.confirm_power:
                if 435 <= x <= 725 and 270 <= y <= 330:
                    self.confirm_shutdown()
                    return 'shutdown-confirmed'
                if 75 <= x <= 365 and 270 <= y <= 330:
                    self.confirm_power = False
                    return 'cancel'
                return None
            if self.panel and x >= 708 and y <= 72:
                self.request_shutdown()
                return 'power'
            if self.locked:
                if start[0] <= 180 and start[1] <= 72 and x <= 180 and y <= 72 and duration >= 2:
                    self.locked = False
                    return 'unlock'
                if start[1] < 55 and y - start[1] > 70:
                    self.panel = True
                return None
            if start[1] < 55 and y - start[1] > 70:
                self.panel = True
                return 'open'
            if self.panel and start[1] - y > 70:
                self.panel = False
                return 'close'
            if not self.panel:
                if y < 64:
                    self.panel = True
                return None
            if 116 <= y <= 160 and 50 <= x <= 750:
                self.configure(brightness=max(5, min(100, round((x - 50) * 100 / 700))))
                return 'brightness'
            if 180 <= y <= 242:
                if x < 270:
                    self.configure(night_mode=not self.settings.night_mode)
                elif x < 535:
                    self.locked = True
                else:
                    self.notice = '수동 밝기 조절: 위 슬라이더를 사용하세요.'
                return 'toggle'
            if 258 <= y <= 320:
                if x < 270:
                    self.screen_off = True
                elif x < 535:
                    # Job adapter owns mounts; it already syncs + unmounts before SAFE.
                    self.notice = ('백업이 끝난 뒤 안전 분리됩니다.' if self.worker_active else
                                   '분리 가능' if self.state.get('safe_to_remove') else '분리 확인 전: 장치를 빼지 마세요.')
                else:
                    choices = (0, 30, 60, 120, 300, 600)
                    self.configure(screen_timeout=choices[(choices.index(self.settings.screen_timeout)+1) % len(choices)])
                return 'action'
            return None


def append_log(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as output:
        output.write(json.dumps(dict(time=time.time(), **state), ensure_ascii=True) + '\n')
        output.flush()
        os.fsync(output.fileno())


class FuturePowerLatch:
    """Extension interface only. No GPIO or actual supply cutoff is implemented."""
    def cut_power(self):
        raise NotImplementedError('Hardware power latch circuit is unconfirmed')
