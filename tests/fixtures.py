"""Self-authored synthetic observations, never native execution evidence."""
import json


def records():
    data = [{"type": "session", "schema_version": 1, "tool_version": "0.1.0",
             "session_id": "synthetic-session", "source_kind": "synthetic",
             "sysname": "Fixture", "release": "synthetic", "machine": "not-a-target",
             "timeout_ms": 250, "clock": "CLOCK_MONOTONIC"}]
    seq, now = 0, 0
    for scenario in ("healthy", "stall", "exit"):
        phases = ["begin", "request"]
        if scenario != "healthy":
            phases.append("recovery_request")
        phases += ["cleanup", "end"]
        for phase in phases:
            seq += 1
            event = {"type": "event", "seq": seq, "scenario": scenario, "phase": phase,
                     "monotonic_ns": now, "outcome": {"begin": "started", "cleanup": "clean", "end": "complete"}.get(phase, "reply"),
                     "errno_name": "", "detail": "Self-authored synthetic fixture"}
            if phase in ("request", "recovery_request"):
                duration = 250000000 if scenario == "stall" and phase == "request" else 1000000
                event.update(started_ns=now, duration_ns=duration, monotonic_ns=now + duration, payload_ok=True)
                if phase == "request" and scenario != "healthy":
                    event.update(outcome="timeout" if scenario == "stall" else "server_gone",
                                 errno_name="ETIMEDOUT" if scenario == "stall" else "ESRCH", payload_ok=False)
            data.append(event)
            now = event["monotonic_ns"] + 1000
    return data


def encode(data=None):
    return ("\n".join(json.dumps(row, ensure_ascii=False) for row in (records() if data is None else data)) + "\n").encode("utf-8")
