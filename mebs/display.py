"""Render the same small display into a PNG without a desktop environment.

800x480 is a preview canvas, not an assertion about the final LCD specification.
Pillow and a locally installed Korean font are only needed for this module.
"""
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480
BG = "#0b111b"
PANEL = "#111d2c"
EDGE = "#243348"
WHITE = "#f0f4fa"
MUTED = "#95a4b8"
ORANGE = "#ff9d47"
GREEN = "#63dfac"
RED = "#ff7d7d"


@lru_cache(maxsize=1)
def font_path():
    configured = os.environ.get("MEBS_FONT")
    paths = [configured] if configured else [
        "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/mebs/NotoSansCJK-Regular.ttc",
    ]
    for name in paths:
        if name and Path(name).is_file():
            return name
    raise RuntimeError("한글 글꼴을 찾지 못했습니다. MEBS_FONT에 TTF/TTC/OTF 경로를 지정하세요.")


@lru_cache(maxsize=32)
def font(size):
    return ImageFont.truetype(font_path(), size)


def amount(size):
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.1f} GB"
    if size >= 1024 ** 2:
        return f"{size / 1024 ** 2:.1f} MB"
    return f"{size / 1024:.1f} KB"


def render(state):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=18, color=WHITE):
        draw.text((x, y), str(value), font=font(size), fill=color, anchor="lt")

    def right(x, y, value, size=18, color=WHITE):
        draw.text((x, y), str(value), font=font(size), fill=color, anchor="rt")

    def fit(value, size, width):
        value = str(value)
        if draw.textlength(value, font=font(size)) <= width:
            return value
        while value and draw.textlength(value + "…", font=font(size)) > width:
            value = value[:-1]
        return value + "…"

    phase = state.get("state", "READY")
    good = phase in ("COMPLETE", "SAFE_TO_REMOVE")
    error = phase in ("ERROR", "CANCELLED", "AMBIGUOUS")
    accent = GREEN if good else RED if error else ORANGE
    draw.rounded_rectangle((34, 29, 42, 63), radius=4, fill=ORANGE)
    text(55, 24, "MEBS", 34)
    text(187, 37, "AUTO BACKUP SYSTEM", 13, MUTED)
    draw.ellipse((620, 42, 628, 50), fill=accent)
    right(764, 36, "샘플 데이터 · DEMO" if state.get("demo") else "현장 백업 시스템", 15, MUTED)
    draw.line((36, 82, 764, 82), fill=EDGE)

    titles = {
        "READY": ("BACKUP READY", "백업을 저장할 외장 하드를 먼저 연결해 주세요."),
        "WAITING_SOURCE": ("외장 하드 연결됨", "두 번째로 카메라 SD카드를 연결해 주세요."),
        "AMBIGUOUS": ("연결 순서를 확인해 주세요", "두 장치를 빼고 외장 하드부터 다시 연결해 주세요."),
        "MOUNTING": ("저장장치 확인 중", "원본은 읽기 전용으로 연결합니다."),
        "UNMOUNTING": ("안전 분리 준비 중", "저장장치를 분리하지 말고 잠시 기다려 주세요."),
        "SAFE_TO_REMOVE": ("백업 완료 · 분리 가능", "두 USB 장치를 분리해도 됩니다. 원본을 보존했습니다."),
        "WAITING_TARGET": ("원본 카드 연결됨", "백업할 외장 저장장치를 연결해 주세요."),
        "CONNECTED": ("백업 준비 완료", "원본과 대상을 확인하고 백업을 시작합니다."),
        "SCANNING": ("원본 파일 확인 중", "폴더 구조와 백업할 파일을 확인하고 있습니다."),
        "COPYING": ("안전하게 백업 중", "백업이 끝날 때까지 저장장치를 연결해 두세요."),
        "VERIFYING": ("데이터 검증 중", "복사한 파일의 SHA-256을 확인하고 있습니다."),
        "FINAL_CHECK": ("최종 검증 중", "완료된 백업을 다시 읽어 무결성을 확인합니다."),
        "COMPLETE": ("백업 검증 완료", "원본 데이터를 보존했습니다. 안전 분리 절차가 필요합니다."),
        "ERROR": ("백업 확인 필요", "백업에 실패했습니다. 원본 카드를 지우지 마세요."),
        "CANCELLED": ("백업이 중단되었습니다", "완료되지 않은 작업입니다. 원본은 보존됩니다."),
    }
    title, subtitle = titles.get(phase, titles["SCANNING"])
    text(36, 104, "FIELD BACKUP  /  SHA-256", 12, accent)
    text(36, 132, title, 34)
    text(36, 185, subtitle, 18, MUTED)

    for x, role, label, connected in (
        (36, "SOURCE · 원본", state.get("source_label", "카메라 SD카드"), state.get("source_connected", False)),
        (428, "DESTINATION · 대상", state.get("target_label", "외장 저장장치"), state.get("target_connected", False)),
    ):
        draw.rounded_rectangle((x, 230, x + 336, 313), radius=12, fill=PANEL, outline=EDGE)
        text(x + 16, 243, role, 12, MUTED)
        text(x + 16, 269, fit(label, 21, 224), 21)
        draw.ellipse((x + 312, 246, x + 320, 254), fill=GREEN if connected else EDGE)
        right(x + 320, 276, "연결됨" if connected else "대기", 13, GREEN if connected else MUTED)
    draw.line((388, 271, 410, 271), fill=MUTED, width=2)
    draw.line((403, 265, 410, 271, 403, 277), fill=MUTED, width=2)

    total = state.get("total_bytes", 0)
    copied = state.get("copied_bytes", 0)
    percent = min(100, int(copied * 100 / total)) if total else (100 if good else 0)
    label = "SHA-256 일치" if good else "진행 중인 파일" if state.get("current_file") else "백업 상태"
    text(36, 334, label, 13, accent if good else MUTED)
    detail = state.get("error") or state.get("current_file") or (f"{state.get('verified_files', 0)}개 파일 검증 완료" if good else "원본 자동 삭제 없음")
    text(36, 356, fit(detail, 17, 520), 17)
    right(764, 333, f"{percent}%", 28, accent)
    if total:
        right(764, 369, f"{amount(copied)} / {amount(total)}", 12, MUTED)
    draw.rounded_rectangle((36, 395, 764, 401), radius=3, fill=EDGE)
    if percent:
        draw.rounded_rectangle((36, 395, 36 + max(6, 728 * percent // 100), 401), radius=3, fill=accent)
    text(36, 435, "제49기 보도부 이정헌", 15, MUTED)
    right(764, 435, "Produced by 이정원", 14, MUTED)
    return image


def png(state):
    out = BytesIO()
    render(state).save(out, format="PNG")
    return out.getvalue()
