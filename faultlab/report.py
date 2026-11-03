"""An inert, offline handoff report. No imported text becomes executable markup."""
from html import escape
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from .analysis import analyze


class ReportError(ValueError):
    """A report cannot be safely created at the requested destination."""


STYLE = """
:root{color-scheme:light;--paper:#f5f3ed;--ink:#172838;--muted:#485c6b;--blue:#164fc6;--line:#c9d1d6;--green:#176241;--red:#a52428}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1120px;margin:auto;padding:44px 28px 30px}a{color:var(--blue);text-underline-offset:3px}a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--blue);outline-offset:4px}h1{font-size:clamp(2.5rem,7vw,4.7rem);line-height:1.02;letter-spacing:-.055em;margin:12px 0}
h2{font-size:1.35rem;margin:0 0 12px}h3{font-size:1rem;margin:0 0 8px}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:.75rem;font-weight:800;color:var(--muted)}
.lead{font-size:1.1rem;max-width:65ch;color:var(--muted);margin:18px 0 26px}.banner{border-left:5px solid #b75a00;background:#fff4df;padding:16px 20px;margin:24px 0}
.banner strong{display:block;letter-spacing:.04em;font-size:.86rem}.banner p{margin:6px 0 0}.top{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:16px}
.brand{font-weight:750;letter-spacing:.02em}.version{font: .8rem ui-monospace,monospace;color:var(--muted)}.summary{display:grid;grid-template-columns:1.5fr 1fr;gap:20px;margin:28px 0}
.panel{border:1px solid var(--line);border-radius:12px;background:#fff;padding:24px;min-width:0}.metric{font-size:2.5rem;font-weight:750;line-height:1.1;margin:12px 0}.small{font-size:.88rem;color:var(--muted)}
.metadata{display:grid;grid-template-columns:max-content 1fr;gap:8px 16px;margin:0;font-size:.9rem}.metadata dt{color:var(--muted)}.metadata dd{margin:0;overflow-wrap:anywhere;min-width:0}
.filter-label{display:inline-block;margin:8px 22px 18px 7px;font-weight:650}.filter{accent-color:var(--blue);width:18px;height:18px;vertical-align:middle}.section-header{margin:32px 0 8px}
.scenario{border-top:4px solid var(--green);margin:0 0 20px}.scenario.fail{border-top-color:var(--red)}.scenario-top{display:flex;justify-content:space-between;align-items:start;gap:16px}
.badge{display:inline-block;border:1px solid currentColor;border-radius:100px;font-size:.78rem;font-weight:800;letter-spacing:.04em;padding:3px 12px;color:var(--green);white-space:nowrap}.fail .badge{color:var(--red)}
.expectation{margin:14px 0 8px}.observation{margin:0 0 18px}.error{color:var(--red);font-weight:650}.facts{display:flex;gap:24px;flex-wrap:wrap;font-size:.9rem;color:var(--muted)}
details{border-top:1px solid var(--line);padding-top:16px;margin-top:18px}summary{cursor:pointer;font-weight:650}summary:hover{color:var(--blue)}table{border-collapse:collapse;width:100%;table-layout:fixed;margin-top:16px;font-size:.83rem}
caption{text-align:left;color:var(--muted);padding:8px 0}th,td{text-align:left;vertical-align:top;padding:10px 7px;border-bottom:1px solid #e1e5e7;overflow-wrap:anywhere}
th{font-weight:700;background:#f3f5f6}code{font: .85em ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.digest{word-break:break-all}
.links{display:flex;gap:16px;flex-wrap:wrap;margin:18px 0}.links a{padding:10px 16px;background:#edf2ff;border:1px solid #ccd9f4;border-radius:7px;font-weight:650}
.no-attention{display:none;padding:24px;border:1px dashed var(--line);border-radius:10px}#attention:checked~#results .pass{display:none}#attention:checked~#results .no-attention{display:block}
footer{border-top:1px solid var(--line);margin-top:32px;padding-top:20px}.limits{padding-left:20px}.limits li{margin-bottom:6px}
@media(max-width:650px){main{padding:24px 16px}.summary{grid-template-columns:1fr}.panel{padding:18px}.metadata{grid-template-columns:1fr;gap:2px}.metadata dd{margin-bottom:10px}.scenario-top{gap:8px}.facts{gap:12px}.version{max-width:45%;text-align:right}.links a{flex:1;text-align:center}table,tbody{display:block}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}tbody tr{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px;padding:14px 0;border-bottom:1px solid var(--line)}td{display:block;border:0;padding:0;font-size:.85rem}td::before{content:attr(data-label);display:block;color:var(--muted);font-size:.7rem;font-weight:700}td:first-child,td:last-child{grid-column:1/-1}}
@media print{body{background:white}main{padding:0}.filter,.filter-label{display:none}.scenario{break-inside:avoid}.links{display:none}details{display:block}}
"""


def _ms(ns):
    whole, part = divmod(ns, 1000000)
    return f"{whole}.{part // 1000:03d}"


def render_html(result):
    session = result["session"]
    synthetic = result["source_kind"] == "synthetic"
    label = "SYNTHETIC EXAMPLE" if synthetic else "DECLARED QNX CAPTURE"
    title = "Fixture analysis, not native proof" if synthetic else "Observed contracts, declared provenance"
    names = {"healthy": "Healthy exchange", "stall": "Stalled reply", "exit": "Service exit"}
    cards = []
    for scenario in result["scenarios"]:
        rows = []
        start = scenario["events"][0]["monotonic_ns"]
        for event in scenario["events"]:
            duration = _ms(event["duration_ns"]) if "duration_ns" in event else "—"
            values = (event["phase"], event["outcome"], event["errno_name"] or "—",
                      str(event["payload_ok"]).lower() if "payload_ok" in event else "—",
                      _ms(event["monotonic_ns"] - start), duration, event["detail"])
            labels = ("Phase", "Outcome", "Error", "Payload verified", "Elapsed ms", "Duration ms", "Note")
            rows.append("<tr>" + "".join(f'<td data-label="{label}">{escape(str(value))}</td>'
                        for label, value in zip(labels, values)) + "</tr>")
        failures = "".join(f'<li>{escape(f)}</li>' for f in scenario["failures"])
        error = f'<ul class="error">{failures}</ul>' if failures else ""
        cards.append(f"""
<article class="scenario {scenario['status'].lower()} panel" aria-labelledby="{scenario['id']}-heading">
<div class="scenario-top"><div><div class="eyebrow">Drill {len(cards)+1:02d}</div><h2 id="{scenario['id']}-heading">{names[scenario['id']]}</h2></div><span class="badge">{scenario['status']}</span></div>
<p class="expectation"><strong>Expected:</strong> {escape(scenario['expected'])}</p>
<p class="observation"><strong>Observed:</strong> {escape(scenario['observed'])}{' · '+escape(scenario['errno_name']) if scenario['errno_name'] else ''}</p>
{error}<div class="facts"><span>Initial request: <strong>{_ms(scenario['duration_ns'])} ms</strong></span><span>{len(scenario['events'])} recorded events</span></div>
<details><summary>Inspect original observations — {names[scenario['id']]}</summary>
<table><caption>Elapsed time is since this drill began (ms); request duration is recorded separately. Values rounded to 0.001 ms; exact ns are in the raw capture.</caption>
<thead><tr><th scope="col">Phase</th><th scope="col">Outcome</th><th scope="col">Error</th><th scope="col">Payload verified</th><th scope="col">Elapsed ms</th><th scope="col">Duration ms</th><th scope="col">Note</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</details></article>""")
    no_attention = '<p class="no-attention">No mismatched contracts in this capture. This does not verify native provenance or untested behavior.</p>' if result["counts"]["failed"] == 0 else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>FaultLab — {escape(session['session_id'])}</title><style>{STYLE}</style></head>
<body><main><header><div class="top"><span class="brand">FAULTLAB / RUN REPORT</span><span class="version">v{escape(result['tool_version'])} · {escape(result['contract_version'])}</span></div>
<div class="eyebrow section-header">Repeatable drills. Inspectable outcomes.</div><h1>Failure, made<br>inspectable.</h1>
<p class="lead">One capture. Three service drills. See what the client observed, whether recovery worked, and the evidence behind each verdict.</p>
<div class="banner" role="note"><strong>{label}</strong><p>{escape(result['provenance_note'])}</p></div></header>
<div class="summary"><section class="panel" aria-labelledby="overview"><div class="eyebrow">Contract observations</div><h2 id="overview">{title}</h2>
<div class="metric">{result['counts']['passed']} / 3 matched</div><p class="small">{result['counts']['failed']} mismatched. PASS means the recorded outcome matched the pinned drill contract, including expected failure and recovery. It is not a safety certification.</p></section>
<section class="panel" aria-labelledby="identity"><h2 id="identity">Capture identity</h2><dl class="metadata">
<dt>Session</dt><dd>{escape(session['session_id'])}</dd><dt>Declared target</dt><dd>{escape(session['sysname'])} {escape(session['release'])} / {escape(session['machine'])}</dd>
<dt>Configured timeout</dt><dd>{session['timeout_ms']} ms</dd><dt>Clock</dt><dd>{escape(session['clock'])}</dd><dt>Source SHA-256</dt><dd class="digest"><code>{result['source_sha256']}</code></dd></dl></section></div>
<h2 class="section-header">Drill results</h2><p class="small">An expected timeout or lost server can be a successful drill observation. Failed recovery or cleanup cannot.</p>
<input class="filter" type="radio" name="view" id="all" checked><label class="filter-label" for="all">All drills</label>
<input class="filter" type="radio" name="view" id="attention"><label class="filter-label" for="attention">Needs attention ({result['counts']['failed']})</label>
<section id="results" aria-label="Scenario observations">{''.join(cards)}{no_attention}</section>
<section class="panel" aria-labelledby="handoff"><div class="eyebrow">Keep the evidence with the verdict</div><h2 id="handoff">Inspect or hand off this run</h2>
<p>Share this whole report directory. The JSON contains the analysis; the raw capture retains the exact original bytes. Its digest detects changes, not who produced it.</p>
<div class="links"><a href="summary.json">Open analysis JSON</a><a href="source.ndjson">Open original capture</a></div></section>
<footer><h2>What this report does not establish</h2><ul class="limits small"><li>Native execution is not authenticated by capture metadata. Verify producer, toolchain and target separately.</li>
<li>These drills cover FaultLab's isolated sample service, not an arbitrary application or production system.</li><li>Timing on the declared target, especially QEMU, does not establish hardware real-time or safety guarantees.</li>
<li>This is an immutable capture analysis, not live monitoring. Capture a new run to inspect changed behavior.</li></ul></footer></main></body></html>"""


def _no_links(path):
    for item in [path, *path.parents]:
        try:
            metadata = item.lstat()
        except FileNotFoundError:
            continue
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(metadata.st_mode) or reparse:
            raise ReportError(f"output path contains a symbolic link or junction: {item}")


def write_report(capture, output):
    """Publish a new three-artifact directory; never overwrite an existing path."""
    out = Path(output).absolute()
    temp = None
    try:
        _no_links(out)
        if out.exists():
            raise ReportError(f"output already exists: {out}; choose a new directory to preserve prior work")
        out.parent.mkdir(parents=True, exist_ok=True)
        _no_links(out.parent)
        result = analyze(capture)
        temp = Path(tempfile.mkdtemp(prefix=".faultlab-", dir=out.parent))
        (temp / "source.ndjson").write_bytes(capture.raw)
        (temp / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (temp / "index.html").write_text(render_html(result), encoding="utf-8")
        _no_links(out)
        if out.exists():
            raise ReportError("output appeared during generation; choose a new directory")
        os.rename(temp, out)
        temp = None
        return out
    except OSError as exc:
        raise ReportError(f"cannot create report at {out}: {exc.strerror or exc}") from exc
    finally:
        if temp is not None and temp.exists():
            if temp.parent.resolve() != out.parent.resolve() or not temp.name.startswith(".faultlab-") or temp.is_symlink():
                raise ReportError("temporary report cleanup path failed ownership check")
            shutil.rmtree(temp)
