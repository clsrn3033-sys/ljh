import argparse
import json
import signal
import subprocess
import sys
import time

from . import __version__
from .backup import BackupError, backup, verify
from .devices import Roles, usb_disks


def main():
    parser = argparse.ArgumentParser(description="MEBS Auto Backup System — explicit directory backup")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ready", help="Display provisional branding and engine readiness")
    commands.add_parser("devices", help="Read-only USB disk inventory using lsblk")
    commands.add_parser("watch", help="Observe USB insertion order; never mount or copy automatically")
    preview = commands.add_parser("preview", help="Run sample backups and export a visual offline replay")
    preview.add_argument("--output", default="preview", help="Generated preview directory")
    display = commands.add_parser("display-demo", help="Run sample backups on an explicit Linux framebuffer")
    display.add_argument("--device", default="/dev/fb0")
    display.add_argument("--case", choices=("success", "corruption", "cancel"), default="success")
    appliance = commands.add_parser("appliance", help="Dedicated-image USB backup service; mounts real disks")
    appliance.add_argument("--device", default="auto")
    copy = commands.add_parser("backup", help="Copy explicitly selected source to destination directory")
    copy.add_argument("--source", required=True)
    copy.add_argument("--target", required=True)
    check = commands.add_parser("verify", help="Read and recheck a completed job")
    check.add_argument("job")
    args = parser.parse_args()
    cancelled = False

    def stop(signum, frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def emit(event):
        print(json.dumps(event, ensure_ascii=True), flush=True)

    try:
        if args.command == "ready":
            print("MEBS\n제49기 보도부 이정헌\nProduced by 이정헌\nBACKUP READY")
            print("Directory engine only; automatic USB/LCD/GPIO not enabled.")
        elif args.command == "devices":
            emit({"devices": usb_disks()})
        elif args.command == "watch":
            roles = Roles()
            previous = None
            while not cancelled:
                disks = usb_disks()
                event = roles.observe([d["id"] for d in disks])
                if event != previous:
                    emit(dict(event, devices=disks))
                    previous = event
                time.sleep(0.5)
        elif args.command == "appliance":
            from .appliance import run
            run(lambda: cancelled, args.device)
        elif args.command == "display-demo":
            from .display import render
            from .framebuffer import Framebuffer
            from .preview import scenario
            with Framebuffer(args.device) as screen:
                def show(state):
                    if cancelled:
                        raise KeyboardInterrupt
                    screen.show(render(state))
                    time.sleep(0.15)  # Slow the sample sequence for display inspection, not a speed benchmark.
                result = scenario(args.case, show)
            emit({"state": result["final_state"], "source_unchanged": result["source_unchanged"], "demo": True})
        elif args.command == "preview":
            from .preview import create_preview
            create_preview(args.output)
        elif args.command == "backup":
            backup(args.source, args.target, emit, lambda: cancelled)
        else:
            result = verify(args.job)
            emit({"state": "VERIFIED", "files": len(result["files"]), "bytes": result["bytes"]})
        return 0
    except KeyboardInterrupt:
        emit({"state": "CANCELLED", "error": "사용자가 화면 데모를 중단했습니다."})
        return 130
    except (BackupError, OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
        emit({"state": "FAILED", "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
