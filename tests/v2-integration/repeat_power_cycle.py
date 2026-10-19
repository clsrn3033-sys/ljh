#!/usr/bin/env python3
"""Repeat host power-cycle fault scenarios without touching real media/power."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=20)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100:
        parser.error('--rounds must be 1..100')
    results = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
               '-p', 'test_power_cycle.py', '-q']
    for number in range(1, args.rounds + 1):
        started = time.monotonic()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        result = {'round': number, 'status': 'PASS' if run.returncode == 0 else 'FAIL',
                  'exit_code': run.returncode, 'seconds': round(time.monotonic()-started, 3),
                  'output': (run.stdout + run.stderr)[-4000:]}
        results.append(result)
        args.output.write_text(json.dumps({'command': command, 'rounds': results},
                                          ensure_ascii=False, indent=2) + '\n')
        print(f"{number}/{args.rounds} {result['status']} {result['seconds']}s", flush=True)
        if run.returncode:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
