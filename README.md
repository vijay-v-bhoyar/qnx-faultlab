# QNX FaultLab
**A service restarted. Did it apply your request twice?**

FaultLab pairs owned native QNX 8.0 services with a dependency-free Python analyzer and offline report. Its application demo commits an inventory reservation, crashes before replying, and retries the same operation after restart. The naive implementation double-reserves stock; the idempotent implementation recognizes the persisted operation. FaultLab checks actual stock and committed-operation counts, not just whether a fresh process answers. The original healthy/stall/exit IPC drills remain supported.

**Current validation:** the inventory application compiled with licensed SDP8.0 and completed three actual QNX8.0.0 x86_64/QEMU bad/good pairs on November4,2026. The host flags duplicate application in each naive run and verifies the corrected state; the final target ELF matches the compiled binary. See [application validation](docs/inventory-validation.md). The earlier IPC runner's three smoke/interruption/closed-pipe checks remain in [legacy validation](docs/native-validation.md), including the SDK finding. This is a prototype, not a qualified fault-injection or safety tool.

![Actual native duplicate-reservation failure report](assets/report-inventory-native.png)

## Guided tutorial
Learn to [detect duplicate application after a lost QNX reply](docs/faultlab-codelab.md) using retained native naive/corrected captures, their journals, and an optional fresh-target run.

## Inspect the application failure and correction
Use Python 3.10+ from this source directory:
```sh
python -m faultlab report samples/native-inventory-20261104/naive/capture.ndjson --out artifacts/inventory-naive
python -m faultlab report samples/native-inventory-20261104/idempotent/capture.ndjson --out artifacts/inventory-idempotent
```
The first command intentionally exits **1** and retains its FAIL report; the second exits **0**. Run both commands separately if your shell stops on a nonzero exit. Open both index.html files. A restarted service initially reports stock7 in both runs. Retrying operation101 changes naive stock to4 (wrong), while the corrected service leaves7. A distinct operation102 then leaves2 versus the required5. The report exposes operation IDs, quantities, remaining stock, applied counts and duplicate recognition.

These commands replay retained QNX bytes; they do not run QNX on the host. Keep the entire [native application sample](samples/native-inventory-20261104), including actual producer exits and journals. See [application validation](docs/inventory-validation.md) for the exact build, target, evidence and limits. This remains a controlled sample, not an adapter for arbitrary services.

## Try the host report
From this source directory, use Python 3.10 or newer (locally exercised with Python 3.12 on Windows):
```sh
python -m faultlab report samples/expected.synthetic.ndjson --out artifacts/first-report
```
Open artifacts/first-report/index.html in a browser. It needs no server, network, account or JavaScript. Keep summary.json and source.ndjson beside the HTML when sharing the report.

Try a deliberately mismatched recovery:
```sh
python -m faultlab report samples/failed-recovery.synthetic.ndjson --out artifacts/failed-example
```
This produces a report and exits **1**. An expected timeout can pass a drill; failed recovery cannot.

Choose a new output directory on every run. Existing files/directories and symbolic-link/junction output paths are refused, preserving prior work. No runtime dependency installation is needed.

## Run real QNX drills
See [native instructions](native/README.md) and the [official QNX QEMU guide](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti_qemu/about.html).
A licensed QNX SDP 8.0 toolchain and disposable QNX 8.0 target are required. The current QSTI/QEMU guide uses Ubuntu 22.04 or 24.04. Do not assume a Windows or WSL host is qualified merely because QEMU is available.

The native source:
- Creates only its own disposable example server processes and channels.
- Uses QNX MsgSend/MsgReceive/MsgReply and TimerTimeout for bounded observations.
- Recreates a fresh service/connection after the two failure drills.
- Emits ordered NDJSON; the smoke harness publishes a completed capture only after producer exit 0 and retains failed output separately.
- Offers no arbitrary PID/service/remote-command interface.

Use your own approved target console/copy workflow; FaultLab never collects SDK credentials or executes remote commands.

Inspect the retained native smoke capture without installing the SDK:
```sh
python -m faultlab report samples/native-smoke-20261103/capture.ndjson --out artifacts/native-example
```
Keep its neighboring producer exit receipt and target/version files. This replays a retained observation; it does not run QNX on your machine.

## Inspect without a report
```sh
python -m faultlab validate samples/expected.synthetic.ndjson
python -m faultlab --help
python -m unittest discover -v
```
Exit codes: **0** valid capture with matched contracts; **1** valid capture with a contract mismatch; **2** input/schema/IO/usage error. Codes 0/1 are not native-authenticity or production-readiness claims.

Input is bounded to 16 MiB and 10,000 records, with strict version, field, type, sequence and timing checks. Duplicate keys, nonfinite values, unsupported text, incomplete sessions and unknown schemas are rejected.

## Evidence and limits
The report retains exact capture bytes and their SHA-256. That detects changes; it does **not** authenticate who produced a capture. A qnx-native header is a producer declaration until the actual target/toolchain/run is independently checked. Files named synthetic are authored fixtures; samples/native-smoke-20261103 contains the retained local QNX run described in the validation record. Neither the header nor the host report authenticates that provenance by itself.

For native evidence, retain the entire smoke output, including native-exit-code.txt. A late failed/interrupted producer can leave structurally complete bytes; the canonical harness keeps those under capture.partial.ndjson rather than publishing capture.ndjson. A host contract verdict alone never certifies producer success.

Timing is measured on the declared target and does not establish hardware hard real-time guarantees. The three sample drills do not qualify an arbitrary service, kernel, production deployment, medical device or vehicle.

No runtime AI or external provider is used. Codex assisted design, source authoring, tests and documentation. No customer interviews, human usability study or measured productivity benefit has been completed.

## Source and maintenance
- [Native build and capture](native/README.md)
- [Capture format and architecture](docs/capture-format.md)
- [Source provenance](docs/provenance.md)
- [Security boundary](SECURITY.md)
- License: [MIT](LICENSE). QNX SDK, images and components remain under their own licenses and are not distributed here.
