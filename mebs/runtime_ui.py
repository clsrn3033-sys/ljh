"""MEBS runtime screen: lightweight read-only Pillow renderer for Raspberry Pi 4.

Input is the appliance's existing state dictionary. This module NEVER operates
on drives or changes backup state; only the service reports successful eject.
"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 720
BG = (5, 9, 15)
PANEL = (12, 20, 31)
EDGE = (39, 62, 84)
WHITE = (242, 248, 255)
MUTED = (145, 170, 196)
CYAN = (76, 218, 248)
GREEN = (97, 224, 186)
RED = (255, 119, 134)


@lru_cache(maxsize=32)
def font(size):
    paths = [os.environ.get("MEBS_FONT", ""),
             "/usr/share/fonts/mebs/NotoSansCJK-Regular.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
             "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc"]
    for path in paths:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError("MEBS needs a locally installed Korean font")


PHASES = {
    "READY": ("BACKUP READY", "외장 저장장치를 먼저 연결해 주세요.", "WAITING FOR STORAGE"),
    "WAITING_SOURCE": ("STORAGE READY", "외장 저장장치 준비됨 · 카메라 SD카드를 연결해 주세요.", "WAITING FOR SD CARD"),
    "WAITING_TARGET": ("SD DETECTED", "백업을 저장할 외장 저장장치를 연결해 주세요.", "WAITING FOR STORAGE"),
    "CONNECTED": ("SD READY", "두 장치를 연결했습니다. 백업을 준비합니다.", "MEDIA CONNECTED"),
    "MOUNTING": ("CHECKING MEDIA", "원본 카드의 읽기 전용 상태를 확인합니다.", "MOUNTING"),
    "SCANNING": ("SCANNING FILES", "파일 목록과 전체 용량을 확인합니다.", "SCANNING"),
    "COPYING": ("BACKING UP", "원본을 보존하며 파일을 복사하고 있습니다.", "COPYING"),
    "VERIFYING": ("VERIFYING DATA", "파일별 SHA-256을 검사하고 있습니다.", "VERIFYING"),
    "FINAL_CHECK": ("FINAL CHECK", "백업 결과 전체의 무결성을 재검증합니다.", "FINAL VERIFICATION"),
    "UNMOUNTING": ("FINALIZING", "저장장치 기록을 종료하고 안전 분리를 확인합니다.", "DISCONNECT PENDING"),
    "COMPLETE": ("VERIFIED", "백업 데이터 검증 완료 · 안전 분리는 아직입니다.", "DO NOT REMOVE"),
    "SAFE_TO_REMOVE": ("BACKUP COMPLETE", "검증과 안전 분리가 끝났습니다. 이제 장치를 분리해도 됩니다.", "SAFE TO REMOVE"),
    "ERROR": ("BACKUP ERROR", "백업이 실패했습니다. 원본 SD카드를 포맷하지 마세요.", "ACTION REQUIRED"),
    "CANCELLED": ("BACKUP STOPPED", "작업이 중단되었습니다. 원본을 보존합니다.", "CANCELLED"),
    "AMBIGUOUS": ("CHECK USB ORDER", "모든 장치를 분리한 뒤 외장 저장장치부터 연결하세요.", "CONNECTION ERROR")
}


def phase_info(state):
    return PHASES.get(state, ("SYSTEM STATUS", "시스템 상태를 확인하고 있습니다.", "STANDBY"))


def copy_progress(state):
    """Percentage is byte-copy progress, NOT a fabricated end-to-end percentage."""
    phase = state.get("state", "READY")
    total = state.get("total_bytes")
    if not isinstance(total, (int, float)) or isinstance(total, bool) or total <= 0:
        return 100 if phase in ("COMPLETE", "SAFE_TO_REMOVE") else None
    copied = state.get("copied_bytes", 0)
    if not isinstance(copied, (int, float)) or isinstance(copied, bool):
        copied = 0
    return max(0, min(100, int(copied * 100 / total)))


def bytes_text(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return "--"
    for unit, name in ((1024 ** 3, "GB"), (1024 ** 2, "MB"), (1024, "KB")):
        if value >= unit:
            return f"{value / unit:.1f} {name}"
    return f"{int(value)} B"


def text(draw, xy, value, size, color=WHITE, anchor="lt", width=None):
    value = str(value)
    ft = font(size)
    if width:
        while value and draw.textlength(value, font=ft) > width:
            value = value[:-2] + "…" if not value.endswith("…") else value[:-2] + "…"
    draw.text(xy, value, font=ft, fill=color, anchor=anchor)


def media(draw, x, index, name, label, connected):
    y, w, h = 307, 557, 137
    draw.rounded_rectangle((x, y, x+w, y+h), radius=18, fill=PANEL, outline=EDGE, width=2)
    draw.rounded_rectangle((x+20, y+20, x+72, y+72), radius=12, fill=(20, 40, 57))
    if index == "01":
        draw.rounded_rectangle((x+32,y+36,x+62,y+58),radius=4,outline=CYAN,width=3)
        draw.ellipse((x+53,y+52,x+57,y+56),fill=CYAN)
    else:
        draw.polygon([(x+34,y+35),(x+53,y+35),(x+62,y+44),(x+62,y+61),(x+32,y+61),(x+32,y+38)],outline=CYAN)
        for dx in (40,46,52):
            draw.line((x+dx,y+39,x+dx,y+48), fill=CYAN, width=2)
    text(draw,(x+87,y+24),f"MEDIA {index}  /  {name}",16,MUTED)
    text(draw,(x+26,y+89),label,22,WHITE,width=385)
    indicator = GREEN if connected else MUTED
    draw.ellipse((x+w-35,y+38,x+w-22,y+51),fill=indicator)
    text(draw,(x+w-24,y+98),"연결됨" if connected else "대기 중",19,indicator,"rt")


def bar(draw, x, y, width, percent, color):
    draw.rounded_rectangle((x,y,x+width,y+22),radius=11,fill=(17,31,45),outline=(79,110,137),width=2)
    if percent is None or percent <= 0:
        return
    filled = max(3, min(width-6, round((width-6)*percent/100)))
    initial = (12,129,239) if color == CYAN else color
    for offset in range(filled):
        ratio = offset/max(1,width-6)
        rgb = tuple(round(a+(b-a)*ratio) for a,b in zip(initial,color))
        draw.line((x+3+offset,y+4,x+3+offset,y+18),fill=rgb)
    draw.ellipse((x+3,y+4,x+18,y+18),fill=initial)
    if filled >= 16:
        draw.ellipse((x+filled-12,y+4,x+filled+3,y+18),fill=color)


def render(state, size=(WIDTH,HEIGHT)):
    """No disk access, mount, format, command execution or network calls."""
    if not isinstance(state,dict):
        raise TypeError("state must be a mapping")
    phase = state.get("state","READY")
    title, subtitle, tag = phase_info(phase)
    safe = phase == "SAFE_TO_REMOVE" and state.get("safe_to_remove") is True
    if phase == "SAFE_TO_REMOVE" and not safe:
        title,subtitle,tag = phase_info("UNMOUNTING")
    failed = phase in ("ERROR","CANCELLED","AMBIGUOUS")
    accent = RED if failed else GREEN if safe else CYAN
    image = Image.new("RGB",(WIDTH,HEIGHT),BG)
    d = ImageDraw.Draw(image)
    d.line((0,0,WIDTH,0),fill=(12,42,68),width=2)
    d.rounded_rectangle((55,36,216,86),radius=12,fill=(14,28,41))
    try:
        from .boot_animation import logo_mask
        logo = logo_mask().resize((152,31),Image.Resampling.LANCZOS)
        image.paste((247,249,252),(60,45),logo)
    except (ImportError, RuntimeError, ValueError, OSError):
        text(d,(65,42),"MEBS",33)
    text(d,(245,47),"AUTO BACKUP SYSTEM",18,(154,185,216))
    badge = "DEMO / PREVIEW" if state.get("demo") else "LIVE STATUS"
    d.rounded_rectangle((1027,42,1223,81),radius=19,fill=(18,30,42),outline=EDGE)
    d.ellipse((1045,58,1054,67),fill=accent)
    text(d,(1065,48),badge,17,accent)
    d.line((57,106,1223,106),fill=EDGE,width=2)

    text(d,(61,128),"01   /   SYSTEM STATUS",18,accent)
    text(d,(58,166),title,58,WHITE,width=1125)
    text(d,(61,245),subtitle,23,MUTED,width=1120)
    media(d,58,"01","EXTERNAL STORAGE",state.get("target_label") or "외장 저장장치",
          bool(state.get("target_connected",False)))
    media(d,665,"02","CAMERA SD CARD",state.get("source_label") or "카메라 SD카드",
          bool(state.get("source_connected",False)))

    d.rounded_rectangle((58,466,1222,643),radius=19,fill=PANEL,outline=EDGE,width=2)
    text(d,(87,489),"02   /   COPY PROGRESS  ·  VERIFICATION IS SEPARATE",16,MUTED)
    text(d,(88,535),tag,20,accent,width=790)
    percent=copy_progress(state)
    text(d,(1187,516),f"{percent}%" if percent is not None else "--%",42,accent if percent is not None else MUTED,"rt")
    if failed:
        detail=state.get("error") or "문제를 확인하고 두 장치를 다시 연결하세요."
    elif phase in ("COPYING","VERIFYING","FINAL_CHECK"):
        detail=state.get("current_file") or "파일을 복사하고 SHA-256 무결성을 확인합니다."
    else:
        detail="원본 자동 삭제·포맷 없음  ·  검증 완료와 안전 분리는 별도 단계"
    if phase == "SAFE_TO_REMOVE" and not safe:
        detail="분리 가능 신호 확인 전에는 장치를 제거하지 마세요."
    text(d,(88,574),detail,16,RED if failed else MUTED,width=1070)
    bar(d,88,612,1099,percent,accent)
    total=state.get("total_bytes",0)
    copied=state.get("copied_bytes",0)
    footer=(f"COPIED  {bytes_text(copied)} / {bytes_text(total)}"
            if isinstance(total,(int,float)) and total>0 else "USB DEVICE MONITORING")
    checked=state.get("verified_files",0)
    if isinstance(checked,int) and checked>0:
        footer+=f"   ·   SHA-256 {checked} files"
    text(d,(60,678),footer,16,MUTED,width=800)
    text(d,(1222,678),"제49기 보도부 이정헌   /   Produced by 이정원",16,(109,134,160),"rt")
    if len(size)!=2 or min(size)<1:
        raise ValueError("size must be positive (width,height)")
    if tuple(size)!=(WIDTH,HEIGHT):
        return image.resize(size,Image.Resampling.LANCZOS)
    return image


def png(state,size=(WIDTH,HEIGHT)):
    result=BytesIO()
    render(state,size).save(result,format="PNG")
    return result.getvalue()
