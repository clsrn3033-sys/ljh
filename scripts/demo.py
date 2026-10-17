"""Run the built application against disposable fixtures, never real USB disks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mebs-demo-") as temp:
    base = Path(temp)
    source, target = base / "source", base / "target"
    (source / "카메라" / "empty").mkdir(parents=True)
    target.mkdir()
    (source / "카메라" / "clip.bin").write_bytes(bytes(range(256)) * 8192)
    (source / "카메라" / "clip.xml").write_text('<clip title="MEBS">메타데이터</clip>', encoding="utf-8")
    hashes = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob("*") if p.is_file()}
    command = [sys.executable, str(root / "dist" / "mebs.pyz")]
    subprocess.run(command + ["backup", "--source", str(source), "--target", str(target)], check=True)
    job, = target.glob("mebs-backup-*")
    subprocess.run(command + ["verify", str(job)], check=True)
    assert hashes == {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.rglob("*") if p.is_file()}
    assert (job / "data" / "카메라" / "empty").is_dir()
    print(json.dumps({"demo": "PASS", "source_unchanged": True, "xml_and_empty_directory": True}))
