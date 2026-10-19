"""800x480 on-demand explorer overlay using the existing MEBS palette."""
from pathlib import Path
import time


from .display import amount
from .explorer_v3 import ExplorerError, VideoPreview
from .backup import BackupError


class ExplorerUI:
    def __init__(self, session):
        self.session = session
        self.browser = session.browser
        self.role = 'source' if 'source' in self.browser.roots else 'target'
        self.path = Path('.')
        self.sort = 'name'
        self.selected = None
        self.preview = None
        self.details = None
        self.notice = ''
        self.confirm = None
        self.page = 0
        self.filter = 'all'
        self.player = None
        self._entries = None
        self._entries_at = 0

    def entries(self):
        now = time.monotonic()
        if self._entries is None or now-self._entries_at > .5:
            items = self.browser.listdir(self.role, self.path, self.sort)
            if self.filter != 'all':
                items = [item for item in items if item['kind'] == 'directory' or item['kind'] == self.filter]
            self._entries = items
            self._entries_at = now
        return self._entries

    def selected_path(self):
        return str(self.path / self.selected) if self.selected else None

    def select(self, entry):
        self.stop_player()
        if entry['blocked']:
            self.notice = '링크 또는 다른 파일시스템은 열 수 없습니다'
            return
        self.selected, self.preview, self.details = entry['name'], None, None
        if entry['kind'] == 'directory':
            self.path /= entry['name']
            self.selected = None
            self.page = 0
            self._entries = None
            return
        selected = self.selected_path()
        for index, listed in enumerate(self.entries()):
            if listed['name'] == entry['name']:
                self.page = index // 6
                break
        self.details = self.browser.info(self.role, selected)
        try:
            if entry['kind'] == 'video':
                self.details.update(self.browser.probe_video(self.role, selected))
            if entry['kind'] in ('image', 'raw', 'video'):
                self.preview = self.browser.thumbnail(self.role, selected)
        except (ExplorerError, OSError, ValueError) as exc:
            self.notice = str(exc)

    def stop_player(self):
        if self.player:
            self.player.stop()
            self.player = None

    def action(self, name, *, confirm=False):
        if name == 'close':
            self.stop_player()
            try:
                self.session.close()
            except (BackupError, OSError) as exc:
                self.notice = '마운트 해제 실패: ' + str(exc)
                return 'error'
            return 'closed'
        if name == 'eject':
            self.stop_player()
            try:
                self.session.close()
            except (BackupError, OSError) as exc:
                self.notice = '안전 분리 실패: ' + str(exc)
                return 'error'
            return 'safe-eject'
        if name == 'back':
            self.stop_player()
            self.path = self.path.parent if self.path != Path('.') else Path('.')
            self.selected = self.preview = self.details = None
            self.page = 0
            self._entries = None
            return 'back'
        if name == 'sort':
            values = ('name', 'mtime', 'size')
            self.sort = values[(values.index(self.sort) + 1) % len(values)]
            self._entries = None
            return 'sort'
        if name in ('source', 'target'):
            self.stop_player()
            if name not in self.browser.roots:
                self.notice = '미디어 없음'
                return None
            self.role, self.path, self.selected = name, Path('.'), None
            self.preview = self.details = None
            self.page = 0
            self._entries = None
            return name
        if name in ('all', 'image', 'video', 'raw', 'directory'):
            self.filter = name
            self.page = 0
            self._entries = None
            return 'filter'
        selected = self.selected_path()
        if not selected:
            self.notice = '파일을 먼저 선택하세요'
            return None
        if name == 'play':
            if self.player:
                self.stop_player()
                return 'stop'
            if not self.details or not self.details.get('software_preview'):
                self.notice = '이 영상은 재생 제한: 정보와 썸네일만 표시'
                return 'unsupported'
            try:
                path = self.browser._path(self.role, selected)
                self.player = VideoPreview(path)
                self.player.start()
                self.notice = '30초 무음 소프트웨어 미리보기 · 가속 미검증'
                return 'play'
            except (ExplorerError, OSError) as exc:
                self.notice = str(exc)
                return 'error'
        if name == 'info':
            self.notice = str(self.details or self.browser.info(self.role, selected))[:90]
            return 'info'
        if not confirm:
            self.confirm = name
            return 'confirm'
        self.confirm = None
        try:
            if name == 'copy' and self.role == 'source':
                result = self.browser.copy_from_source(selected, confirm=True)
                self.notice = f"복사·SHA-256 확인 {amount(result['bytes'])}"
            elif name == 'move' and self.role == 'target':
                self.browser.move_target(selected, confirm=True)
                self.notice = 'MEBS_FILES/Archive 폴더로 이동 완료'
                self.selected = None
            elif name == 'delete' and self.role == 'target':
                self.browser.delete_target(selected, confirm=True)
                self.notice = '사용자 작업 영역 파일 삭제 완료'
                self.selected = None
            else:
                raise ExplorerError('원본 SD 수정 또는 이 작업은 지원하지 않습니다')
        except (ExplorerError, OSError) as exc:
            self.notice = str(exc)
            return 'error'
        self._entries = None
        return name

    def gesture(self, start, end, duration=0):
        x, y = end
        if self.confirm:
            if 230 <= x <= 400 and 315 <= y <= 375:
                self.confirm = None
                return 'cancel'
            if 430 <= x <= 600 and 315 <= y <= 375:
                return self.action(self.confirm, confirm=True)
            return None
        if y < 48 and x > 710:
            return self.action('close')
        if 58 <= y < 108 and x < 178:
            return self.action('source')
        if 111 <= y < 165 and x < 178:
            return self.action('target')
        if 218 <= y < 378 and x < 178:
            index = (y - 218) // 32
            filters = ('all', 'image', 'video', 'raw', 'directory')
            return self.action(filters[index]) if index < len(filters) else None
        if 58 <= y < 92 and x >= 184:
            return self.action('back' if x < 221 else 'sort' if x > 680 else 'back')
        if 120 <= y < 390 and 184 <= x < 520:
            if 184 <= start[0] < 520 and 120 <= start[1] < 390 and abs(y-start[1]) > 35:
                pages = max(1, (len(self.entries()) + 5)//6)
                self.page = max(0, min(pages-1, self.page + (1 if y < start[1] else -1)))
                return 'page'
            row = (y - 120) // 42
            items = self.entries()
            index = self.page * 6 + row
            if row < 6 and index < len(items):
                self.select(items[index])
                return 'select'
        if 145 <= y < 315 and x >= 530:
            return self.action('play')
        if 405 <= y <= 445 and x >= 184:
            index = min(6, (x - 184) // 86)
            return self.action(('back', 'play', 'info', 'copy', 'move', 'delete', 'eject')[index])
        return None
