"""Synthetic producer/real shell handoff tests; never native QNX evidence."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.fixtures import encode

ROOT = Path(__file__).resolve().parents[1]
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
SHELL = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")


@unittest.skipUnless(SHELL, "POSIX shell unavailable; handoff execution not verified")
class NativeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic.ndjson"
        self.source.write_bytes(encode())
        self.probe = self.root / "synthetic-producer.sh"
        self.probe.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = "--version" ]; then printf "synthetic-test-producer\\n"; exit 0; fi\n'
            'if [ "$2" = "0" ]; then exit 2; fi\n'
            'cat "$FAULTLAB_TEST_CAPTURE"\n'
            'exit "$FAULTLAB_TEST_EXIT"\n', encoding="utf-8")
        self.probe.chmod(0o700)

    def run_handoff(self, exit_code):
        output = self.root / ("run-" + str(exit_code))
        env = dict(os.environ, FAULTLAB_TEST_CAPTURE=self.source.as_posix(), FAULTLAB_TEST_EXIT=str(exit_code))
        result = subprocess.run([SHELL, "--noprofile", "--norc", (ROOT / "native/smoke.sh").as_posix(),
                                 self.probe.as_posix(), output.as_posix()],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
        return output, result

    def test_failed_producer_with_complete_bytes_cannot_publish_completed_capture(self):
        for code in (1, 130):
            out, result = self.run_handoff(code)
            with self.subTest(exit_code=code):
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertFalse((out / "capture.ndjson").exists())
                self.assertEqual((out / "capture.partial.ndjson").read_bytes(), self.source.read_bytes())
                self.assertEqual((out / "native-exit-code.txt").read_text().strip(), str(code))

    def test_success_publishes_exact_capture_and_zero_exit_receipt(self):
        out, result = self.run_handoff(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((out / "capture.ndjson").read_bytes(), self.source.read_bytes())
        self.assertFalse((out / "capture.partial.ndjson").exists())
        self.assertEqual((out / "native-exit-code.txt").read_text().strip(), "0")
