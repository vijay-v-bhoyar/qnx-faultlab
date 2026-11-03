# Local native validation, November 3, 2026

The runner source and smoke harness from commit f130727e7a299e9ea2b030cdb9712706b10c61db were exercised without source changes. This record describes one local disposable VM, not independent certification or general WSL support.

## Build and target

- Windows QNX Software Center 2.0.4:v202501021438; licensed SDP baseline com.qnx.qnx800/8.0.0.00141T202311271501L, conservative dependency selection, experimental packages/debug symbols disabled.
- Compiler variant 12.2.0,gcc_ntox86_64; `make -C native` used `-std=c11 -Wall -Wextra -Werror -O2`, exit 0, no warnings.
- Built ELF SHA-256: `86d372d293da8b7c3b6aec4e563be6ccac6f760dff6cfbbe4312626a13e05382`. An exported copy of the running target's executable matched the built file byte for byte. The executable is not distributed here.
- QNX Image Builder 0.5.0.00132T202605281115L generated an x86_64 QEMU image on Windows. Its local system-files snippet included the probe and smoke harness. Graphics disabled, 2 CPUs, 512 MiB RAM, default vendor security configuration.
- Ubuntu 24.04 WSL, QEMU 8.2.2+ds-0ubuntu1.18, KVM. QEMU used `-enable-kvm -cpu host -smp 2 -m 512 -kernel ifs.bin -drive file=disk-qemu.vmdk,if=ide,format=vmdk -snapshot -nic none -display none`. Only the disposable image was attached. A private local serial socket carried commands; no network interface, bridge, host port or remote target was used.
- Target: `QNX faultlab-disposable 8.0.0 2026/06/05-16:26:03EDT x86pc x86_64`.

The Windows-build/WSL-run combination was empirically exercised here. The [official mkqnximage documentation](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.utilities/topic/m/mkqnximage.html) lists Ubuntu in its supported QEMU host table; this local result does not extend the vendor's support matrix. The [installed package list](qnx-packages-20261103.txt) records all 222 selected package IDs and versions.

## Observations

| Check | Observed result |
|---|---|
| Three canonical smoke runs, timeout 250 ms | Producer and harness exit 0; host validation passes all three contracts in each capture |
| Healthy exchange | Correct echo payload |
| Stalled service | ETIMEDOUT, followed by correct reply from a fresh service |
| Exit after receive | ESRCH, followed by correct reply from a fresh service |
| Invalid timeout 0 | Exit 2 in each smoke harness |
| SIGINT while stalled | Parent observed in REPLY state; exit 130, observed child absent afterward |
| SIGTERM while stalled | Exit 143, observed child absent afterward |
| Output reader closes after six records | Exit 2, "Broken pipe" diagnostic, observed child absent afterward |
| Unrelated sentinel | Separate harness-owned sleep process remains alive after each interruption/pipe case |
| Final process snapshot | No residual faultlab_probe process |
| Partial interruption/pipe captures | Host validation rejects them with exit 2 |

The sentinel and VM were cleaned up after observation. Process snapshots and raw acceptance logs are retained locally; the repository includes the complete first smoke output directory. Captures alone do not authenticate execution. The host summary intentionally continues to report `native_execution_verified: false`; execution corroboration is a separate record.

## Replay and reproduce

Replay the retained capture on Python 3.10+:

```sh
python -m faultlab report samples/native-smoke-20261103/capture.ndjson --out artifacts/native-example
```

The retained producer exit is 0 and capture SHA-256 is `b637913f3ac2f759ebff21829f9d62e2c28b34de0deaf90802520a4b73735adb`. This creates a report from existing bytes; it does not execute a target.

For a fresh target run, obtain your own licensed SDP 8.0, inspect `qcc -V`, build using [native instructions](../native/README.md), and transfer the executable plus smoke.sh to an isolated QNX 8.0 x86_64 target. Run the canonical harness into a new directory and retain every output file and actual exit status. Repeat interruption and pipe tests only against the disposable runner and its own children. SDK packages, images, licenses and account material are excluded from this repository.

## SDK verification finding and limits

QSC's full-install verification exited 4 with 562 UnexpectedFile findings, all under target/qnx/usr/share/terminfo. Each flagged path matched an ncurses package-manifest entry when compared without case sensitivity, and every file's SHA-512 matched that manifest. This supports a Windows path-casing explanation; the vendor verification itself remains failed. No files were deleted, assertions disabled or SDK repair claimed. The build and native behavior above were observed despite that finding. The isolated image also logged absent-network-interface and sshd-auth startup diagnostics; neither network nor SSH was used.

Two console script-transfer attempts failed before acceptance execution; the QA driver was instead included in the image. The first QA-driver execution stopped because sha256sum was absent; a correction copied the target ELF for host digest comparison. A subsequent transfer-quoting error also failed before drills. Those failures are retained separately from the successful run; no product-source repair was needed.

These checks cover a sample service, one VM configuration and interruption during a stall. They do not establish exhaustive cancellation interleavings, hardware timing guarantees, arbitrary-service recovery, production readiness, safety certification, human usability or productivity benefit.
