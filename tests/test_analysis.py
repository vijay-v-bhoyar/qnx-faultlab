import unittest
from tests.fixtures import records, encode
try:
    from faultlab.capture import parse_capture
    from faultlab.analysis import analyze
except ImportError:
    parse_capture = analyze = None


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(analyze), "Contract analyzer is not implemented")

    def test_expected_faults_are_successful_drill_observations(self):
        result = analyze(parse_capture(encode()))
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual([r["status"] for r in result["scenarios"]], ["PASS"] * 3)
        self.assertEqual(result["source_kind"], "synthetic")
        self.assertIn("not", result["provenance_note"].lower())

    def test_wrong_error_cannot_pass(self):
        data = records()
        data[6]["errno_name"] = "EACCES"
        result = analyze(parse_capture(encode(data)))
        self.assertEqual(result["overall"], "FAIL")
        self.assertEqual(result["counts"], {"passed": 2, "failed": 1, "total": 3})

    def test_corrupt_reply_failed_recovery_and_cleanup_fail(self):
        for index, key, value in ((2, "payload_ok", False), (7, "payload_ok", False), (8, "outcome", "error")):
            data = records()
            data[index][key] = value
            with self.subTest(index=index):
                result = analyze(parse_capture(encode(data)))
                self.assertEqual(result["overall"], "FAIL")
                self.assertTrue(any(s["failures"] for s in result["scenarios"]))

    def test_native_label_is_declaration_not_authenticated_proof(self):
        data = records()
        data[0].update(source_kind="qnx-native", sysname="QNX", release="8.0.0")
        result = analyze(parse_capture(encode(data)))
        self.assertFalse(result["native_execution_verified"])
        self.assertIn("declared", result["provenance_note"].lower())
