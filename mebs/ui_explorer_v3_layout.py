"""MEBS V3 800x480 explorer presentation based on the supplied reference."""
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from .display import amount, font
from .explorer_v3 import ExplorerError
from .ui800 import THEME, logo


def render(ui):
    image = Image.new('RGB', (800, 480), '#020911')
    draw = ImageDraw.Draw(image)
    cyan, white, muted, panel, edge = ('#4bcff5', '#eef5ff', '#91a9c0', '#071624', '#1e3850')

    def text(x, y, value, size=12, color=white):
        draw.text((x, y), str(value), font=font(size), fill=color, anchor='lt')

    def box(coords, *, active=False, fill=panel):
        draw.rounded_rectangle(coords, radius=6, fill=fill, outline=cyan if active else edge, width=1)

    try:
        image.paste(cyan, (19, 12), logo())
    except (OSError, ValueError):
        text(19, 10, 'MEBS', 27, cyan)
    text(165, 20, '/  FILE EXPLORER', 12, muted)
    reading = ui.session.control.reading
    cpu = 'N/A' if reading.cpu_c is None else f'{reading.cpu_c:.0f}°C'
    ram = 'N/A' if reading.ram_percent is None else f'{reading.ram_percent:.0f}%'
    battery = 'N/A' if reading.voltage is None else f'{reading.voltage:.2f}V'
    text(396, 18, f'CPU {cpu}  RAM {ram}  BAT {battery}', 11, muted)
    text(649, 15, datetime.now().strftime('%H:%M'), 16)
    text(725, 17, '닫기 ×', 13, cyan)
    draw.line((15, 49, 785, 49), fill=cyan)

    box((15, 58, 177, 390))
    for role, y, title in (('source', 65, 'SD CARD'), ('target', 124, 'USB STORAGE')):
        present = role in ui.browser.roots
        selected = ui.role == role
        text(30, y, title + (' ●' if present else ' · 미디어 없음'), 13, cyan if selected else muted)
        if present:
            try:
                capacity = ui.browser.capacity(role)
                total, free = capacity['total'], capacity['free']
                box((30, y+23, 158, y+31), fill=edge)
                used = max(0, total - free)
                if total and used:
                    draw.rounded_rectangle((31, y+24, 31+max(1, int(126*used/total)), y+30), 3, fill=cyan)
                text(30, y+34, f'{amount(used)} / {amount(total)}', 10, muted)
            except OSError:
                text(30, y+34, '용량 확인 불가', 10, muted)
    draw.line((25, 191, 167, 191), fill=edge)
    for index, (name, title) in enumerate((('all', '▣  모든 파일'), ('image', '▧  사진'),
                                         ('video', '▤  동영상'), ('raw', '▧  RAW'), ('directory', '▣  폴더'))):
        y = 218 + index*32
        if ui.filter == name:
            box((23, y-3, 169, y+26), active=True, fill='#063557')
        text(32, y+3, title, 12, cyan if ui.filter == name else white)

    box((184, 58, 220, 92))
    text(195, 64, '〈', 18, cyan)
    box((226, 58, 679, 92))
    path = '/' if ui.path == Path('.') else '/' + str(ui.path)
    text(240, 67, '▣  ' + path[:44], 12, muted)
    box((685, 58, 788, 92))
    text(693, 68, '정렬 ' + ui.sort, 11, cyan)
    box((184, 100, 520, 393))
    text(198, 105, '이름', 11, muted)
    text(397, 105, '크기', 11, muted)
    text(459, 105, '수정', 11, muted)
    draw.line((193, 119, 511, 119), fill=edge)
    try:
        entries = ui.entries()
    except (ExplorerError, OSError, ValueError) as exc:
        ui.notice = str(exc)
        entries = []
    for row, item in enumerate(entries[ui.page*6:ui.page*6+6]):
        y = 123 + row*42
        if item['name'] == ui.selected:
            box((188, y-2, 516, y+37), active=True, fill='#063557')
        icon = '▣' if item['kind'] == 'directory' else '▤' if item['kind'] == 'video' else '▧' if item['kind'] in ('image', 'raw') else '□'
        text(199, y+6, icon, 15, cyan if not item['blocked'] else muted)
        name = item['name'] + ('/' if item['kind'] == 'directory' else '')
        text(224, y+8, name[:20] + ('…' if len(name) > 20 else ''), 11,
             muted if item['blocked'] else white)
        text(390, y+8, amount(item['size']) if item['kind'] != 'directory' else '--', 10, muted)
        text(452, y+8, datetime.fromtimestamp(item['mtime_ns']/1e9).strftime('%m-%d'), 10, muted)
        draw.line((193, y+39, 510, y+39), fill=edge)
    if not entries:
        text(255, 230, '미디어 없음' if ui.role not in ui.browser.roots else '파일 없음', 17, muted)
    if len(entries) > 6:
        text(431, 376, f'{ui.page+1}/{(len(entries)+5)//6}', 10, muted)

    box((526, 100, 788, 393))
    box((533, 107, 781, 255), fill='#020911')
    picture = ui.player.image() if ui.player else None
    if picture is None:
        picture = ui.preview
    if picture:
        thumb = picture.copy()
        thumb.thumbnail((244, 143))
        image.paste(thumb, (535+(244-thumb.width)//2, 109+(143-thumb.height)//2))
    else:
        text(590, 170, '미리보기 없음', 14, muted)
    if ui.details and ui.details.get('kind') == 'video':
        text(543, 236, '▶  재생 / 정지', 11, cyan)
    if ui.details:
        detail = ui.details
        text(539, 263, detail['name'][:26], 13)
        text(539, 286, f"{detail['kind']} · {amount(detail['size'])}", 11, muted)
        if detail.get('codec'):
            text(539, 308, f"{detail['codec']}  {detail.get('width')}×{detail.get('height')}", 11)
            text(539, 328, f"{detail.get('pix_fmt')}  {detail.get('bit_depth') or '?'}bit  {detail.get('frame_rate')}", 10, muted)
            text(539, 348, 'SW 무음 미리보기' if detail.get('software_preview') else '재생 제한 · 정보만 표시', 10, cyan)
        elif detail['kind'] == 'raw' and not ui.preview:
            text(539, 308, 'RAW 미리보기 불가 · 정보 표시', 10, muted)
    else:
        text(539, 270, '파일을 선택하세요', 12, muted)

    for index, caption in enumerate(('뒤로', '재생', '정보', '복사', '이동', '삭제', '분리')):
        x = 184 + index*86
        box((x, 405, x+81, 441), active=caption == '분리')
        text(x+17, 415, caption, 12, cyan if caption == '분리' else white)
    text(18, 450, (ui.notice or '원본 SD 읽기 전용 · 기존 백업 보호')[:72], 10, cyan if ui.notice else muted)
    draw.line((15, 463, 785, 463), fill=edge)
    text(17, 465, 'MEBS / AUTO BACKUP SYSTEM V3', 9, muted)
    if getattr(ui.session.control, 'state', {}).get('demo'):
        text(277, 465, 'SIMULATION · 가상 미디어', 9, cyan)
    text(562, 465, 'Produced by 이정헌  |  제49기 보도부 이정헌', 9, muted)
    if ui.confirm:
        box((200, 205, 610, 390), active=True, fill='#071624')
        text(237, 235, f'{ui.confirm} 작업을 실행할까요?', 19)
        text(237, 275, '원본 SD·기존 백업은 수정 불가', 12, muted)
        box((230, 315, 400, 375))
        box((430, 315, 600, 375), active=True)
        text(288, 333, '취소', 16)
        text(485, 333, '확인', 16, cyan)
    return image
