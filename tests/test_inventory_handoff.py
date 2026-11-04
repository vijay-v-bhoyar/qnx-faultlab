"""Real shell handoff with explicitly synthetic producers, not QNX execution."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tests.fixtures import encode
from tests.test_inventory import inventory_records

ROOT = Path(__file__).resolve().parents[1]
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
SHELL = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")


@unittest.skipUnless(SHELL, "POSIX shell unavailable; inventory handoff not verified")
class InventoryHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = {}
        for mode in ("naive", "idempotent"):
            source = self.root / (mode + ".synthetic.ndjson")
            source.write_bytes(encode(inventory_records(mode)))
            self.inputs[mode] = source
        self.producer = self.root / "synthetic-inventory-producer.sh"
        self.producer.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = "--version" ]; then printf "synthetic-inventory-producer\\n"; exit 0; fi\n'
            'mode=$2\n'
            'printf "synthetic producer only\\n" >&2\n'
            'case "$mode" in\n'
            'naive) cat "$FAULTLAB_TEST_NAIVE"; code=1 ;;\n'
            'idempotent) cat "$FAULTLAB_TEST_IDEMPOTENT"; code=0 ;;\n'
            '*) exit 2 ;;\n'
            'esac\n'
            'if [ "$mode" = "$FAULTLAB_TEST_BAD_MODE" ]; then code=$FAULTLAB_TEST_BAD_EXIT; fi\n'
            'if [ "$mode" = "$FAULTLAB_TEST_BLOCK_RECEIPT" ]; then mkdir "$(dirname "$4")/native-exit-code.txt" || exit 2; fi\n'
            'exit "$code"\n', encoding="utf-8")
        self.producer.chmod(0o700)

    def run_handoff(self, output, bad_mode="", bad_exit="", block_receipt=""):
        env = dict(os.environ, FAULTLAB_TEST_NAIVE=self.inputs["naive"].as_posix(),
                   FAULTLAB_TEST_IDEMPOTENT=self.inputs["idempotent"].as_posix(),
                   FAULTLAB_TEST_BAD_MODE=bad_mode, FAULTLAB_TEST_BAD_EXIT=str(bad_exit),
                   FAULTLAB_TEST_BLOCK_RECEIPT=block_receipt)
        return subprocess.run([SHELL, "--noprofile", "--norc", (ROOT / "native/inventory-smoke.sh").as_posix(),
                               self.producer.as_posix(), output.as_posix()],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)

    def test_expected_naive_failure_and_corrected_success_publish_exact_pair(self):
        output = self.root / "pair"
        result = self.run_handoff(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("naive contract FAIL (1), idempotent PASS (0)", result.stdout)
        for mode, code in (("naive", 1), ("idempotent", 0)):
            case = output / mode
            with self.subTest(mode=mode):
                self.assertEqual((case / "capture.ndjson").read_bytes(), self.inputs[mode].read_bytes())
                self.assertFalse((case / "capture.partial.ndjson").exists())
                self.assertEqual((case / "native-exit-code.txt").read_text().strip(), str(code))
                self.assertEqual((case / "diagnostics.txt").read_text().strip(), "synthetic producer only")

    def test_unexpected_exit_retains_partial_bytes_and_actual_receipt(self):
        for mode in ("naive", "idempotent"):
            for code in (2, 130):
                with self.subTest(mode=mode, code=code):
                    output = self.root / (mode + "-" + str(code))
                    result = self.run_handoff(output, mode, code)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    case = output / mode
                    self.assertEqual((case / "capture.partial.ndjson").read_bytes(), self.inputs[mode].read_bytes())
                    self.assertFalse((case / "capture.ndjson").exists())
                    self.assertEqual((case / "native-exit-code.txt").read_text().strip(), str(code))
                    self.assertIn("partial evidence retained", result.stderr)
                    if mode == "naive":
                        self.assertFalse((output / "idempotent").exists())
                    else:
                        self.assertEqual((output / "naive/capture.ndjson").read_bytes(), self.inputs["naive"].read_bytes())

    def test_reused_output_is_rejected_without_overwriting_retained_files(self):
        output = self.root / "existing"
        result = self.run_handoff(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        sentinel = output / "user-notes.txt"
        sentinel.write_bytes(b"preserve original notes")
        before = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()}
        result = self.run_handoff(output)
        self.assertEqual(result.returncode, 2, result.stderr)
        after = {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_failed_exit_receipt_write_cannot_promote_complete_capture(self):
        for mode in ("naive", "idempotent"):
            with self.subTest(mode=mode):
                output = self.root / ("blocked-receipt-" + mode)
                result = self.run_handoff(output, block_receipt=mode)
                self.assertEqual(result.returncode, 2, result.stderr)
                case = output / mode
                self.assertTrue((case / "native-exit-code.txt").is_dir())
                self.assertEqual((case / "capture.partial.ndjson").read_bytes(), self.inputs[mode].read_bytes())
                self.assertFalse((case / "capture.ndjson").exists())
