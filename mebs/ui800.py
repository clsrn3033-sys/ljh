"""Additive 800x480 touch presentation retaining upstream palette and credits."""
from datetime import datetime
from functools import lru_cache
from PIL import Image, ImageDraw
from . import display
from .boot_animation import logo_mask

THEME = dict(display.DEFAULT_THEME, BG="#000000", PANEL="#08121b", EDGE="#213849", ORANGE="#58dfff", MUTED="#91a9c0")


@lru_cache(maxsize=1)
def logo():
    return logo_mask().resize((137, 28), Image.Resampling.LANCZOS)


def render(control, now=None):
    with control.lock:
        c = control
        if c.screen_off:
            return Image.new('RGB', (800, 480), 'black')
        image = display.render(c.state, theme=THEME)
        draw = ImageDraw.Draw(image)
        def text(x, y, value, size=16, color=THEME["WHITE"]):
            draw.text((x, y), str(value), fill=color, font=display.font(size), anchor='lt')
        draw.rectangle((0, 0, 799, 81), fill=THEME["BG"])
        try:
            image.paste(THEME["ORANGE"], (25, 23), logo())
        except (ValueError, OSError):
            # Upstream boot branch currently has a corrupt encoded logo mask.
            # Preserve the working main branch text logotype, do not alter mask.
            text(25, 20, 'MEBS', 32, THEME["ORANGE"])
        text(180, 31, 'MEBS  /  AUTO BACKUP', 12, THEME["MUTED"])
        cpu = 'N/A' if c.reading.cpu_c is None else f'{c.reading.cpu_c:.0f}°C'
        ram = 'N/A' if c.reading.ram_percent is None else f'{c.reading.ram_percent:.0f}%'
        battery = 'N/A' if c.reading.voltage is None else f'{c.reading.voltage:.2f}V'
        text(399, 32, f'CPU {cpu}  RAM {ram}  BAT {battery}', 12)
        text(616, 28, (now or datetime.now()).strftime('%H:%M'), 18)
        text(717, 28, '설정', 17, THEME["ORANGE"])
        draw.line((25, 78, 775, 78), fill=THEME["EDGE"])
        text(36, 216, 'SD READY' if c.state.get('source_connected') else 'SD WAIT', 11, THEME["GREEN"])
        text(428, 216, 'STORAGE READY' if c.state.get('target_connected') else 'STORAGE WAIT', 11, THEME["GREEN"])
        text(36, 410, f"파일 {c.state.get('verified_files', 0)}/{c.state.get('total_files', 0)}", 12, THEME["MUTED"])
        free = c.state.get('free_bytes')
        if free is not None:
            text(300, 410, '잔여 ' + display.amount(free), 12, THEME["MUTED"])
        if c.panel:
            draw.rectangle((0, 0, 799, 429), fill=THEME["PANEL"])
            text(25, 24, '2초 길게: 잠금 해제' if c.locked else '빠른 설정  /  위로 밀어 닫기', 17)
            draw.rounded_rectangle((708, 8, 792, 70), 10, fill=THEME["EDGE"])
            text(722, 27, '전원', 20, THEME["ORANGE"])
            value = lambda v, unit: 'N/A' if v is None else f'{v:.2f}{unit}'
            text(25, 82, f"CPU {cpu}  RAM {ram}  BAT {battery}  {value(c.reading.current_a, 'A')}  {value(c.reading.power_w, 'W')}  {c.reading.sensor_source}", 15)
            direction = 'CHARGING' if c.reading.current_a is not None and c.reading.current_a < -.01 else 'DISCHARGING' if c.reading.current_a is not None and c.reading.current_a > .01 else 'IDLE' if c.reading.current_a is not None else 'N/A'
            text(25, 106, ('STORAGE READY' if c.state.get('target_connected') else 'STORAGE WAIT') + '  /  ' + ('SD READY' if c.state.get('source_connected') else 'SD WAIT') + f'  /  {c.reading.sensor_model} {direction}  /  {c.battery_status()}', 11, THEME["MUTED"])
            draw.rounded_rectangle((50, 124, 750, 150), 10, fill=THEME["EDGE"])
            end = 50 + int(c.settings.brightness * 7)
            draw.rounded_rectangle((50, 124, max(60, end), 150), 10, fill=THEME["ORANGE"])
            text(55, 157, f'밝기 {c.effective_brightness}%  ·  미연결 센서: N/A', 12, THEME["MUTED"])
            labels = [('야간 ' + ('ON' if c.settings.night_mode else 'OFF'), '터치 잠금', '수동 밝기'),
                      ('화면 끄기', '안전 제거', f'화면 대기 {c.settings.screen_timeout}s')]
            for row, items in enumerate(labels):
                y = 180 + row * 78
                for col, label in enumerate(items):
                    x = 20 + col * 260
                    draw.rounded_rectangle((x, y, x+240, y+62), 10, fill=THEME["EDGE"])
                    text(x+15, y+20, label, 17)
            status = c.state.get('state', 'READY')
            text(25, 345, f"{status}  ·  {c.state.get('copied_bytes', 0)} bytes  ·  {c.state.get('verified_files', 0)} files", 16)
            text(25, 380, (c.notice or c.reading.error or '설정창을 열어도 백업은 계속됩니다.')[:66], 14, THEME["ORANGE"])
        if c.locked and not c.panel:
            text(36, 85, '터치 잠금 · 상단 왼쪽 2초 길게 / 설정에서 전원 접근', 13, THEME["ORANGE"])
        if c.notice and not c.panel:
            draw.rectangle((24, 82, 780, 102), fill=THEME["BG"])
            text(30, 84, c.notice[:70], 13, THEME["RED"])
        if c.confirm_power:
            draw.rounded_rectangle((45, 143, 755, 348), 16, fill=THEME["PANEL"], outline=THEME["ORANGE"], width=2)
            text(75, 170, '백업 완료 후 종료하시겠습니까?' if c.worker_active else 'MEBS를 안전 종료하시겠습니까?', 26)
            text(75, 222, '운영체제 종료 후에도 배터리 전원은 별도입니다.', 17, THEME["MUTED"])
            for x, label in [(75, '취소'), (435, '종료 예약' if c.worker_active else '종료 확인')]:
                draw.rounded_rectangle((x, 270, x+290, 330), 8, fill=THEME["EDGE"])
                text(x+50, 288, label, 22)
        if c.state.get('demo'):
            text(337, 460, 'MOCK · 모의 화면', 12, THEME["ORANGE"])
        if c.screen_off:
            return Image.new('RGB', (800, 480), 'black')
        return image
