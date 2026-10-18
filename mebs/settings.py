"""Versioned settings on the OS-owned writable partition, never USB media."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class Settings:
    brightness: int = 70
    night_mode: bool = False
    screen_timeout: int = 120

    def __post_init__(self):
        if type(self.brightness) is not int or not 5 <= self.brightness <= 100:
            raise ValueError('brightness must be 5..100')
        if type(self.screen_timeout) is not int or self.screen_timeout not in (0, 30, 60, 120, 300, 600):
            raise ValueError('invalid screen timeout')
        if type(self.night_mode) is not bool:
            raise ValueError('night mode must be boolean')


class SettingsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.error = ''

    def load(self):
        try:
            value = json.loads(self.path.read_text())
            version = value.pop('version')
            if type(version) is not int or version not in (1, 2):
                raise ValueError('unsupported settings version')
            # V1 used an ambient-light option that is absent from V2 hardware.
            if version == 1:
                value.pop('auto_brightness', None)
            return Settings(**value)
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.error = '설정 읽기 실패: ' + str(exc)
            return Settings()

    def save(self, settings):
        payload = json.dumps(dict(version=2, **asdict(settings))) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix='.settings-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_DIRECTORY | os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)
