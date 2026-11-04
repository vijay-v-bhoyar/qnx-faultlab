# Native application validation — November 4, 2026

FaultLab0.2 adds a controlled inventory service with persisted operation identity. This record covers actual QNX process crashes and application-state checks, not an arbitrary-service adapter or independent user study.

## Build and target

- Licensed QNX SDP8.0, GCC12.2.0, qcc variant gcc_ntox86_64. make -C native compiled inventory_demo.c with C11, Wall/Wextra/Werror and O2, exit0 without warnings.
- Final native source SHA-256:254993e0e8d4cb0bc540eab392e6067fe02b74956975b01df0727e1179126026.
- Final ELF SHA-256:8980d03feb25609914b604ce03fd1ee7c28dd795ae2c6b2e6fe03cef8db3c4e0. A separately exported copy of the target executable matched exactly. SDK/ELF/image/license material is not distributed.
- Final inventory-smoke.sh SHA-256:e1f15bd7656e8bb5760848d16a2b415c46290326421d0a8e15b78d3afe4ab750.
- QNX8.0.0 target: QNX faultlab-disposable 8.0.0 2026/06/05-16:26:03EDT x86pc x86_64.
- Windows mkqnximage image build; Ubuntu24.04 WSL/QEMU8.2.2 KVM,2 CPUs/512MiB, snapshot disk, no NIC/bridge/host port. A private serial socket carries only commands to the owned disposable VM. Current image was explicitly rebuilt with mkqnximage --build after final source/harness changes; merely invoking the tool with unchanged options can reuse prior output.

The original package/toolchain and SDK-wide verifier finding are retained in [legacy native validation](native-validation.md). The verifier's terminfo casefold/hash explanation does not convert its exit4 into a vendor PASS. This local result does not extend QNX's supported host matrix.

## Actual application behavior

Three fresh native pairs, each with new state directories, produced these observations:

| Check | Naive | Idempotent |
|---|---|---|
| Reserve101/3 from10; commit then exit before reply | Client ESRCH; observed child exit42 | Same |
| Restart query against same journal | remaining7/applied1 | remaining7/applied1 |
| Retry101/3 | remaining4/applied2/duplicate=false | remaining7/applied1/duplicate=true |
| New reservation102/2 | remaining2/applied3 | remaining5/applied2 |
| Final state query |2/3 |5/2 |
| Retained journal |1013 twice, then1022 |1013 once, then1022 |
| Native producer exit |1, completed mismatch |0, matched |
| Independent host contract analysis |FAIL/exit1 |PASS/exit0 |

Journal rows are space-separated operation ID and quantity, for example101 3. The service synchronizes and closes its journal before the injected _exit42. Restart loads that same log. These are actual native application failures and corrections, not synthetic capture mutations. The naive/corrected variants differ in whether they recognize a previously committed operation ID.

The host derives required stock7/5 and commit counts1/2 from initial stock10 and the distinct requested quantities. It does not grant PASS based on the declared implementation label. Its tests swap labels and challenge stock/count/ID/replay/crash fields. Separate state queries are reads from the same application, not an external trusted storage oracle; separately transferred journal bytes corroborate the controlled run.

## Handoff and failure checks

- Closed output reader after five records: final runner reports Broken pipe, exits2, and no residual inventory service appears in the observed process snapshot. An unrelated harness-owned sentinel remains alive; the harness then cleans it up. The incomplete prefix is rejected by the host with2.
- Reusing an existing state directory: native exit2 and unchanged journal checksum. No existing evidence is overwritten.
- Host shell-handoff regressions use explicitly synthetic producers: unexpected exit2/130 retains partial bytes/status, and an unwritable actual-status receipt prevents completed-capture promotion. These shell tests are not native application observations.
- Native inventory producer1 is an intentional completed application mismatch. inventory-smoke.sh requires the expected naive1/corrected0, records actual statuses, and retains both captures. Other statuses remain partial and stop the harness.
- Initial runner/output-check and harness-receipt defects were found during development, reproduced, corrected and retested. Earlier source/binary receipts remain historical; the hashes above identify the final validated candidate.

## Reproduce and inspect

Build and run using [native instructions](../native/README.md). Replay both retained actual captures:

```sh
python -m faultlab report samples/native-inventory-20261104/naive/capture.ndjson --out artifacts/inventory-naive
python -m faultlab report samples/native-inventory-20261104/idempotent/capture.ndjson --out artifacts/inventory-idempotent
```

Run separately; expected exits1 and0. Keep the entire [sample directory](../samples/native-inventory-20261104), including target/version, producer exits, diagnostics, journals and manifest. Captures retain exact original bytes. Hashes and metadata do not authenticate execution; actual build, target, binary-copy and transport observations are separate evidence. The host intentionally leaves native_execution_verified=false.

## Limits

This is one disposable x86_64 VM, three controlled process-crash pairs and a closed-reader schedule. It does not establish concurrent-client correctness, arbitrary application recovery, torn-write/corrupt-journal handling, disk/VM/power-loss durability, distributed exactly-once delivery, exhaustive cancellation schedules, hardware real-time performance, safety certification, human comprehension or productivity improvement. Legacy SIGINT/SIGTERM checks qualify only their separately documented legacy runner/schedules.
