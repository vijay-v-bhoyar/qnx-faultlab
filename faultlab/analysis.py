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
    if capture.session["schema_version"] == 2:
        return _analyze_inventory(capture)
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


def _analyze_inventory(capture):
    """Check observed application state, never infer success from implementation labels."""
    events = [dict(e) for e in capture.events]
    phases = {e["phase"]: e for e in events}
    failures = []
    # The fixed application task reserves 3 then 2 from stock 10. Replaying
    # operation 101 must not apply another reservation, regardless of mode label.
    initial_stock, first_quantity, next_quantity = 10, 3, 2
    committed_stock = initial_stock - first_quantity
    final_stock = committed_stock - next_quantity
    lost = phases["request"]
    if not (lost["operation_id"] == 101 and lost["quantity"] == first_quantity
            and lost["outcome"] == "server_gone" and lost["errno_name"] == "ESRCH"
            and lost["payload_ok"] is False and lost["remaining"] == -1
            and lost["applied"] == -1 and lost["duplicate"] is False):
        failures.append("Initial reservation did not record operation 101/quantity 3 and lost reply ESRCH without an invented application result.")
    if phases["crash_exit"]["exit_code"] != 42:
        failures.append(f"Committed service crash expected exit 42; observed {phases['crash_exit']['exit_code']}.")
    expected = (("recovered_state", 0, 0, committed_stock, 1, False),
                ("recovery_request", 101, first_quantity, committed_stock, 1, True),
                ("followup_request", 102, next_quantity, final_stock, 2, False),
                ("final_state", 0, 0, final_stock, 2, False))
    names = {"recovered_state": "Restarted state", "recovery_request": "Same-operation retry",
             "followup_request": "New-operation reservation", "final_state": "Final state query"}
    for phase, operation, quantity, stock, applied, duplicate in expected:
        event = phases[phase]
        if not _reply(event):
            failures.append(f"{names[phase]} did not return a verified application reply.")
        if (event["operation_id"], event["quantity"]) != (operation, quantity):
            failures.append(f"{names[phase]} expected operation {operation}, quantity {quantity}; observed {event['operation_id']}, {event['quantity']}.")
        if (event["remaining"], event["applied"], event["duplicate"]) != (stock, applied, duplicate):
            failures.append(f"{names[phase]} expected remaining {stock}, applied {applied}, duplicate {str(duplicate).lower()}; observed remaining {event['remaining']}, applied {event['applied']}, duplicate {str(event['duplicate']).lower()}.")
    if phases["cleanup"]["outcome"] != "clean":
        failures.append("Owned inventory service cleanup was not recorded as clean.")
    source_kind = capture.session["source_kind"]
    note = ("Synthetic fixture: not evidence of native QNX execution." if source_kind == "synthetic" else
            "Producer-declared QNX observation. Metadata is not authenticated; native execution must be verified independently.")
    passed = int(not failures)
    return {"schema_version": 2, "tool_version": __version__, "contract_version": "inventory-retry/1",
            "session": dict(capture.session), "source_kind": source_kind, "provenance_note": note,
            "native_execution_verified": False, "source_sha256": capture.sha256,
            "overall": "PASS" if passed else "FAIL", "counts": {"passed": passed, "failed": 1 - passed, "total": 1},
            "scenarios": [{"id": "inventory_retry", "status": "PASS" if passed else "FAIL",
                           "expected": "Stock 10 → committed 7 → same-operation retry 7 → new reservation 5; exactly two unique operations; owned cleanup.",
                           "observed": lost["outcome"], "errno_name": lost["errno_name"],
                           "duration_ns": lost["duration_ns"], "failures": failures, "events": events}]}
