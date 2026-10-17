"""MEBS 480x320 runtime UI. Pure read-only renderer; no mount, copy, eject or format operations.

Input contract: state is a dict containing `state` and optional total_bytes, copied_bytes,
verified_bytes, cpu_temp_c, ram_percent, uptime_seconds, detail, storage_name, sd_name.
The backup service alone is authoritative for VERIFIED and SAFE_TO_REMOVE transitions.
"""
from functools import lru_cache
from pathlib import Path
import os
import math
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 480, 320
BG = (5, 11, 18)
CARD = (13, 25, 37)
EDGE = (34, 58, 74)
TEXT = (232, 245, 251)
MUTED = (132, 163, 180)
CYAN = (54, 207, 239)
GREEN = (92, 222, 180)
AMBER = (250, 193, 91)
RED = (255, 109, 127)
STAGES = ("STORAGE", "SD", "COPY", "VERIFY", "EJECT")

# Explicitly distinguish verified from safe to remove. Unknown states fail closed.
PHASES = {
    "READY": ("BACKUP READY", "외장 저장장치를 연결하세요", 0, "waiting"),
    "WAITING_SOURCE": ("STORAGE READY", "SD 카드를 연결하세요", 1, "waiting"),
    "WAITING_TARGET": ("SD DETECTED", "외장 저장장치를 연결하세요", 0, "waiting"),
    "CONNECTED": ("SD READY", "백업 준비 중", 2, "active"),
    "MOUNTING": ("CHECKING MEDIA", "장치 확인 중", 2, "active"),
    "SCANNING": ("SCANNING FILES", "파일 및 용량 확인 중", 2, "active"),
    "COPYING": ("BACKING UP", "원본 SD는 변경하지 않습니다", 2, "active"),
    "VERIFYING": ("VERIFYING", "복사 데이터 검증 중", 3, "active"),
    "FINAL_CHECK": ("FINAL CHECK", "백업 무결성 재검증 중", 3, "active"),
    "COMPLETE": ("VERIFIED", "검증 완료 · 아직 분리 금지", 4, "verified"),
    "UNMOUNTING": ("FINALIZING", "안전 분리 확인 중", 4, "active"),
    "SAFE_TO_REMOVE": ("SAFE TO REMOVE", "안전 분리 확인 · 장치 분리 가능", 5, "safe"),
    "ERROR": ("BACKUP ERROR", "오류 발생 · SD 포맷 금지", 0, "error"),
    "CANCELLED": ("BACKUP STOPPED", "작업 중단 · 원본 보존", 0, "error"),
    "AMBIGUOUS": ("CHECK USB ORDER", "저장장치 연결 순서 확인", 0, "error"),
}

@lru_cache(maxsize=32)
def font(size, bold=False):
    names = [os.getenv("MEBS_FONT", "")]
    if bold:
        names += ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
    names += ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for name in names:
        if name and Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()

def _bounded(value, minimum, maximum):
    try:
        n = float(value)
        if not math.isfinite(n):
            return None
        return max(minimum, min(maximum, n))
    except (ValueError, TypeError, OverflowError):
        return None

def _progress(snapshot, state):
    """Byte progress only; never pretend verified or safely ejected from copied bytes."""
    if state not in ("COPYING", "VERIFYING", "FINAL_CHECK"):
        return None
    total = _bounded(snapshot.get("total_bytes"), 0, 1e30)
    if not total:
        return None
    key = "copied_bytes" if state == "COPYING" else "verified_bytes"
    value = _bounded(snapshot.get(key), 0, total)
    return round(100 * value / total) if value is not None else None

def _fit(draw, text, max_width, ft):
    s = str(text or "")
    if draw.textbbox((0, 0), s, font=ft)[2] <= max_width:
        return s
    while s and draw.textbbox((0, 0), s + "…", font=ft)[2] > max_width:
        s = s[:-1]
    return s + "…"

def render(snapshot):
    """Render immutable snapshot to 480x320 RGB Pillow Image; never performs I/O to drives."""
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    state = str(snapshot.get("state", "READY")).upper()
    title, subtitle, stage, mode = PHASES.get(state, ("UNKNOWN STATE", "시스템 상태 확인 필요", 0, "error"))
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    d.text((17, 10), "MEBS", font=font(23, True), fill=TEXT)
    d.text((97, 17), "AUTO BACKUP SYSTEM", font=font(10), fill=MUTED)
    # Read-only telemetry; missing readings are explicitly N/A.
    cpu = _bounded(snapshot.get("cpu_temp_c"), -40, 150)
    temp_color = RED if cpu is not None and cpu >= 80 else AMBER if cpu is not None and cpu >= 65 else CYAN
    d.arc((415, 6, 455, 46), 0, 359, fill=EDGE, width=4)
    if cpu is not None:
        d.arc((415, 6, 455, 46), -90, -90 + int(359 * max(0, min(cpu / 100, 1))), fill=temp_color, width=4)
    d.text((435, 15), "--" if cpu is None else f"{cpu:.0f}°", anchor="mt", font=font(11, True), fill=TEXT)
    d.text((435, 48), "CPU", anchor="mt", font=font(8), fill=MUTED)
    d.line((17, 61, 463, 61), fill=EDGE, width=1)
    uptime = _bounded(snapshot.get("uptime_seconds"), 0, 1e10)
    if uptime is None:
        up = "--"
    else:
        sec = int(uptime)
        up = f"{sec//86400}d {sec%86400//3600:02d}h" if sec >= 86400 else f"{sec//3600:02d}:{sec%3600//60:02d}"
    d.text((17, 68), f"UPTIME {up}", font=font(9), fill=MUTED)
    ram = _bounded(snapshot.get("ram_percent"), 0, 100)
    d.text((298, 68), f"RAM {'--' if ram is None else str(round(ram))+'%'}", font=font(9), fill=MUTED)
    d.rounded_rectangle((362, 73, 457, 78), radius=2, fill=EDGE)
    if ram is not None and ram > 0:
        d.rounded_rectangle((362, 73, 362 + round(95 * ram / 100), 78), radius=2, fill=CYAN)
    d.rounded_rectangle((12, 90, 468, 233), radius=13, fill=CARD, outline=EDGE, width=1)
    col = RED if mode == "error" else GREEN if mode in ("verified", "safe") else CYAN
    d.ellipse((28, 110, 37, 119), fill=col)
    d.text((47, 102), title, font=font(24, True), fill=TEXT)
    d.text((28, 144), _fit(d, subtitle, 421, font(13)), font=font(13), fill=MUTED)
    progress = _progress(snapshot, state)
    if progress is not None:
        d.rounded_rectangle((28, 177, 452, 190), radius=6, fill=EDGE)
        if progress > 0:
            d.rounded_rectangle((28, 177, 28 + round(424 * progress / 100), 190), radius=6, fill=CYAN)
        d.text((28, 199), f"{'COPY' if state=='COPYING' else 'VERIFY'} {progress}%", font=font(11, True), fill=CYAN)
    elif mode == "verified":
        d.text((28, 186), "VERIFIED  ≠  SAFE TO REMOVE", font=font(12, True), fill=AMBER)
    elif mode == "safe":
        d.text((28, 186), "✓  SAFE TO REMOVE", font=font(13, True), fill=GREEN)
    else:
        d.text((28, 186), _fit(d, snapshot.get("detail", "SYSTEM STANDBY"), 410, font(11)), font=font(11), fill=MUTED)
    # Distinct stages, no back button, no touch/format controls.
    for i, label in enumerate(STAGES):
        x = 17 + i * 91
        complete = i < stage
        active = i == stage and stage < 5
        color = GREEN if complete else CYAN if active else EDGE
        d.ellipse((x, 250, x+14, 264), fill=color)
        d.text((x+20, 250), label, font=font(9, True), fill=TEXT if complete or active else MUTED)
        if i < 4:
            d.line((x+69, 257, x+83, 257), fill=EDGE, width=2)
    d.line((17, 283, 463, 283), fill=EDGE, width=1)
    d.text((17, 291), "SOURCE SD: READ ONLY", font=font(9), fill=GREEN)
    d.text((463, 291), "480 × 320", anchor="ra", font=font(9), fill=MUTED)
    return img

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--state", default="READY", choices=sorted(PHASES))
    p.add_argument("--output", default="mebs-preview.png")
    args = p.parse_args()
    render({"state": args.state, "cpu_temp_c": 49, "ram_percent": 31,
            "uptime_seconds": 3671, "total_bytes": 100, "copied_bytes": 64,
            "verified_bytes": 45}).save(args.output)