"""Offline comparison invariants; authored captures are synthetic, not QNX proof."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from faultlab.analysis import analyze
from faultlab.capture import CaptureError, load_capture, parse_capture
from faultlab.report import ReportError
from tests.fixtures import encode, records
from tests.test_inventory import inventory_records

try:
    from faultlab.comparison import compare_captures, write_comparison
except ImportError:
    compare_captures = write_comparison = None

ROOT = Path(__file__).resolve().parents[1]


def capture(mode="idempotent", interval=1000000, offset=0):
    rows = inventory_records(mode)
    lost_index = next(i for i, row in enumerate(rows) if row.get("phase") == "request")
    final_index = next(i for i, row in enumerate(rows) if row.get("phase") == "final_state")
    start = rows[lost_index]["monotonic_ns"]
    previous = start
    for step, row in enumerate(rows[lost_index + 1:final_index + 1], 1):
        row["monotonic_ns"] = start + interval * step // (final_index - lost_index)
        if "started_ns" in row:
            row["started_ns"] = previous
            row["duration_ns"] = row["monotonic_ns"] - previous
        previous = row["monotonic_ns"]
    for row in rows[final_index + 1:]:
        previous += 1000
        row["monotonic_ns"] = previous
    for row in rows[1:]:
        row["monotonic_ns"] += offset
        if "started_ns" in row:
            row["started_ns"] += offset
    return parse_capture(encode(rows))


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(compare_captures), "Offline comparison is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_improvement_without_policy_keeps_timing_not_evaluated(self):
        baseline, candidate = capture("naive"), capture()
        result = compare_captures(baseline, candidate)
        self.assertEqual(result["application_transition"], "improved")
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(result["timing_status"], "NOT_EVALUATED")
        self.assertIsNone(result["policy"]["max_recovery_ms"])
        self.assertEqual(result["baseline"]["analysis"]["overall"], "FAIL")
        self.assertEqual(result["candidate"]["analysis"]["overall"], "PASS")

    def test_retained_native_pair_compares_as_improved_without_claiming_new_execution(self):
        sample = ROOT / "samples/native-inventory-20261104"
        baseline = load_capture(sample / "naive/capture.ndjson")
        candidate = load_capture(sample / "idempotent/capture.ndjson")
        result = compare_captures(baseline, candidate)
        self.assertEqual(result["source_kind"], "qnx-native")
        self.assertEqual(result["application_transition"], "improved")
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(result["timing_status"], "NOT_EVALUATED")
        self.assertFalse(result["native_execution_verified"])

    def test_regression_and_unchanged_are_based_on_application_outcomes(self):
        for before, after, transition, overall in (("idempotent", "naive", "regressed", "FAIL"),
                                                   ("idempotent", "idempotent", "unchanged", "PASS"),
                                                   ("naive", "naive", "unchanged", "FAIL")):
            with self.subTest(before=before, after=after):
                result = compare_captures(capture(before), capture(after))
                self.assertEqual(result["application_transition"], transition)
                self.assertEqual(result["overall"], overall)

    def test_capture_clocks_are_independent_and_interval_is_lost_reply_to_final_state(self):
        result = compare_captures(capture("naive", 5000000, 10**12), capture(interval=1000000, offset=10**15))
        self.assertEqual(result["baseline"]["recovery_interval_ns"], 5000000)
        self.assertEqual(result["candidate"]["recovery_interval_ns"], 1000000)
        self.assertIn("final_state", result["measurement"]["definition"])
        self.assertNotIn("faster", json.dumps(result).lower())

    def test_budget_inclusive_boundary_and_one_nanosecond_over(self):
        baseline = capture("naive")
        exact = compare_captures(baseline, capture(interval=1000000), max_recovery_ms=1)
        over = compare_captures(baseline, capture(interval=1000001), max_recovery_ms=1)
        self.assertEqual((exact["overall"], exact["timing_status"]), ("PASS", "PASS"))
        self.assertEqual((over["overall"], over["timing_status"]), ("FAIL", "FAIL"))
        self.assertEqual(over["candidate"]["analysis"]["overall"], "PASS")

    def test_declared_request_timeout_is_not_implicitly_a_recovery_budget(self):
        slow = capture(interval=60000000000)
        self.assertEqual(slow.session["timeout_ms"], 250)
        self.assertEqual(analyze(slow)["overall"], "PASS")
        self.assertEqual(compare_captures(capture("naive"), slow)["timing_status"], "NOT_EVALUATED")
        result = compare_captures(capture("naive"), slow, max_recovery_ms=250)
        self.assertEqual(result["overall"], "FAIL")
        self.assertEqual(result["candidate"]["analysis"]["overall"], "PASS")

    def test_policy_bounds_and_boolean_api_are_rejected(self):
        for budget in (0, -1, 60001, True, False, 1.5, "250"):
            with self.subTest(budget=budget), self.assertRaises(CaptureError):
                compare_captures(capture("naive"), capture(), max_recovery_ms=budget)
        self.assertEqual(compare_captures(capture("naive"), capture(), max_recovery_ms=60000)["timing_status"], "PASS")

    def test_v1_mixed_kind_and_target_mismatches_are_rejected(self):
        base = capture("naive")
        invalid = [parse_capture(encode(records()))]
        for field, value in (("machine", "different-machine"), ("release", "different-release"), ("sysname", "different-system")):
            data = inventory_records()
            data[0][field] = value
            invalid.append(parse_capture(encode(data)))
        data = inventory_records()
        data[0].update(source_kind="qnx-native", sysname="QNX", release="8.0.0")
        invalid.append(parse_capture(encode(data)))
        for index, candidate in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(CaptureError):
                compare_captures(base, candidate)
        with self.assertRaises(CaptureError):
            compare_captures(invalid[0], capture())

    def test_mode_labels_do_not_override_observed_state(self):
        rows = inventory_records("naive")
        rows[0]["implementation"] = "idempotent"
        result = compare_captures(capture(), parse_capture(encode(rows)))
        self.assertEqual(result["application_transition"], "regressed")
        self.assertEqual(result["overall"], "FAIL")

    def test_eight_file_report_preserves_both_raw_inputs_and_inert_state_table(self):
        before_data = inventory_records("naive")
        before_data[0]["session_id"] = '<img src=x onerror="bad()">'
        before_data[4]["detail"] = '</td><script>bad()</script>'
        baseline, candidate = parse_capture(encode(before_data)), capture()
        out = write_comparison(baseline, candidate, self.root / "comparison", max_recovery_ms=250)
        files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
        self.assertEqual(files, ["baseline/index.html", "baseline/source.ndjson", "baseline/summary.json",
                                 "candidate/index.html", "candidate/source.ndjson", "candidate/summary.json", "index.html", "summary.json"])
        for name, original in (("baseline", baseline), ("candidate", candidate)):
            self.assertEqual((out / name / "source.ndjson").read_bytes(), original.raw)
            result = json.loads((out / name / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result["source_sha256"], hashlib.sha256(original.raw).hexdigest())
        html = (out / "index.html").read_text(encoding="utf-8")
        for text in ("Before", "After", "7", "4", "2", "5", "250", "baseline/index.html", "candidate/index.html", "summary.json", "SYNTHETIC", "not", "improved"):
            self.assertIn(text, html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html.lower())
        self.assertIn("&lt;img", html)
        self.assertIn("Content-Security-Policy", html)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["baseline"]["analysis"]["source_sha256"], baseline.sha256)
        self.assertEqual(summary["candidate"]["analysis"]["source_sha256"], candidate.sha256)

    def test_existing_directory_and_symbolic_ancestor_preserve_user_files(self):
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaises(ReportError):
            write_comparison(capture("naive"), capture(), output)
        self.assertEqual(sentinel.read_text(), "keep")
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ReportError):
            write_comparison(capture("naive"), capture(), link / "report")
        self.assertEqual(list(target.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_junction_output_ancestor_is_rejected(self):
        target = self.root / "junction-target"
        target.mkdir()
        link = self.root / "junction"
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(created.returncode, 0, created.stderr)
        with self.assertRaises(ReportError):
            write_comparison(capture("naive"), capture(), link / "comparison")
        self.assertEqual(list(target.iterdir()), [])

    def test_candidate_operation_identity_is_not_hidden_by_baseline_table_labels(self):
        rows = inventory_records()
        retry = next(row for row in rows if row.get("phase") == "recovery_request")
        retry.update(operation_id=102, quantity=2)
        out = write_comparison(capture("naive"), parse_capture(encode(rows)), self.root / "wrong-operation")
        html = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-label="Before operation / qty">101 / 3</td>', html)
        self.assertIn('data-label="After operation / qty">102 / 2</td>', html)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["candidate"]["analysis"]["overall"], "FAIL")

    def test_failed_publish_cleans_only_owned_temporary_directory(self):
        sentinel = self.root / ".faultlab-user-owned"
        sentinel.mkdir()
        (sentinel / "keep.txt").write_text("keep")
        real_rename = os.rename
        def fail_final_publish(source, destination):
            if Path(destination) == self.root / "comparison":
                raise OSError("synthetic final publish failure")
            return real_rename(source, destination)
        with patch("faultlab.comparison.os.rename", side_effect=fail_final_publish):
            with self.assertRaises(ReportError):
                write_comparison(capture("naive"), capture(), self.root / "comparison")
        self.assertEqual([p.name for p in self.root.iterdir()], [".faultlab-user-owned"])

    def test_cli_zero_one_two_and_bad_budget_do_not_overwrite(self):
        base, good, bad = self.root / "baseline.ndjson", self.root / "good.ndjson", self.root / "bad.ndjson"
        base.write_bytes(capture("naive").raw)
        good.write_bytes(capture().raw)
        bad.write_bytes(capture("naive").raw)
        for index, candidate, budget, expected in ((0, good, [], 0), (1, bad, [], 1),
                                                   (2, self.root / "absent", [], 2), (3, good, ["--max-recovery-ms", "0"], 2)):
            with self.subTest(case=index):
                out = self.root / ("cli-" + str(index))
                result = subprocess.run([sys.executable, "-m", "faultlab", "compare", str(base), str(candidate), "--out", str(out), *budget],
                                        cwd=ROOT, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(out.exists(), expected != 2)
        result = subprocess.run([sys.executable, "-m", "faultlab", "compare", str(base), str(good), "--out", str(self.root / "cli-0")],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
