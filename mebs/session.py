"""Presentation state for an explicitly selected, mounted directory pair.

The appliance USB/mount adapter is intentionally separate: this class neither
mounts disks nor claims they have been unmounted after verification.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event

from .backup import BackupError, Cancelled, backup, verify


@dataclass
class ViewState:
    state: str = "READY"
    source_connected: bool = False
    target_connected: bool = False
    source_label: str = "카메라 SD카드"
    target_label: str = "외장 저장장치"
    copied_bytes: int = 0
    total_bytes: int = 0
    verified_files: int = 0
    total_files: int = 0
    current_file: str = ""
    error: str = ""
    job: str = ""
    safe_to_remove: bool = False


class BackupSession:
    """A single backup job. Callers must explicitly select the two directories."""
    def __init__(self, on_state=lambda state: None, target_first=False):
        self.view = ViewState()
        self.on_state = on_state
        self.source = None
        self.target = None
        self.cancelled = Event()
        self.running = False
        self.target_first = target_first

    def publish(self):
        self.on_state(asdict(self.view))

    def attach_source(self, path):
        expected = "WAITING_SOURCE" if self.target_first else "READY"
        if self.running or self.source is not None or self.view.state != expected:
            raise BackupError("원본은 새 작업의 첫 번째 장치로 지정해야 합니다.")
        source = Path(path).resolve(strict=True)
        if not source.is_dir():
            raise BackupError("원본 디렉터리를 찾을 수 없습니다.")
        if self.target is not None and (source == self.target or source in self.target.parents or self.target in source.parents):
            raise BackupError("원본과 대상은 서로 다른 독립 디렉터리여야 합니다.")
        self.source = source
        self.view.source_connected = True
        self.view.state = "CONNECTED" if self.target_first else "WAITING_TARGET"
        self.publish()

    def attach_target(self, path):
        if self.running or (self.source is None and not self.target_first) or self.target is not None:
            raise BackupError("원본 연결 후 대상을 지정해야 합니다.")
        target = Path(path).resolve(strict=True)
        if not target.is_dir():
            raise BackupError("대상 디렉터리를 찾을 수 없습니다.")
        if self.source is not None and (target == self.source or target in self.source.parents or self.source in target.parents):
            raise BackupError("원본과 대상은 서로 다른 독립 디렉터리여야 합니다.")
        self.target = target
        self.view.target_connected = True
        self.view.state = "WAITING_SOURCE" if self.target_first else "CONNECTED"
        self.publish()

    def cancel(self):
        self.cancelled.set()

    def _event(self, event):
        state = event["state"]
        if state == "SCANNED":
            self.view.total_bytes = event["total_bytes"]
            self.view.total_files = event["total_files"]
        elif state == "FILE_VERIFIED":
            self.view.verified_files = event["verified_files"]
        elif state == "VERIFIED":
            # The engine's commit is followed by a separate full verification.
            self.view.state = "FINAL_CHECK"
        else:
            self.view.state = state
        self.view.current_file = event.get("path", self.view.current_file)
        self.view.copied_bytes = event.get("bytes", self.view.copied_bytes)
        self.view.total_bytes = event.get("total_bytes", self.view.total_bytes)
        self.publish()

    def run(self):
        if self.running or self.view.state != "CONNECTED":
            raise BackupError("원본과 대상 연결을 확인한 뒤 시작해야 합니다.")
        self.running = True
        try:
            job = backup(self.source, self.target, self._event, self.cancelled.is_set)
            self.view.job = str(job)
            manifest = verify(job, cancel=self.cancelled.is_set)
            self.view.state = "COMPLETE"
            self.view.total_files = self.view.verified_files = len(manifest["files"])
            self.view.total_bytes = self.view.copied_bytes = manifest["bytes"]
            self.view.current_file = ""
        except Cancelled as exc:
            self.view.state = "CANCELLED"
            self.view.error = str(exc)
        except (BackupError, OSError, ValueError, KeyError, TypeError) as exc:
            self.view.state = "ERROR"
            self.view.error = str(exc)
        finally:
            self.running = False
            self.publish()
        return asdict(self.view)

