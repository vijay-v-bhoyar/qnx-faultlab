"""Pinned, inspectable expectations; no statistical or native-authenticity claims."""
from . import __version__
from .capture import SCENARIOS

CONTRACT_VERSION = "faultlab-drills/1"
EXPECTED = {
    "healthy": "Verified echo reply; owned service cleaned up.",
    "stall": "ETIMEDOUT from stalled reply; fresh-service echo recovery; cleanup.",
    "exit": "ESRCH or EBADF server/connection loss; fresh-service echo recovery; cleanup.",
}


def _reply(event):
    return event["outcome"] == "reply" and event["payload_ok"] is True and event["errno_name"] == ""


def analyze(capture):
    scenarios = []
    for scenario in SCENARIOS:
        events = [dict(e) for e in capture.events if e["scenario"] == scenario]
        phases = {e["phase"]: e for e in events}
        request = phases["request"]
        failures = []
        if scenario == "healthy":
            expected = _reply(request)
        elif scenario == "stall":
            expected = request["outcome"] == "timeout" and request["errno_name"] == "ETIMEDOUT" and request["payload_ok"] is False
        else:
            expected = request["outcome"] == "server_gone" and request["errno_name"] in {"ESRCH", "EBADF"} and request["payload_ok"] is False
        if not expected:
            failures.append("Initial client outcome did not match the pinned expectation.")
        if scenario != "healthy" and not _reply(phases["recovery_request"]):
            failures.append("Fresh-service recovery did not produce a verified echo reply.")
        if phases["cleanup"]["outcome"] != "clean":
            failures.append("Owned-service cleanup was not recorded as clean.")
        scenarios.append({"id": scenario, "status": "FAIL" if failures else "PASS",
                          "expected": EXPECTED[scenario], "observed": request["outcome"],
                          "errno_name": request["errno_name"], "duration_ns": request["duration_ns"],
                          "failures": failures, "events": events})
    passed = sum(row["status"] == "PASS" for row in scenarios)
    source_kind = capture.session["source_kind"]
    note = ("Synthetic fixture: not evidence of native QNX execution."
            if source_kind == "synthetic" else
            "Producer-declared QNX observation. Metadata is not authenticated; native execution must be verified independently.")
    return {"schema_version": 1, "tool_version": __version__, "contract_version": CONTRACT_VERSION,
            "session": dict(capture.session), "source_kind": source_kind, "provenance_note": note,
            "native_execution_verified": False, "source_sha256": capture.sha256,
            "overall": "PASS" if passed == 3 else "FAIL",
            "counts": {"passed": passed, "failed": 3 - passed, "total": 3},
            "scenarios": scenarios}
