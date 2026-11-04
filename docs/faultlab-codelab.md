# Inspect QNX client failures without losing the recovery evidence

This self-paced guide is for a QNX developer or reviewer who wants to answer a specific question: when a sample service stalls or exits, what did the client observe, and did a fresh service return the correct reply afterward?

You will analyze a retained QNX 8.0 run, inspect the original observations, and compare it with a deliberately failed recovery. An optional final section explains how to capture a new run on your own disposable QNX target. This guide was authored during the hackathon submission period in November 2026.

## What you need

For the retained-capture steps, download or clone this repository and open a terminal in its root. Use Python 3.10 or newer. No SDK, server, account, package installation or runtime AI service is needed for these steps. Commands below use `python`; substitute your Python 3 command if your platform names it differently.

Keep every output path new. FaultLab refuses existing output directories, symlinks and junctions so that a later run cannot overwrite an earlier result. If you already used a path below, choose a new name consistently throughout the guide.

Creating a new native capture additionally requires your own licensed QNX SDP 8.0 toolchain and an isolated QNX 8.0 target. SDK packages, images and licenses are not included here. Do not target production services.

## 1. Predict what should count as success

FaultLab's runner creates its own tiny services and exercises three client contracts. Before running the report, predict which of these should pass:

| Drill | Expected client observation | Recovery requirement |
|---|---|---|
| Healthy exchange | Correct echo reply | Owned service is cleaned up |
| Stalled reply | ETIMEDOUT from the request | A fresh service returns the correct payload; cleanup completes |
| Service exit | Server/connection loss; the retained native run observes ESRCH | A fresh service returns the correct payload; cleanup completes |

A timeout is expected in the stalled drill. A successful verdict also requires the recovery reply to be correct. Receiving any reply is insufficient.

## 2. Generate a report from retained native observations

Run from the repository root:

```sh
python -m faultlab report samples/native-smoke-20261103/capture.ndjson --out artifacts/codelab-native
```

Expected command exit: **0**. The terminal identifies a PASS and a qnx-native capture. Open `artifacts/codelab-native/index.html` in a browser. Keep `summary.json` and `source.ndjson` beside it; the report uses no JavaScript or network assets.

The overview should show **3 / 3 matched**, declared QNX 8.0.0 target information, a configured timeout of 250 ms and a source SHA-256. This command reads retained bytes; it does not execute QNX on your host. The public sample's actual build/run and producer-exit record are described in [native validation](native-validation.md).

The DECLARED QNX CAPTURE banner is deliberate. A source-kind label, a successful host analysis and a digest do not authenticate native execution. The analyzer's `native_execution_verified` field remains false even when separate target evidence exists.

## 3. Inspect the stalled client's recovery

Find **Stalled reply** and open **Inspect original observations**. Follow the rows in order:

1. `request`: outcome `timeout`, error `ETIMEDOUT`; the request did not verify a reply payload.
2. `recovery_request`: outcome `reply`, payload verified `true`; the detail names a fresh owned sample.
3. `cleanup`: outcome `clean`.

The request's configured timeout and observed duration are different concepts. QEMU scheduling and the recorded elapsed values do not establish hardware real-time guarantees. The table rounds displayed milliseconds; original nanosecond values remain in the capture.

Now open the **Service exit** observations. The retained run's request records `server_gone` with `ESRCH`; its recovery row records a verified reply from a fresh sample. The broader host contract recognizes declared ESRCH/EBADF server-connection-loss outcomes, while the native runner's specific exit-after-receive drill expects ESRCH.

**Checkpoint:** explain why an expected request error can coexist with a passing drill, and why a fresh reply with the wrong payload must fail. The next step makes that distinction visible.

## 4. Compare a failed recovery

```sh
python -m faultlab report samples/failed-recovery.synthetic.ndjson --out artifacts/codelab-mismatch
```

Expected command exit: **1**. This is the deliberate contract mismatch, and the report is retained. Open `artifacts/codelab-mismatch/index.html` and confirm its **SYNTHETIC EXAMPLE** banner. This authored fixture is not a second native experiment.

Select **Needs attention (1)**. Only the mismatched stalled-reply drill should remain. Expand its observations: the initial request still has ETIMEDOUT, but `recovery_request` has outcome `reply` and payload verified `false`. The failure explains that recovery did not produce a verified echo reply. The two other contracts match.

Return to **All drills** to compare them. This is the practical distinction the report is designed to preserve: the original request outcome and the recovery result are separate observations.

## 5. Check the handoff, not just the green verdict

Use the native report's **Open analysis JSON** and **Open original capture** links. The JSON gives the pinned analysis; the raw file preserves the input bytes. Check those bytes directly from your terminal:

```sh
python -c "from pathlib import Path; import hashlib; original=Path('samples/native-smoke-20261103/capture.ndjson').read_bytes(); retained=Path('artifacts/codelab-native/source.ndjson').read_bytes(); print('Exact bytes:', original==retained); print('SHA-256:', hashlib.sha256(retained).hexdigest())"
```

Expected `Exact bytes: True`. For this frozen public sample the SHA-256 is `b637913f3ac2f759ebff21829f9d62e2c28b34de0deaf90802520a4b73735adb`.

Keep the entire neighboring `samples/native-smoke-20261103/` directory when evaluating the native record, including `native-exit-code.txt`, target, version and diagnostics. The producer exit receipt is 0 for this sample. The host verdict alone does not prove that a producer completed successfully.

For a handoff, share the whole generated report directory plus the original capture's run/status context. A digest can detect changed bytes; it does not identify who produced them.

## 6. Optional: capture a new disposable QNX run

This section uses the already implemented native sample, not an adapter for an arbitrary service. In your own configured licensed SDP environment, build from the repository root:

```sh
make -C native
```

The Makefile uses qcc variant `gcc_ntox86_64`, C11 and warnings-as-errors. Follow [native setup and run instructions](../native/README.md) for the supported target/context and record your actual toolchain and target. Transfer `native/faultlab_probe` and `native/smoke.sh` into a new directory on your disposable QNX 8.0 x86_64 target. In that target directory:

```sh
sh smoke.sh ./faultlab_probe ./fresh-codelab
cat fresh-codelab/native-exit-code.txt
```

Stop and investigate if the harness fails. Only a successful producer exit 0 publishes `capture.ndjson`; failed producer bytes remain `capture.partial.ndjson` for diagnosis. Retain partial bytes and actual exit codes, even if a partial file appears structurally complete. The harness also checks invalid timeout rejection, but does not by itself prove interruption cleanup or unrelated-process isolation.

Transfer the **complete** `fresh-codelab` directory back to the source root using your approved copy method. On the host, with a new output path:

```sh
python -m faultlab report fresh-codelab/capture.ndjson --out artifacts/codelab-fresh
```

Inspect the actual result rather than assuming it will match this repository's sample. Keep producer/harness status and toolchain/target records alongside the report. Existing local validation covers one disposable VM and specific cleanup cases; it is not exhaustive scheduling, hardware or production qualification.

## Why these are QNX observations

The runner uses ChannelCreate/ConnectAttach and MsgSend/MsgReceive/MsgReply. It configures TimerTimeout for SEND and REPLY blocking around the client exchange. It starts a fresh owned service/connection for recovery and reaps its own children. See [the native source](../native/faultlab_probe.c) and the QNX references for [MsgSend](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/m/msgsend.html) and [TimerTimeout](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/t/timertimeout.html).

This host report is useful for inspecting that QNX-specific contract; it is not a live monitor or authenticity verifier. The SDK terminal-database verification finding and original validation limits remain disclosed in [native validation](native-validation.md). No measured productivity benefit, human usability result, general service recovery or safety claim follows from completing this tutorial.

## Troubleshooting

| Observation | Action |
|---|---|
| Output already exists | Choose a new output directory; preserve the previous evidence |
| Deliberate synthetic mismatch exits 1 | Expected in step 4; open the retained failed report |
| Exit 2 | Read the diagnostic; input/schema/IO/usage checks failed, so do not interpret it as an analyzed native outcome |
| Native receipt is nonzero or capture is partial | Keep it as diagnostic evidence; resolve the producer/target failure before qualifying a new capture |
| No native SDK/target available | Complete steps 1-5 with retained data; do not label that replay as a fresh QNX run |
