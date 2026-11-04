# Capture format v1
This section specifies the retained legacy IPC format. Records are LF-delimited (CRLF accepted); Unicode U+0085/U+2028/U+2029 inside JSON strings are text, not record separators. Exact bytes remain preserved.
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

## Application capture v2: inventory-retry/1
Session: all v1 session fields, schema_version2, contract=inventory-retry/1, implementation=naive or idempotent. The implementation label is declared context, never the success oracle. Limits and provenance rules remain unchanged.

One inventory_retry scenario contains exactly nine phases: begin, request, crash_exit, recovered_state, recovery_request, followup_request, final_state, cleanup,end. All use v1 base event fields. Request/recovered_state/recovery_request/followup_request/final_state additionally use v1 request fields plus integer operation_id(0..102), quantity(0..3), remaining(-1..10), applied(-1..3), and boolean duplicate. Minus1 denotes unavailable application results after the lost reply. crash_exit additionally records integer exit_code(0..255), outcome exited and empty errno. Other phase/timing/type constraints remain strict.

Pinned application invariant: start stock10. Request101 reserves3, loses reply with ESRCH, and reports no invented state (-1/-1). Child exit42 corroborates the injected process failure. A restarted query must return stock7/applied1. Retrying101/3 must return7/1 with duplicate=true; a distinct102/2 must return5/2 with duplicate=false; final query must return5/2. Successful reads/replies require empty errno and payload verification. Cleanup must be clean. The oracle computes expected stock from the fixed initial state and distinct requested quantities, independently of implementation label. Naive stock4/2 then2/3 is a valid capture with analyzed FAIL, not a schema error.

Application source flow: native/inventory_demo.c -> native/inventory-smoke.sh -> schema2 capture -> capture.py -> analysis.py -> existing inert report/raw/JSON outputs. The report visibly includes application state and observed child status. Full producer exit, state journal and target context must accompany a native evidence handoff. No timing-performance or power-loss guarantee is inferred.

## Offline comparison report: inventory-comparison/1
Host0.3 adds `faultlab compare` for two compatible application captures. Raw capture schema2 and inventory-retry/1 application expectations are unchanged. Comparison JSON schema_version1/contract_version inventory-comparison/1 contains full baseline/candidate analyses and source digests, each state path, within-run recovery_interval_ns, application_transition, explicit policy, timing_status and overall candidate verdict. It never authenticates execution.

No budget means timing_status NOT_EVALUATED. A supplied integer1..60000ms budget is checked inclusively against the candidate interval in exact nanoseconds. The interval is final_state completion minus original request completion within that capture. Candidate applicationFAIL or timingFAIL yields overallFAIL/exit1; a baseline failure remains visible but can improve to an accepted candidate. Invalid/mismatched source_kind/target or schema1 inputs exit2. See [comparison output/handoff](comparison.md) for its eight files and limits.
