# Capture format v1
A complete capture is UTF-8 newline-delimited JSON. The first object describes the session; exactly fourteen ordered events cover healthy, stall and exit. Blank lines are permitted. The parser retains exact bytes.

Session fields: type=session, schema_version=1, tool_version, session_id, source_kind (synthetic or qnx-native), sysname, release, machine, timeout_ms (10..5000), clock=CLOCK_MONOTONIC. Native declarations require QNX/8.x metadata, but are not authenticated proof.

Every event has type=event, contiguous seq from 1, scenario, phase, monotonic_ns, outcome, errno_name and detail. Event timestamps are nondecreasing. Each scenario starts with begin/started and closes cleanup/(clean or error), end/complete. Healthy has one request; stall and exit have request then recovery_request.

Request fields additionally include started_ns, duration_ns and payload_ok. Duration must equal completion minus start, and start cannot precede the prior event. Request outcome is reply, timeout, server_gone or error. Parser structure is separate from contract verdicts.

Pinned expectations:
- healthy: verified reply, empty errno, clean cleanup;
- stall: ETIMEDOUT/timeout, no reply payload, then verified fresh-service reply and cleanup;
- exit: ESRCH or EBADF/server_gone, no reply payload, then verified fresh-service reply and cleanup. The native exit-after-receive implementation specifically expects ESRCH; its native smoke result must be checked separately.

Missing events, duplicate fields, nonfinite numbers, boolean counters, unpaired Unicode surrogates, unexpected fields/versions and over-budget files are rejected. Limits: 16 MiB, 10,000 records, 4096 characters per text field.

The analyzer outputs contract version faultlab-drills/1, exact input digest, declared provenance, expectations, observations, failures and counts. It never sets native_execution_verified=true. Real native proof consists of actual licensed build/target/run evidence in addition to metadata.

Source flow: native/faultlab_probe.c -> capture.ndjson -> faultlab/capture.py -> faultlab/analysis.py -> faultlab/report.py -> index.html + summary.json + exact source.ndjson. faultlab/__main__.py owns CLI exit status and errors. Tests exercise parser, contract, output boundaries and the first-task CLI. No repository graph is configured; this explicit file/interface map is the navigation fallback.
