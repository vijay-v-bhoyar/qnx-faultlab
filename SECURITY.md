# Security boundary
FaultLab is a local prototype for its own disposable example service, not a production fault injector.

The host CLI reads a user-selected bounded capture and writes a new user-selected directory. Capture text cannot select output paths, execute commands, fetch URLs or produce executable HTML. Reports have no scripts, remote assets or network service. The SHA-256 is an integrity aid, not an authenticity signature.

Both native runners signal only a PID returned from their own fork and retain it only until reaping. Interruption/setup failures are non-success and can produce incomplete captures. The legacy IPC runner's QNX8.0.0/QEMU checks observed cleanup after SIGINT, SIGTERM and a closed pipe; see [legacy validation](docs/native-validation.md). The inventory runner separately passed a closed-reader cleanup check with an unrelated owned sentinel alive; see [application validation](docs/inventory-validation.md). Do not transfer the legacy signal checks to the new runner or infer exhaustive scheduling/isolation guarantees.

The inventory sample creates a new caller-selected state directory and retains its operation journal. It rejects existing state directories. Use an owned parent directory. It has no production connection or generic database adapter. Its process-crash journal is not hardened for concurrent writers, corruption, interrupted disk writes or power loss.

Do not import sensitive or proprietary traces into a public evidence bundle. The examples include labeled synthetic fixtures and the retained local QNX capture documented in the validation record. FaultLab does not automatically publish or transmit reports.

Existing output paths, symlinks and junctions are refused. This does not claim isolation against another privileged process concurrently manipulating the local filesystem. Use a directory you control.

If you find a security issue, contact the repository owner privately before disclosing sensitive details; never attach credentials or proprietary SDK material.
