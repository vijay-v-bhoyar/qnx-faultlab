"""Synthetic contract tests; native application execution is a separate check."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from faultlab.analysis import analyze
from faultlab.capture import CaptureError, parse_capture
from faultlab.report import write_report
from tests.fixtures import encode


def inventory_records(implementation="idempotent"):
    rows = [{"type": "session", "schema_version": 2, "tool_version": "0.2.0",
             "session_id": "synthetic-inventory", "source_kind": "synthetic",
             "sysname": "Fixture", "release": "synthetic", "machine": "not-a-target",
             "timeout_ms": 250, "clock": "CLOCK_MONOTONIC",
             "contract": "inventory-retry/1", "implementation": implementation}]
    naive = implementation == "naive"
    requests = {
        "request": (101, 3, -1, -1, False),
        "recovered_state": (0, 0, 7, 1, False),
        "recovery_request": (101, 3, 4 if naive else 7, 2 if naive else 1, not naive),
        "followup_request": (102, 2, 2 if naive else 5, 3 if naive else 2, False),
        "final_state": (0, 0, 2 if naive else 5, 3 if naive else 2, False),
    }
    phases = ("begin", "request", "crash_exit", "recovered_state", "recovery_request",
              "followup_request", "final_state", "cleanup", "end")
    now = 0
    for seq, phase in enumerate(phases, 1):
        event = {"type": "event", "seq": seq, "scenario": "inventory_retry", "phase": phase,
                 "monotonic_ns": now, "outcome": {"begin": "started", "crash_exit": "exited",
                 "cleanup": "clean", "end": "complete"}.get(phase, "reply"),
                 "errno_name": "", "detail": "Self-authored synthetic inventory fixture"}
        if phase in requests:
            op, quantity, stock, applied, duplicate = requests[phase]
            event.update(started_ns=now, duration_ns=1000, monotonic_ns=now + 1000,
                         payload_ok=phase != "request", operation_id=op, quantity=quantity,
                         remaining=stock, applied=applied, duplicate=duplicate)
            if phase == "request":
                event.update(outcome="server_gone", errno_name="ESRCH")
        if phase == "crash_exit":
            event["exit_code"] = 42
        rows.append(event)
        now = event["monotonic_ns"] + 1000
    return rows


class InventoryTests(unittest.TestCase):
    def result(self, data):
        return analyze(parse_capture(encode(data)))

    def test_corrected_operation_replay_preserves_stock_and_followup(self):
        result = self.result(inventory_records())
        self.assertEqual(result["contract_version"], "inventory-retry/1")
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(result["counts"], {"passed": 1, "failed": 0, "total": 1})
        self.assertFalse(result["native_execution_verified"])

    def test_naive_duplicate_application_is_analyzed_failure(self):
        result = self.result(inventory_records("naive"))
        self.assertEqual(result["overall"], "FAIL")
        failures = " ".join(result["scenarios"][0]["failures"])
        self.assertIn("retry", failures.lower())
        self.assertIn("7", failures)
        self.assertIn("4", failures)

    def test_declaration_cannot_make_wrong_stock_pass_or_correct_stock_fail(self):
        data = inventory_records("naive")
        data[0]["implementation"] = "idempotent"
        self.assertEqual(self.result(data)["overall"], "FAIL")
        data = inventory_records()
        data[0]["implementation"] = "naive"
        self.assertEqual(self.result(data)["overall"], "PASS")

    def test_invariants_detect_wrong_identity_state_receipt_reply_and_cleanup(self):
        for index, key, value in ((2, "operation_id", 102), (2, "errno_name", "EBADF"),
                                  (3, "exit_code", 0), (4, "remaining", 10),
                                  (5, "quantity", 2), (5, "duplicate", False),
                                  (5, "applied", 2), (6, "operation_id", 101),
                                  (6, "payload_ok", False), (7, "remaining", 4),
                                  (8, "outcome", "error")):
            with self.subTest(index=index, key=key):
                data = inventory_records()
                data[index][key] = value
                self.assertEqual(self.result(data)["overall"], "FAIL")

    def test_schema_rejects_malformed_incomplete_extra_and_out_of_order(self):
        invalid = []
        data = inventory_records(); data[0]["contract"] = "inventory-retry/2"; invalid.append(data)
        data = inventory_records(); data[0]["implementation"] = "unknown"; invalid.append(data)
        data = inventory_records(); data[4]["remaining"] = True; invalid.append(data)
        data = inventory_records(); data[5]["duplicate"] = 1; invalid.append(data)
        data = inventory_records(); data[3]["exit_code"] = -1; invalid.append(data)
        data = inventory_records(); data[4]["duration_ns"] = 0; invalid.append(data)
        data = inventory_records(); data[5]["operation_id"] = 103; invalid.append(data)
        data = inventory_records(); data[5]["remaining"] = 11; invalid.append(data)
        data = inventory_records(); data[5]["unexpected"] = 1; invalid.append(data)
        data = inventory_records(); data[4], data[5] = data[5], data[4]; invalid.append(data)
        invalid.extend((inventory_records()[:-1], inventory_records() + [inventory_records()[-1]]))
        for index, data in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(CaptureError):
                parse_capture(encode(data))

    def test_report_exposes_operation_stock_count_replay_and_raw_bytes(self):
        data = inventory_records("naive")
        data[4]["detail"] = '<script>bad()</script>\u2028recovered'
        raw = encode(data)
        with tempfile.TemporaryDirectory() as folder:
            out = write_report(parse_capture(raw), Path(folder) / "report")
            html = (out / "index.html").read_text(encoding="utf-8")
            for text in ("Inventory", "101", "Remaining", "Applied", "Duplicate", "ESRCH", "FAIL", "0 / 1 matched", "SYNTHETIC", "naive", "observed child exit 42"):
                self.assertIn(text, html)
            self.assertNotIn("<script", html)
            self.assertIn('<td data-label="Duplicate">unknown</td>', html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("Three service drills", html)
            self.assertEqual((out / "source.ndjson").read_bytes(), raw)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["source_sha256"], hashlib.sha256(raw).hexdigest())

    def test_cli_reports_corrected_zero_naive_one_malformed_two(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for mode, expected in (("idempotent", 0), ("naive", 1), ("broken", 2)):
                path = root / (mode + ".ndjson")
                path.write_bytes(encode(inventory_records(mode if mode != "broken" else "idempotent"))
                                 if mode != "broken" else b'{"schema_version":2}\n')
                out = root / mode
                result = subprocess.run([sys.executable, "-m", "faultlab", "report", str(path), "--out", str(out)],
                                        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(out.exists(), expected != 2)
