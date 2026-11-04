"""Run with python -m faultlab; no network or native fault action in the host CLI."""
import argparse
import json
import sys

from . import __version__
from .analysis import analyze
from .capture import CaptureError, load_capture
from .comparison import compare_captures, write_comparison
from .report import ReportError, write_report


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="FaultLab: inspect QNX service-drill captures offline. Synthetic fixtures are not native proof.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "report"):
        command = commands.add_parser(name, help="Validate and analyze capture" if name == "validate" else "Create a new offline report directory")
        command.add_argument("capture", help="UTF-8 FaultLab NDJSON capture")
        if name == "report":
            command.add_argument("--out", required=True, help="New report directory; existing paths are refused")
    comparison = commands.add_parser("compare", help="Compare two inventory application captures offline")
    comparison.add_argument("baseline", help="Baseline schema 2 inventory capture")
    comparison.add_argument("candidate", help="Candidate schema 2 inventory capture")
    comparison.add_argument("--out", required=True, help="New comparison directory; existing paths are refused")
    comparison.add_argument("--max-recovery-ms", type=int, help="Optional caller recovery-workflow budget, integer 1..60000 ms; no default")
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            baseline, candidate = load_capture(args.baseline), load_capture(args.candidate)
            result = compare_captures(baseline, candidate, max_recovery_ms=args.max_recovery_ms)
            out = write_comparison(baseline, candidate, args.out, max_recovery_ms=args.max_recovery_ms)
            print(f"{result['overall']} - application {result['application_transition']}; timing {result['timing_status']}; comparison: {out / 'index.html'}")
            print(result["provenance_note"])
            return 0 if result["overall"] == "PASS" else 1
        capture = load_capture(args.capture)
        result = analyze(capture)
        if args.command == "report":
            out = write_report(capture, args.out)
            print(f"{result['overall']} - {result['source_kind']} capture; report: {out / 'index.html'}")
            print(result["provenance_note"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0 if result["overall"] == "PASS" else 1
    except (CaptureError, ReportError) as exc:
        print(f"faultlab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
