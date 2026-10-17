import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


class ProcessInterruptionTests(unittest.TestCase):
    def exercise(self, signum):
        with tempfile.TemporaryDirectory(prefix="mebs-process-") as temp:
            base = Path(temp)
            source, target = base / "source", base / "target"
            source.mkdir()
            target.mkdir()
            payload = b"MEBS source data" * 131072
            (source / "clip.bin").write_bytes(payload)
            # Pause after a real data write so the parent can deterministically
            # deliver a real signal at the transaction boundary under test.
            script = '''
import os, signal, sys
from mebs.backup import backup, Cancelled
cancelled = False
def stop(signum, frame):
    global cancelled
    cancelled = True
signal.signal(signal.SIGTERM, stop)
def event(e):
    if e['state'] == 'COPYING':
        print('COPYING', flush=True)
        os.kill(os.getpid(), signal.SIGSTOP)
try:
    backup(sys.argv[1], sys.argv[2], event, lambda: cancelled)
except Cancelled:
    sys.exit(7)
'''
            process = subprocess.Popen([sys.executable, "-c", script, str(source), str(target)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                # A timeout on the subprocess avoids hanging the test suite if
                # the child fails before reaching its first copy event.
                import selectors
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=10), "Child did not start copying")
                self.assertEqual(process.stdout.readline().strip(), "COPYING")
                _, status = os.waitpid(process.pid, os.WUNTRACED)
                self.assertTrue(os.WIFSTOPPED(status))
                process.send_signal(signum)
                if signum == signal.SIGTERM:
                    process.send_signal(signal.SIGCONT)
                process.communicate(timeout=10)
                self.assertEqual(list(target.glob("mebs-backup-*")), [])
                pending, = target.glob(".mebs-pending-*")
                self.assertEqual(json.loads((pending / "job.json").read_text())["state"], "IN_PROGRESS")
                self.assertEqual((source / "clip.bin").read_bytes(), payload)
                returncode = process.returncode
                failed = (pending / "failure.json").exists()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
            return returncode, failed

    def test_sigterm_records_failure_and_keeps_source(self):
        code, failed = self.exercise(signal.SIGTERM)
        self.assertEqual(code, 7)
        self.assertTrue(failed)

    def test_sigkill_cannot_publish_partial_copy(self):
        code, failed = self.exercise(signal.SIGKILL)
        self.assertEqual(code, -signal.SIGKILL)
        self.assertFalse(failed)  # No handler runs; hidden pending directory remains.


if __name__ == "__main__":
    unittest.main()
