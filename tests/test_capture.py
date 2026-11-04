import hashlib
import json
import unittest
from tests.fixtures import records, encode

try:
    from faultlab.capture import parse_capture, CaptureError, MAX_BYTES, MAX_RECORDS
except ImportError:
    parse_capture = CaptureError = None
    MAX_BYTES, MAX_RECORDS = 16 * 1024 * 1024, 10000


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(parse_capture), "Capture parser is not implemented")

    def reject(self, data):
        with self.assertRaises(CaptureError):
            parse_capture(encode(data))

    def test_complete_capture_preserves_exact_bytes(self):
        raw = encode()
        cap = parse_capture(raw)
        self.assertEqual(cap.raw, raw)
        self.assertEqual(cap.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(cap.events), 14)

    def test_reject_missing_scenario_and_incomplete_phase(self):
        for data in (records()[:-1], [r for r in records() if r.get("scenario") != "exit"]):
            with self.subTest(data=len(data)):
                self.reject(data)

    def test_reject_duplicate_phase_sequence_and_unknown_field(self):
        for key, value in (("phase", "begin"), ("seq", 7), ("unexpected", 1)):
            data = records()
            data[2][key] = value
            with self.subTest(key=key):
                self.reject(data)

    def test_reject_boolean_counters_and_nonfinite_values(self):
        for key in ("seq", "monotonic_ns", "duration_ns", "started_ns"):
            data = records()
            data[2][key] = True
            with self.subTest(key=key):
                self.reject(data)
        raw = encode().replace(b'"timeout_ms": 250', b'"timeout_ms": NaN')
        with self.assertRaises(CaptureError):
            parse_capture(raw)

    def test_reject_duplicate_json_keys_even_same_value(self):
        raw = encode().replace(b'"type": "session"', b'"type": "session", "type": "session"', 1)
        with self.assertRaises(CaptureError):
            parse_capture(raw)

    def test_reject_invalid_utf8_json_and_shape(self):
        for raw in (b"\xff", b"[]\n", b"{broken", b"", b"null\n"):
            with self.subTest(raw=raw), self.assertRaises(CaptureError):
                parse_capture(raw)

    def test_reject_time_regression_and_inconsistent_duration(self):
        for key, value in (("monotonic_ns", -1), ("duration_ns", 2), ("started_ns", 999999999)):
            data = records()
            data[2][key] = value
            with self.subTest(key=key):
                self.reject(data)

    def test_qnx_declaration_requires_qnx8_identity(self):
        data = records()
        data[0]["source_kind"] = "qnx-native"
        self.reject(data)
        data[0].update(sysname="QNX", release="8.0.0", machine="x86_64")
        cap = parse_capture(encode(data))
        self.assertEqual(cap.session["source_kind"], "qnx-native")

    def test_reject_unknown_version_bounds_and_long_text(self):
        for key, value in (("schema_version", 2), ("timeout_ms", 9), ("timeout_ms", 5001), ("session_id", "x" * 4097)):
            data = records()
            data[0][key] = value
            with self.subTest(key=key):
                self.reject(data)

    def test_reject_oversized_and_too_many_records(self):
        with self.assertRaises(CaptureError):
            parse_capture(b" " * (MAX_BYTES + 1))
        with self.assertRaises(CaptureError):
            parse_capture(b"{}\n" * (MAX_RECORDS + 1))

    def test_whitespace_and_crlf_preserve_original(self):
        raw = b"\n" + encode().replace(b"\n", b"\r\n")
        self.assertEqual(parse_capture(raw).raw, raw)

    def test_literal_unicode_separators_are_text_not_record_boundaries(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            with self.subTest(separator=repr(separator)):
                data = records()
                data[2]["detail"] = "prefix" + separator + "suffix"
                raw = encode(data)
                escaped = ("\n".join(json.dumps(row, ensure_ascii=True) for row in data) + "\n").encode()
                literal = parse_capture(raw)
                self.assertEqual(literal.events, parse_capture(escaped).events)
                self.assertEqual(literal.raw, raw)
                self.assertEqual(literal.sha256, hashlib.sha256(raw).hexdigest())

    def test_reject_unpaired_surrogates_before_report_encoding(self):
        for index, field in ((0, "session_id"), (2, "detail")):
            data = records()
            data[index][field] = chr(0xD800)
            raw = ("\n".join(json.dumps(r, ensure_ascii=True) for r in data) + "\n").encode()
            with self.subTest(field=field), self.assertRaises(CaptureError):
                parse_capture(raw)
