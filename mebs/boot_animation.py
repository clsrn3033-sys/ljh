"""MEBS boot splash for Pi4 Buildroot fbdev; independent of backup UI.

Uses the user's approved MEBS logo as a compact 1-bit mask embedded in source.
Does not read, format, mount, or modify USB/SD media. Missing USB/SD is normal.
"""
import argparse
import base64
import importlib
import json
from functools import lru_cache
import os
from pathlib import Path
import shutil
import sys
import time
import zlib

from PIL import Image, ImageDraw, ImageFont, ImageFilter

SIZE = (1280, 720)
LOGO_SIZE = (650, 132)
# 1-bit mask from the user's supplied 1536x1024 splash reference.
# Cropped to the white MEBS logotype and zlib/base85 compressed.
LOGO_MASK = "c-rmSU9P1l5CC8d>G<dpSc*&2q&H?V8!?#;FzJUOX(Dq~{)#H0JeRi~U+y_x&!-~APl*u!Z#}ljIk&-G!`CizeVSditzyZ(*>t?jj}k(`|Av#;@F8s*5dAqz(2EX=a}bxB_;t<qrt+PK|Gok-+|=NzqRtLS;#L;pC60CRxDSU%SugISsOqA>GewFz7iAEahPdPUa6T^uo?E;PTNV%@YFv!xJ}gdN99p6k`0)i1RLHPLw!{P1#<L_;_Sm2}wnT@c;H)*ul~sK9;?xvZszMOrlGlQ&xS>aVo<zAaXo5I5#T{3%c-31Ggr~SPMO_j1B4qd?e*8$3L3B;gpz4@{R~I4k^{=5V;!2xD(@8W@v_%kp?T~HpKw+RMQS}jzB4l`?LxHuYD8l0SO>u=G!xnK^hg};C8K$_F;!21^5T|d7d(oeB#TmDl3U<CpB(^0h@Ff#LR~keEL#8cGNjyYVoS34#3t}$&y(rqZ;*g3~lj8Aoh9^-ZaVJFwLxv$PTyc3XZnU_*73Y??!O>s`aR)*8N?d7C!$EaFaqK6W?xF=D)8ok;<Ov$$$`EJwriNEV*I!)oka;CO#I-+@b8p%nQEAP*IIzXx79U#Ne`6S4$Ngrv;n}PdioaseT*v+5_A`fnk}DGbi9vIP%->}1x<b)qB7783yqLd85s$g?@P7@Wc3{>|iU%z!G$6gjB?QfNz)!Ad&`2tZbNF_Bkd#PFkK?owkIj;JT`VaYLfp~#F^q9_Ojew~v21Y@)SX=76t37kip2ctyoQmUA?eZI!xb`y6p1;Y!`YEA)6~-c=K8C-q7~G%J`=V7|4xb<77Zc#9DpAD0oOfjq_|>n$7zaCp|r@S{cO?TR7$Ay`mQx0<wc4(k9J2H9hf={e($s#B_4vVJ;Yg(=-bbOFYY)`5k-|!mb7RE9oHy75=0*~X^vTnM$oMp(J<fQm_)-D528W>aUbqmp+rrIPEgr36_FS^l(>`PN@W0V@xD6WU{K;libPUs_u^fGzBKvbE{HjMCR#t&qr~-593I50Ci+Y^U(`75s)Kk%%ls^gXK|#(>+*bb-{OyOX@j9gDPtPED^i?_JQHvH2uEf9B&BG$BJn~sN<!bi=yD6_)mi6fm)h~kh{F`g(JqR4{dV{!VPIJCqi1;@wYc>OSla|#Z==xU;Z&2m4{_7kV>;s{4a9YmShr@rFePaHaku!f7&L-C`qE-tY@`B;Q4g%27b-n3?Y#R-cG6cu=3$Lkf2O0SS!Jih6<4%~C;B&P0C*7D)tt@S}o78FP*w8e4&*%EaUN1iC3#UTz8`J$yJT?)K5-d>AiMU3Un7Y!cSS48=lxMkuTV&IjiDxwNCR&w7LhJhzF`|v?yzb}esk@4R3tZYj~9K#5cFK+0lBNt`%f%mq#C5n)o<BKaQZ3{$cL@u`9+B+PC28ekN!dh8CHWU@Hz50O+>x$T3p<$?lDq?dL37EAMSuRp+u5^iuP>4(%DK=N*oEJ1dWD99=W~`l=A2OP>*jm+OsC7zJab&D&S{^dPwAff3=5X4~HpHTkO3_d!ZHTfe;#E@i4_^QHAKl?_U;"
STAGES = (("kernel", 14, "Kernel ready"),
          ("usb", 34, "USB detection ready"),
          ("storage", 54, "Storage manager ready"),
          ("backup", 78, "Backup engine ready"),
          ("display", 100, "Display ready"))


@lru_cache(maxsize=12)
def font(size, bold=False):
    paths = [os.environ.get("MEBS_FONT", "")]
    if bold:
        paths = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"] + paths
    paths += [
        "/usr/share/fonts/mebs/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in paths:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError("MEBS font not found; set MEBS_FONT to a Korean font")


@lru_cache(maxsize=1)
def logo_asset():
    from .logo_asset import load
    return load(LOGO_MASK, LOGO_SIZE, font(116, True))


def logo_mask():
    return logo_asset().mask


def centered(draw, y, text, f, fill, spacing=0):
    if spacing:
        widths = [draw.textlength(ch, font=f) for ch in text]
        total = sum(widths) + spacing * (len(widths) - 1)
        x = (SIZE[0] - total) / 2
        for ch, width in zip(text, widths):
            draw.text((round(x), y), ch, font=f, fill=fill, anchor="lt")
            x += width + spacing
    else:
        draw.text((SIZE[0] / 2, y), text, font=f, fill=fill, anchor="mt")


def render(percent=0, *, opacity=1.0, state="boot", caption="Initializing system..."):
    """Render a 1280x720 RGB frame. No OS probes or side effects."""
    if not 0 <= percent <= 100 or not 0 <= opacity <= 1:
        raise ValueError("percent and opacity must be in range")
    image = Image.new("RGB", SIZE, "black")
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    asset = logo_asset()
    logo = asset.mask
    halo = logo.filter(ImageFilter.GaussianBlur(12)).point(lambda n: int(n * .2))
    tint = Image.new("RGBA", LOGO_SIZE, (118, 197, 255, 0))
    tint.putalpha(halo)
    overlay.alpha_composite(tint, (315, 148))
    tint = Image.new("RGBA", LOGO_SIZE, (246, 249, 254, 0))
    tint.putalpha(logo)
    overlay.alpha_composite(tint, (315, 148))
    d = ImageDraw.Draw(overlay)
    centered(d, 286, "AUTO BACKUP SYSTEM", font(31), (152, 180, 217, 255), spacing=7)
    d.line((320, 357, 960, 357), fill=(68, 98, 130, 255), width=1)
    d.line((465, 357, 815, 357), fill=(111, 190, 236, 180), width=2)
    centered(d, 390, "제49기 보도부 이정헌", font(35, True), (248, 249, 251, 255))
    centered(d, 442, "Produced by 이정헌", font(20), (129, 155, 189, 255), spacing=1)
    if asset.source == 'text-fallback':
        centered(d, 665, "TEXT LOGO FALLBACK / original asset pending", font(14), (160, 170, 190, 255))
    if state == "ready":
        centered(d, 515, "BACKUP READY", font(30), (230, 249, 255, 255), spacing=3)
        centered(d, 561, "Connect external storage to begin", font(16), (130, 174, 206, 255))
    elif state == "shutdown":
        centered(d, 535, "Shutting down safely...", font(24), (247, 249, 252, 255))
    else:
        label = "Initialization failed" if state == "error" else caption
        centered(d, 516, label, font(24), (255, 162, 156, 255) if state == "error" else (247, 249, 252, 255))
        left, top, right, bottom = 350, 577, 909, 598
        d.rounded_rectangle((left, top, right, bottom), radius=11,
                            fill=(14, 23, 32, 255), outline=(97, 126, 154, 255), width=2)
        filled = int((right - left - 4) * percent / 100)
        if filled:
            w = max(1, filled)
            gradient = Image.new("RGBA", (w, 17))
            px = gradient.load()
            for x in range(w):
                t = x / max(1, right - left)
                rgb = (round(0 + 103 * t), round(153 + 89 * t), round(245 + 8 * t), 255)
                for y in range(17):
                    px[x, y] = rgb
            mask = Image.new("L", (w, 17), 255)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, 16), radius=8, fill=255)
            overlay.paste(gradient, (left + 2, top + 2), mask)
        d = ImageDraw.Draw(overlay)
        d.text((928, 572), f"{percent}%", font=font(25), fill=(204, 225, 242, 255), anchor="lt")
        if state == "error":
            centered(d, 620, "Check boot log; original SD is untouched", font(16), (225, 129, 129, 255))
    if opacity < 1.0:
        a = overlay.getchannel("A").point(lambda n: round(n * opacity))
        overlay.putalpha(a)
    image.paste(overlay, (0, 0), overlay)
    return image


def checks(display_ready=True, root=Path("/")):
    """Actual dependency probes, not a timer; media presence is not required.

    Kernel inspection starts in userspace; no claims about earlier boot stages.
    """
    importlib.invalidate_caches()
    def bootable_backup():
        from mebs import appliance
        return callable(appliance.run) and callable(appliance.inventory)
    return (
        (root / "proc/self/stat").exists(),
        (root / "sys/bus/usb/devices").is_dir() and bool(shutil.which("lsblk")),
        (root / "proc/mounts").exists() and (root / "run").is_dir(),
        bootable_backup(),
        bool(display_ready),
    )


def easing(t):
    t = max(0., min(1., float(t)))
    return t * t * (3 - 2 * t)


def shutdown_frames(steps=8):
    """Fade the approved logo to black after storage has been safely flushed."""
    if steps < 1:
        raise ValueError("Expected a positive frame count")
    for n in range(steps + 1):
        yield 1.0 - easing(n / steps)


def frames(results, *, steps=5, delay_stage=None):
    """Yield (percent, opacity, state, caption) frames; stop on failure."""
    if len(results) != len(STAGES) or steps < 1:
        raise ValueError("Expected five stage results and a positive frame count")
    current = 0
    for t in range(1, steps + 1):
        yield 0, easing(t / steps), "boot", "Initializing system..."
    for (key, target, label), passed in zip(STAGES, results):
        if not passed:
            yield current, 1.0, "error", f"{label}: FAILED"
            return
        for t in range(1, steps + 1):
            value = current + (target - current) * easing(t / steps)
            yield min(100, round(value)), 1.0, "boot", f"{label}..."
        if delay_stage == key:
            for _ in range(steps * 2):
                yield target, 1.0, "boot", f"{label}: waiting..."
        current = target
    for _ in range(steps):
        yield 100, 1.0, "ready", "BACKUP READY"


def generate_preview(directory):
    """Offline GIF/PNG simulation; never presented as real boot evidence."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for case, result, delay in (
        ("success", [True] * 5, None),
        ("delay", [True] * 5, "storage"),
        ("error", [True, True, False, True, True], None),
    ):
        sequence = list(frames(result, steps=5, delay_stage=delay))
        imgs = [render(percent, opacity=o, state=state, caption=caption)
                for percent, o, state, caption in sequence]
        imgs[0].save(directory / f"boot-{case}.gif", save_all=True,
                     append_images=imgs[1:], duration=55, loop=0, optimize=False)
        imgs[-1].save(directory / f"boot-{case}.png")
    render(78).save(directory / "boot-78.png")
    manifest = {"simulation": True, "hardware_tested": False,
                "scenarios": ["success", "delay", "error"],
                "note": "These are offline visual simulations, not Raspberry Pi boot evidence."}
    (directory / "boot-preview.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def device_paths():
    from mebs.appliance import display_paths
    return display_paths("auto")


def run_fb(max_wait=0.45, fps=15):
    """Short splash; never waits for USB, SD or absent HDMI indefinitely."""
    from mebs.framebuffer import Framebuffer
    deadline = time.monotonic() + max_wait
    screen = None
    while screen is None:
        for dev in device_paths():
            try:
                screen = Framebuffer(dev)
                break
            except (OSError, ValueError):
                pass
        if screen is not None or time.monotonic() >= deadline:
            break
        time.sleep(.05)
    if screen is None:
        print(json.dumps({"boot_splash": "skipped", "reason": "No supported framebuffer within bounded wait"}), flush=True)
        return 0
    with screen:
        results = checks(True)
        begin = time.monotonic()
        for index, (percent, opacity, state, caption) in enumerate(frames(results, steps=3)):
            screen.show(render(percent, opacity=opacity, state=state, caption=caption))
            remaining = begin + (index + 1) / fps - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        print(json.dumps({"boot_splash": "done", "stages": dict(zip((s[0] for s in STAGES), results)),
                          "elapsed_seconds": round(time.monotonic() - begin, 3)}), flush=True)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="MEBS verified-stage boot splash (fbdev)")
    p.add_argument("--preview", metavar="DIR", help="Generate simulated GIF/PNG previews on a PC")
    p.add_argument("--max-wait", type=float, default=.45, help="Max wait for fbdev, seconds")
    args = p.parse_args(argv)
    if args.preview:
        print(json.dumps(generate_preview(args.preview), ensure_ascii=False))
        return 0
    if not 0 <= args.max_wait <= 3:
        p.error("--max-wait must be between 0 and 3 seconds")
    try:
        return run_fb(args.max_wait)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(json.dumps({"boot_splash": "failed", "error": str(exc)}), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
