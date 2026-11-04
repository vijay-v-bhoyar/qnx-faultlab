import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tests.fixtures import records, encode

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "faultlab", *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=10)

    def test_help_and_version_are_actionable(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("report", result.stdout)
        self.assertIn("validate", result.stdout)
        self.assertEqual(self.run_cli("--version").stdout.strip(), "0.3.0")

    def test_complete_report_first_task(self):
        path = self.root / "source.ndjson"
        path.write_bytes(encode())
        out = self.root / "new-report"
        result = self.run_cli("report", path, "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((out / "index.html").exists())
        self.assertIn("synthetic", result.stdout.lower())

    def test_mismatch_exits_one_and_preserves_report(self):
        data = records()
        data[2]["payload_ok"] = False
        path = self.root / "source.ndjson"
        path.write_bytes(encode(data))
        out = self.root / "failed"
        result = self.run_cli("report", path, "--out", out)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads((out / "summary.json").read_text())["overall"], "FAIL")

    def test_invalid_missing_input_and_overwrite_exit_two_no_traceback(self):
        path = self.root / "broken.ndjson"
        path.write_text("{}")
        for input_path in (path, self.root / "absent"):
            out = self.root / "should-not-exist"
            result = self.run_cli("report", input_path, "--out", out)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())
            self.assertNotIn("Traceback", result.stderr)
        good = self.root / "good.ndjson"
        good.write_bytes(encode())
        result = self.run_cli("report", good, "--out", path)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_text(), "{}")

    def test_validate_reports_provenance_and_failed_contract(self):
        path = self.root / "source.ndjson"
        path.write_bytes(encode())
        result = self.run_cli("validate", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["source_kind"], "synthetic")
        data = records()
        data[6]["errno_name"] = "EACCES"
        path.write_bytes(encode(data))
        self.assertEqual(self.run_cli("validate", path).returncode, 1)

    def test_unicode_capture_validation_survives_ascii_output_pipe(self):
        data = records()
        data[0]["session_id"] = "fixture-" + chr(0x1F9EA)
        path = self.root / "unicode.ndjson"
        path.write_bytes(encode(data))
        env = dict(os.environ, PYTHONIOENCODING="ascii")
        result = subprocess.run([sys.executable, "-m", "faultlab", "validate", str(path)],
                                cwd=ROOT, env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["session"]["session_id"], data[0]["session_id"])
