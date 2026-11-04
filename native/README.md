# Native QNX probe

## Application: commit succeeded, reply was lost
Build both runners with `make -C native` in the licensed SDP8.0 environment. Transfer `native/faultlab_inventory` and `native/inventory-smoke.sh` to a disposable QNX8.0 x86_64 directory. Then run:
```sh
sh inventory-smoke.sh ./faultlab_inventory ./inventory-run
```
This runs two real application variants. Both commit reservation101 (3 of10 units), synchronize and close the journal, then exit42 before MsgReply. The client observes ESRCH. A restarted service reloads the same journal, reports stock7, retries101, handles new reservation102 (2 units), and reports final stock. The naive baseline applies101 twice, leaving4 then2; the idempotent implementation leaves7 then5. The host checks those observed fields independently of the implementation label.

Transfer the entire inventory-run directory back, then run these host commands separately:
```sh
python -m faultlab report inventory-run/naive/capture.ndjson --out artifacts/inventory-naive
python -m faultlab report inventory-run/idempotent/capture.ndjson --out artifacts/inventory-idempotent
```
Expected host exits are1 and0. Native inventory producer exits0 for matched invariants,1 for a completed application mismatch,2 for infrastructure/input/output failure, or128+signal for accepted cancellation. Unlike the legacy smoke harness, inventory-smoke.sh deliberately retains a completed naive exit1 capture. Unexpected statuses remain partial and stop the harness with2. Check actual status receipts; a standalone capture never establishes producer completion.

State directories must be new; the sample leaves its append-only journals for review. Faults affect only its own service child. This validates a controlled process-crash/retry case, not arbitrary applications, concurrent writers, torn journal recovery, VM/power loss, general transaction durability or distributed exactly-once execution. See [application validation](../docs/inventory-validation.md).

## Legacy IPC runner
Source authored against QNX 8.0 primary documentation. **Locally compiled and exercised on QNX 8.0.0 x86_64 under QEMU on November 3, 2026.** See [the validation record](../docs/native-validation.md) for exact tooling, observations and limits. Host Python tests alone do not qualify this runner.

Use a licensed QNX SDP 8.0 shell. For an x86_64 QEMU image:
```sh
make -C native
```
The Makefile invokes qcc with variant gcc_ntox86_64. Verify installed variants with qcc -V; override QNX_VARIANT for another supported target only after checking its SDK. Record qcc version/variant/build output separately with native evidence.

Transfer native/faultlab_probe and native/smoke.sh to a disposable QNX 8.0 target directory using your normal approved copy method. No SDK, image, license or credentials belong in the source repository.
```sh
chmod +x faultlab_probe smoke.sh
sh smoke.sh ./faultlab_probe ./first-run
```
Transfer first-run/ to the host, then:
```sh
python -m faultlab report first-run/capture.ndjson --out artifacts/native-first-run
```

The executable spawns its own tiny example server, creates a fresh channel for each exchange, observes MsgSend, and reaps each owned child. Healthy reply; intentional stalled reply with ETIMEDOUT; server exit while client blocked with ESRCH; fresh service/connection recovery for the two failure drills. Host contract also recognizes EBADF as a declared stale-connection outcome, but the native exit-after-receive drill specifically expects ESRCH and returns failure otherwise.

TimerTimeout covers SEND and REPLY using CLOCK_MONOTONIC and SIGEV_UNBLOCK. Channels omit _NTO_CHF_UNBLOCK to permit the timeout to unblock the client. Request duration records start/completion timestamps; no target scheduling or hard real-time guarantee follows from the measurement.

SIGINT/SIGTERM set an interruption flag; bounded operations return and atexit cleans the owned child. Cancellation is checked through final cleanup and output. A late interruption can occur after the last complete record has been written, so NDJSON alone cannot certify that the producer exited successfully.

The canonical smoke harness writes to capture.partial.ndjson and publishes capture.ndjson only after producer exit 0, with native-exit-code.txt retained. Failed/interrupted producer output stays partial diagnostic material even if its bytes are structurally complete. Discard it as qualification evidence; keep it for investigation. Transfer the entire smoke directory as well as the host report, and check the exit receipt. Synthetic handoff regressions and local native interruption/cleanup checks are recorded separately; these checks do not cover every possible scheduling interleaving.

Run only in the disposable sample context. No arbitrary PID, service, command, credentials or remote-fault flag exists. No production attachment is supported.

Primary references:
- [MsgSend](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/m/msgsend.html)
- [TimerTimeout](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/t/timertimeout.html)
- [QNX QEMU setup](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti_qemu/about.html)
