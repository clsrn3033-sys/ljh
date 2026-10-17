"""Build a dependency-free Python zip application from this local source tree."""
from pathlib import Path
import shutil
import tempfile
import zipapp

root = Path(__file__).resolve().parents[1]
out = root / "dist"
out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="mebs-build-") as temp:
    stage = Path(temp)
    shutil.copytree(root / "mebs", stage / "mebs", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (stage / "__main__.py").write_text("from mebs.__main__ import main\nraise SystemExit(main())\n")
    zipapp.create_archive(stage, out / "mebs.pyz", interpreter="/usr/bin/env python3")
print(out / "mebs.pyz")
