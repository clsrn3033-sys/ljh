"""Run real isolated backup scenarios and export an offline visual replay."""
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import tempfile

from .backup import verify
from .session import BackupSession


def fixtures(base):
    source, target = base / "camera-sd", base / "external-storage"
    camera = source / "PRIVATE" / "M4ROOT" / "CLIP"
    camera.mkdir(parents=True)
    (source / "DCIM" / "empty").mkdir(parents=True)
    target.mkdir()
    # Deterministic sample bytes, not an actual encoded movie or user footage.
    (camera / "C0001.MP4").write_bytes(bytes(range(256)) * 32768)
    (camera / "C0001M01.XML").write_text('<Clip title="MEBS 현장 촬영" id="C0001"/>', encoding="utf-8")
    (camera / "C0002.MP4").write_bytes(bytes(reversed(range(256))) * 16384)
    (source / "촬영 메모.txt").write_text("MEBS 검증용 샘플 데이터\n원본 자동 삭제 없음\n", encoding="utf-8")
    return source, target


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def scenario(kind, on_state=lambda state: None):
    if kind not in ("success", "corruption", "cancel"):
        raise ValueError("Unknown preview scenario")
    states = []
    with tempfile.TemporaryDirectory(prefix="mebs-visual-") as temp:
        source, target = fixtures(Path(temp))
        original = tree_hashes(source)
        injected = False

        def observe(state):
            nonlocal injected
            public = dict(state)
            public["demo"] = True
            public["job"] = Path(public["job"]).name if public["job"] else ""
            states.append(public)
            on_state(public)
            if kind == "corruption" and state["state"] == "VERIFYING" and not injected:
                pending, = target.glob(".mebs-pending-*")
                (pending / "data" / state["current_file"]).write_bytes(b"INTENTIONALLY CORRUPTED DEMO COPY")
                injected = True
            if kind == "cancel" and state["state"] == "COPYING" and not injected:
                session.cancel()
                injected = True

        session = BackupSession(observe, target_first=True)
        session.publish()
        session.attach_target(target)
        session.attach_source(source)
        result = session.run()
        jobs = list(target.glob("mebs-backup-*"))
        unchanged = tree_hashes(source) == original
        assert unchanged, "Preview source was modified"
        manifest = None
        if kind == "success":
            assert result["state"] == "COMPLETE", result
            assert len(jobs) == 1
            manifest = verify(jobs[0])
            assert tree_hashes(jobs[0] / "data") == original
            assert (jobs[0] / "data" / "DCIM" / "empty").is_dir()
        else:
            assert result["state"] == ("ERROR" if kind == "corruption" else "CANCELLED"), result
            assert not jobs, "Failed job was published as complete"
        return {"kind": kind, "states": states, "final_state": result["state"],
                "source_unchanged": unchanged, "published_jobs": len(jobs),
                "source_hashes": original, "manifest": manifest,
                "hardware_tested": False, "safe_to_remove": False}


def create_preview(output):
    from .display import png, render

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "evidence"
    evidence.mkdir(exist_ok=True)
    cases = []
    for kind in ("success", "corruption", "cancel"):
        result = scenario(kind)
        (evidence / f"{kind}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        frames = []
        previous = None
        for state in result["states"]:
            # Retain phase changes, 10% copy steps and verification-count updates.
            total = state["total_bytes"]
            bucket = int(state["copied_bytes"] * 10 / total) if total else 0
            key = (state["state"], bucket, state["verified_files"], state["current_file"])
            if key == previous:
                continue
            previous = key
            frames.append({"state": state, "image": "data:image/png;base64," + base64.b64encode(png(state)).decode()})
        cases.append({"kind": kind, "frames": frames, "source_unchanged": result["source_unchanged"],
                      "published_jobs": result["published_jobs"], "final_state": result["final_state"],
                      "manifest": result["manifest"]})
        filename = {"success": "complete.png", "corruption": "error.png", "cancel": "cancelled.png"}[kind]
        (output / filename).write_bytes(png(result["states"][-1]))
        if kind == "success":
            (output / "ready.png").write_bytes(png(result["states"][0]))
            phases = ("READY", "WAITING_SOURCE", "CONNECTED", "COPYING", "VERIFYING", "COMPLETE")
            selected = [next(s for s in result["states"] if s["state"] == phase) for phase in phases]
            images = [render(s) for s in selected]
            images[0].save(output / "demo.gif", save_all=True, append_images=images[1:],
                           duration=1800, loop=0)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "cases": cases}
    template = files("mebs").joinpath("ui/preview.html").read_text(encoding="utf-8")
    embedded = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    (output / "index.html").write_text(template.replace("__MEBS_TRACE_JSON__", embedded), encoding="utf-8")
    print(json.dumps({"preview": str(output / "index.html"), "cases": 3,
                      "source_unchanged": True, "hardware_tested": False}, ensure_ascii=False))
    return output / "index.html"
