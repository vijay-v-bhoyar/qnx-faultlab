import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tests.fixtures import records, encode
from faultlab.capture import parse_capture
try:
    from faultlab.report import write_report, ReportError
except ImportError:
    write_report = ReportError = None


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(write_report), "Offline report writer is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_handoff_retains_bytes_digest_and_inert_offline_html(self):
        cap = parse_capture(encode())
        out = write_report(cap, self.root / "report")
        self.assertEqual((out / "source.ndjson").read_bytes(), cap.raw)
        summary = json.loads((out / "summary.json").read_text())
        self.assertEqual(summary["source_sha256"], cap.sha256)
        html = (out / "index.html").read_text()
        for expected in ("FaultLab", "SYNTHETIC", "not evidence of native", "summary.json", "source.ndjson", "<details", 'id="attention"', "Elapsed"):
            self.assertIn(expected, html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn('src="http', html.lower())
        self.assertIn("Content-Security-Policy", html)

    def test_untrusted_text_is_escaped_and_no_external_urls_added(self):
        data = records()
        data[0]["session_id"] = '<img src=x onerror="alert(1)">'
        data[2]["detail"] = "</td><script>alert('injected')</script>"
        out = write_report(parse_capture(encode(data)), self.root / "hostile")
        html = (out / "index.html").read_text()
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html.lower())
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)

    def test_failed_drill_has_visible_mismatch_and_attention_state(self):
        data = records()
        data[6]["errno_name"] = "EACCES"
        out = write_report(parse_capture(encode(data)), self.root / "failed")
        html = (out / "index.html").read_text()
        self.assertIn("EACCES", html)
        self.assertRegex(html, r'<article class="[^\"]*\bfail\b[^\"]*"')
        self.assertIn("did not match", html)

    def test_failed_recovery_exposes_payload_verification_evidence(self):
        data = records()
        data[7]["payload_ok"] = False
        out = write_report(parse_capture(encode(data)), self.root / "payload-failed")
        html = (out / "index.html").read_text()
        self.assertIn('data-label="Payload verified">false</td>', html)

    def test_refuse_existing_directory_without_touching_user_file(self):
        out = self.root / "existing"
        out.mkdir()
        sentinel = out / "my-work.txt"
        sentinel.write_text("keep me")
        with self.assertRaises(ReportError):
            write_report(parse_capture(encode()), out)
        self.assertEqual(sentinel.read_text(), "keep me")
        self.assertEqual(list(out.iterdir()), [sentinel])

    def test_refuse_existing_file_and_empty_directory(self):
        for name, isdir in (("empty", True), ("file", False)):
            out = self.root / name
            out.mkdir() if isdir else out.write_text("keep")
            with self.subTest(name=name), self.assertRaises(ReportError):
                write_report(parse_capture(encode()), out)

    def test_refuse_symlink_output_or_ancestor(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("OS privilege does not allow symlinks; exercise on Linux")
        with self.assertRaises(ReportError):
            write_report(parse_capture(encode()), link / "report")
        self.assertEqual(list(real.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point boundary")
    def test_junction_is_refused_when_path_is_junction_is_unavailable(self):
        real = self.root / "junction-target"
        real.mkdir()
        link = self.root / "junction"
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(created.returncode, 0, created.stderr)
        # Simulate the fallback used before pathlib added is_junction in Python 3.12.
        with patch.object(Path, "is_junction", return_value=False, create=True):
            with self.assertRaises(ReportError):
                write_report(parse_capture(encode()), link / "report")
        self.assertEqual(list(real.iterdir()), [])
