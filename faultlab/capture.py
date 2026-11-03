"""Strict, bounded parsing of producer-declared FaultLab captures."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 10000
MAX_TEXT = 4096
SCENARIOS = ("healthy", "stall", "exit")
BASE_FIELDS = {"type", "seq", "scenario", "phase", "monotonic_ns", "outcome", "errno_name", "detail"}
REQUEST_FIELDS = {"started_ns", "duration_ns", "payload_ok"}
SESSION_FIELDS = {"type", "schema_version", "tool_version", "session_id", "source_kind",
                  "sysname", "release", "machine", "timeout_ms", "clock"}


class CaptureError(ValueError):
    """Input does not satisfy the pinned capture contract."""


@dataclass(frozen=True)
class Capture:
    raw: bytes
    session: dict
    events: tuple
    sha256: str


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key: " + key)
        obj[key] = value
    return obj


def _constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _integer(value, label, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CaptureError(f"{label}: expected integer in {minimum}..{maximum}")


def _text(value, label, allow_empty=False):
    if not isinstance(value, str) or len(value) > MAX_TEXT or (not allow_empty and not value.strip()):
        raise CaptureError(f"{label}: expected {'possibly empty ' if allow_empty else ''}text up to {MAX_TEXT} characters")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise CaptureError(f"{label}: unsupported control character")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise CaptureError(f"{label}: unpaired Unicode surrogate is not valid text")


def _fields(obj, expected, label):
    if set(obj) != expected:
        missing, extra = expected - set(obj), set(obj) - expected
        raise CaptureError(f"{label}: field mismatch; missing={sorted(missing)}, unexpected={sorted(extra)}")


def parse_capture(raw):
    """Parse complete capture bytes; never infer a record or successful outcome."""
    if not isinstance(raw, bytes):
        raise CaptureError("capture must be bytes")
    if len(raw) > MAX_BYTES:
        raise CaptureError(f"capture exceeds {MAX_BYTES} bytes")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CaptureError("capture is not valid UTF-8") from exc
    nonempty = [(n, line) for n, line in enumerate(lines, 1) if line.strip()]
    if not nonempty or len(nonempty) > MAX_RECORDS:
        raise CaptureError(f"capture needs 1..{MAX_RECORDS} nonempty records")
    records = []
    for line_number, line in nonempty:
        try:
            row = json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant)
        except (ValueError, RecursionError) as exc:
            raise CaptureError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise CaptureError(f"line {line_number}: expected JSON object")
        records.append(row)
    session = records[0]
    _fields(session, SESSION_FIELDS, "session")
    for key in SESSION_FIELDS - {"schema_version", "timeout_ms"}:
        _text(session[key], "session." + key)
    _integer(session["schema_version"], "session.schema_version", 1, 1)
    _integer(session["timeout_ms"], "session.timeout_ms", 10, 5000)
    if session["type"] != "session" or session["clock"] != "CLOCK_MONOTONIC":
        raise CaptureError("session: expected session type and CLOCK_MONOTONIC")
    if session["source_kind"] not in {"synthetic", "qnx-native"}:
        raise CaptureError("session.source_kind: expected synthetic or qnx-native")
    if session["source_kind"] == "qnx-native" and (session["sysname"] != "QNX" or not session["release"].startswith("8.")):
        raise CaptureError("native declaration requires sysname QNX and QNX 8.x release")
    expected = []
    for scenario in SCENARIOS:
        phases = ["begin", "request"]
        if scenario != "healthy":
            phases.append("recovery_request")
        expected.extend((scenario, phase) for phase in phases + ["cleanup", "end"])
    if len(records) - 1 != len(expected):
        raise CaptureError(f"incomplete or extra capture: expected {len(expected)} events for healthy, stall and exit")
    previous_time = 0
    for seq, ((scenario, phase), event) in enumerate(zip(expected, records[1:]), 1):
        label = f"event {seq}"
        request = phase in {"request", "recovery_request"}
        _fields(event, BASE_FIELDS | (REQUEST_FIELDS if request else set()), label)
        for key in BASE_FIELDS - {"seq", "monotonic_ns"}:
            _text(event[key], label + "." + key, allow_empty=key in {"errno_name", "detail"})
        _integer(event["seq"], label + ".seq", seq, seq)
        _integer(event["monotonic_ns"], label + ".monotonic_ns", previous_time)
        if (event["type"], event["scenario"], event["phase"]) != ("event", scenario, phase):
            raise CaptureError(f"{label}: expected {scenario}/{phase} in pinned scenario order")
        if request:
            _integer(event["started_ns"], label + ".started_ns", previous_time)
            _integer(event["duration_ns"], label + ".duration_ns")
            if type(event["payload_ok"]) is not bool:
                raise CaptureError(label + ".payload_ok: expected boolean")
            if event["monotonic_ns"] - event["started_ns"] != event["duration_ns"]:
                raise CaptureError(label + ": duration does not equal completion minus start")
            if event["outcome"] not in {"reply", "timeout", "server_gone", "error"}:
                raise CaptureError(label + ": unknown request outcome")
        else:
            allowed = {"begin": {"started"}, "cleanup": {"clean", "error"}, "end": {"complete"}}[phase]
            if event["outcome"] not in allowed or event["errno_name"]:
                raise CaptureError(label + ": invalid phase outcome or errno")
        previous_time = event["monotonic_ns"]
    return Capture(raw, session, tuple(records[1:]), sha256(raw).hexdigest())


def load_capture(path):
    """Read at most one byte beyond the input budget, including for changing files."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise CaptureError(f"cannot read capture {path}: {exc.strerror or exc}") from exc
    return parse_capture(raw)
