"""Offline application-state comparison with a caller-declared timing policy."""
from html import escape
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import __version__
from .analysis import analyze
from .capture import CaptureError
from .report import ReportError, STYLE, _no_links, write_report


def _run_result(capture):
    analysis = analyze(capture)
    phases = {event["phase"]: event for event in capture.events}
    # Absolute clocks belong to one capture only. Compare derived intervals,
    # never a timestamp in one VM run with a timestamp in another run.
    interval = phases["final_state"]["monotonic_ns"] - phases["request"]["monotonic_ns"]
    path = []
    for phase in ("request", "recovered_state", "recovery_request", "followup_request", "final_state"):
        event = phases[phase]
        path.append({"phase": phase, "operation_id": event["operation_id"], "quantity": event["quantity"],
                     "remaining": event["remaining"] if event["remaining"] >= 0 else None,
                     "applied": event["applied"] if event["applied"] >= 0 else None,
                     "duplicate": event["duplicate"] if event["payload_ok"] else None})
    return {"analysis": analysis, "source_sha256": capture.sha256, "state_path": path,
            "recovery_interval_ns": interval}


def compare_captures(baseline, candidate, max_recovery_ms=None):
    """Compare compatible inventory captures; no implicit recovery-time budget."""
    if max_recovery_ms is not None and (type(max_recovery_ms) is not int or not 1 <= max_recovery_ms <= 60000):
        raise CaptureError("max_recovery_ms: expected integer in 1..60000, or no policy")
    for name, capture in (("baseline", baseline), ("candidate", candidate)):
        if capture.session["schema_version"] != 2 or capture.session.get("contract") != "inventory-retry/1":
            raise CaptureError(f"{name}: comparison requires schema 2 inventory-retry/1 capture")
    compatibility = ("source_kind", "sysname", "release", "machine")
    differences = [field for field in compatibility if baseline.session[field] != candidate.session[field]]
    if differences:
        raise CaptureError("comparison requires equal declared source kind and target; mismatched: " + ", ".join(differences))
    before, after = _run_result(baseline), _run_result(candidate)
    before_pass = before["analysis"]["overall"] == "PASS"
    after_pass = after["analysis"]["overall"] == "PASS"
    transition = "unchanged" if before_pass == after_pass else "improved" if after_pass else "regressed"
    limit = None if max_recovery_ms is None else max_recovery_ms * 1000000
    timing_status = "NOT_EVALUATED" if limit is None else "PASS" if after["recovery_interval_ns"] <= limit else "FAIL"
    synthetic = candidate.session["source_kind"] == "synthetic"
    return {"schema_version": 1, "tool_version": __version__, "contract_version": "inventory-comparison/1",
            "source_kind": candidate.session["source_kind"],
            "declared_target": {field: candidate.session[field] for field in ("sysname", "release", "machine")},
            "provenance_note": ("Synthetic fixtures: not evidence of native QNX execution." if synthetic else
                                "Producer-declared QNX captures. Metadata is not authenticated; verify producer, target and actual exit receipts separately."),
            "native_execution_verified": False,
            "measurement": {"definition": "Within each capture: final_state.monotonic_ns minus request.monotonic_ns (lost-reply completion to final-state reply).",
                            "unit": "ns", "clock_scope": "Within each capture only; absolute clocks are never compared across runs.",
                            "meaning": "A sample recovery-workflow interval, including restart, retry and follow-up; not a hardware real-time guarantee."},
            "policy": {"max_recovery_ms": max_recovery_ms, "max_recovery_ns": limit,
                       "source": "Caller-supplied candidate recovery budget; no default or inference from request timeout.",
                       "comparison": "candidate recovery_interval_ns <= max_recovery_ns (inclusive)"},
            "baseline": before, "candidate": after, "application_transition": transition,
            "timing_status": timing_status,
            "overall": "PASS" if after_pass and timing_status != "FAIL" else "FAIL"}


def _state(value):
    return "unknown" if value is None else str(value).lower() if isinstance(value, bool) else str(value)


def _render_html(result):
    before, after = result["baseline"], result["candidate"]
    session_before, session_after = before["analysis"]["session"], after["analysis"]["session"]
    label = "SYNTHETIC COMPARISON" if result["source_kind"] == "synthetic" else "DECLARED QNX CAPTURES"
    budget = result["policy"]["max_recovery_ms"]
    policy = "No recovery budget supplied. Timing NOT_EVALUATED." if budget is None else f"Caller budget: {budget} ms. Candidate interval must be <= {result['policy']['max_recovery_ns']} ns."
    rows = []
    for left, right in zip(before["state_path"], after["state_path"]):
        values = (left["phase"], f"{left['operation_id']} / {left['quantity']}",
                  _state(left["remaining"]), _state(left["applied"]), _state(left["duplicate"]),
                  f"{right['operation_id']} / {right['quantity']}",
                  _state(right["remaining"]), _state(right["applied"]), _state(right["duplicate"]))
        labels = ("Phase", "Before operation / qty", "Before stock", "Before applied", "Before duplicate", "After operation / qty", "After stock", "After applied", "After duplicate")
        rows.append("<tr>" + "".join(f'<td data-label="{heading}">{escape(str(value))}</td>' for heading, value in zip(labels, values)) + "</tr>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>FaultLab — application comparison</title><style>{STYLE}</style></head><body><main>
<header><div class="top"><span class="brand">FAULTLAB / BEFORE &amp; AFTER</span><span class="version">v{escape(result['tool_version'])}</span></div>
<h1>Did recovery preserve the operation?</h1><p class="lead">Compare observed application state. A successful restart alone does not prevent duplicate application.</p>
<div class="banner"><strong>{label}</strong><p>{escape(result['provenance_note'])}</p></div></header>
<p class="small">Declared target: {escape(result['declared_target']['sysname'])} {escape(result['declared_target']['release'])} / {escape(result['declared_target']['machine'])}. Matching metadata is not authentication.</p>
<section class="panel"><h2>Comparison result: {result['overall']}</h2><p>Application transition: <strong>{result['application_transition']}</strong>. Before: {before['analysis']['overall']}. After: {after['analysis']['overall']}.</p>
<p><strong>Timing policy: {result['timing_status']}</strong>. {escape(policy)}</p>
<p class="small">The overall result checks the candidate application and any supplied budget. Baseline results remain visible; an analyzed failure keeps this report.</p></section>
<div class="summary"><section class="panel"><h2>Before / baseline</h2><p>{escape(session_before['session_id'])}</p><p>Application: <strong>{before['analysis']['overall']}</strong></p>
<p>Recovery-workflow interval: {before['recovery_interval_ns']} ns</p><p class="digest small">Source SHA-256: {before['source_sha256']}</p><a href="baseline/index.html">Open baseline full report</a></section>
<section class="panel"><h2>After / candidate</h2><p>{escape(session_after['session_id'])}</p><p>Application: <strong>{after['analysis']['overall']}</strong></p>
<p>Recovery-workflow interval: {after['recovery_interval_ns']} ns</p><p class="digest small">Source SHA-256: {after['source_sha256']}</p><a href="candidate/index.html">Open candidate full report</a></section></div>
<section class="panel"><h2>Before and after application state</h2><p>Stock starts at 10. A committed operation101/3 must leave7 after retry; new operation102/2 must leave5. Applied counts and duplicate recognition are checked independently of declared implementation names.</p>
<table><caption>Observed replies; unknown means no application reply was received. Both full reports retain original events.</caption><thead><tr>{''.join(f'<th scope="col">{heading}</th>' for heading in labels)}</tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<section class="panel section-header"><h2>Measurement and policy</h2><p>{escape(result['measurement']['definition'])}</p><p>{escape(result['measurement']['clock_scope'])}</p><p>{escape(result['policy']['source'])}</p>
<div class="links"><a href="summary.json">Open comparison JSON</a><a href="baseline/source.ndjson">Open baseline original capture</a><a href="candidate/source.ndjson">Open candidate original capture</a></div></section>
<footer><h2>Interpretation limits</h2><p>This is one controlled application comparison. It establishes neither causation, measured developer benefit, statistical performance nor hardware real-time behavior. Equal target labels do not authenticate execution or establish equivalent workloads or host conditions. No arbitrary service or production guarantee follows. Keep both producer/status contexts with these exact bytes.</p></footer>
</main></body></html>"""


def write_comparison(baseline, candidate, output, max_recovery_ms=None):
    """Publish a new eight-file comparison directory; preserve all prior outputs."""
    result = compare_captures(baseline, candidate, max_recovery_ms=max_recovery_ms)
    out = Path(output).absolute()
    temp = None
    try:
        _no_links(out)
        if out.exists():
            raise ReportError(f"output already exists: {out}; choose a new directory to preserve prior work")
        out.parent.mkdir(parents=True, exist_ok=True)
        _no_links(out.parent)
        temp = Path(tempfile.mkdtemp(prefix=".faultlab-comparison-", dir=out.parent))
        write_report(baseline, temp / "baseline")
        write_report(candidate, temp / "candidate")
        (temp / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (temp / "index.html").write_text(_render_html(result), encoding="utf-8")
        _no_links(out)
        if out.exists():
            raise ReportError("output appeared during generation; choose a new directory")
        os.rename(temp, out)
        temp = None
        return out
    except OSError as exc:
        raise ReportError(f"cannot create comparison at {out}: {exc.strerror or exc}") from exc
    finally:
        if temp is not None and temp.exists():
            if temp.parent.resolve() != out.parent.resolve() or not temp.name.startswith(".faultlab-comparison-") or temp.is_symlink():
                raise ReportError("temporary comparison cleanup path failed ownership check")
            shutil.rmtree(temp)
