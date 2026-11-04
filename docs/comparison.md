# Compare application recovery before and after a change

FaultLab's offline comparison supports a concrete decision: did the candidate preserve the inventory operation, and did its observed recovery interval fit a caller-supplied budget?

## Run a comparison

From this source root, with Python3.10+:

```sh
python -m faultlab compare samples/native-inventory-20261104/naive/capture.ndjson samples/native-inventory-20261104/idempotent/capture.ndjson --out artifacts/recovery-comparison
```

Expected exit0: the candidate application passes. Open index.html. Application transition is improved (baselineFAIL, candidatePASS), but **timing is NOT_EVALUATED** because no budget was supplied. Both state paths, source digests, full reports and exact raw inputs remain accessible.

Inputs must be valid schema2 inventory-retry/1 captures with matching declared source_kind/sysname/release/machine. Session IDs and absolute clock readings may differ. Matching metadata is not execution authentication. Legacy schema1 or incompatible inputs exit2 instead of an invalid comparison.

## Declare a timing policy deliberately

```sh
python -m faultlab compare samples/native-inventory-20261104/naive/capture.ndjson samples/native-inventory-20261104/idempotent/capture.ndjson --max-recovery-ms 1000 --out artifacts/recovery-budget-example
```

The1000ms value is an illustrative caller policy, not a recommended production SLO. Choose a justified budget for your workload and target. Valid integer limits are1..60000ms. The candidate passes timing when its recorded interval is less than or equal to the limit, using exact nanoseconds. A one-nanosecond excess fails.

The measurement is **within each capture**, from completion of the lost-reply request to completion of the final state query. It includes the owned restart and application checks. It does not subtract a timestamp in one run from a timestamp in another, and it is not the configured MsgSend timeout or an authenticated hardware deadline.

An analyzed candidate can satisfy the application invariant and still FAIL a supplied budget. Such a comparison exits1 and keeps its full report. Without a budget, even a long observed interval remains explicitly NOT_EVALUATED for timing; an application PASS must not be read as a latency qualification.

## Detect an application regression

Reverse the retained pair with a new output path:

```sh
python -m faultlab compare samples/native-inventory-20261104/idempotent/capture.ndjson samples/native-inventory-20261104/naive/capture.ndjson --out artifacts/recovery-regression
```

Expected exit1, application transition regressed. Both inputs are valid native captures; the candidate's retry stock4/final2 violates required7/final5. A failure is not discarded and is not confused with an input error.

Application transition is based on before/after application verdicts, independently of the timing policy: improved, regressed or unchanged. These labels describe recorded contract results, not measured developer productivity or a causal speed improvement.

## Evidence and output

Each comparison is a new eight-file directory:

- index.html and summary.json describe both analyses, declared policy, intervals and verdicts.
- baseline/ and candidate/ each retain index.html, summary.json and exact source.ndjson.

Existing output paths, symlinks and junctions are refused. Input limits, strict parsing and inert/no-network HTML behavior remain unchanged. Native build/producer-exit/journal/target context belongs alongside these reports; the comparison does not authenticate it or replace those receipts. The native sample manifest and [validation record](inventory-validation.md) preserve the bounded actual run.

Exit0 means candidate application plus any supplied timing policy matched; exit1 means an analyzed candidate application or budget failure, with report retained; exit2 means usage/input/compatibility/IO failure.

## What this adds, and what it does not establish

The application report exposes whether a restart concealed duplicate application. The comparison puts both state paths and an optional declared timing check into one inspectable handoff. Those mechanisms are exercised in host tests and native-capture replay; they are not measured human task improvements.

This is not HAM supervision, a System Profiler replacement, live monitoring, an arbitrary-service adapter, a cross-platform performance benchmark, distributed exactly-once proof, statistical timing analysis, hardware/safety qualification or evidence of market demand. The native application remains a controlled sample on one QNX/QEMU configuration. Human learning and productivity require separate actual observations.
