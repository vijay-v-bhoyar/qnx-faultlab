# Native QNX probe
Source authored against QNX 8.0 primary documentation. **Native compile/runtime validation is pending.** Host Python tests do not qualify this runner.

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

The canonical smoke harness writes to capture.partial.ndjson and publishes capture.ndjson only after producer exit 0, with native-exit-code.txt retained. Failed/interrupted producer output stays partial diagnostic material even if its bytes are structurally complete. Discard it as qualification evidence; keep it for investigation. Transfer the entire smoke directory as well as the host report, and check the exit receipt. This handoff is tested with synthetic producers; actual QNX cleanup/interruption still requires native execution.

Run only in the disposable sample context. No arbitrary PID, service, command, credentials or remote-fault flag exists. No production attachment is supported.

Primary references:
- [MsgSend](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/m/msgsend.html)
- [TimerTimeout](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/t/timertimeout.html)
- [QNX QEMU setup](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti_qemu/about.html)
