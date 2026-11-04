# Security boundary
FaultLab is a local prototype for its own disposable example service, not a production fault injector.

The host CLI reads a user-selected bounded capture and writes a new user-selected directory. Capture text cannot select output paths, execute commands, fetch URLs or produce executable HTML. Reports have no scripts, remote assets or network service. The SHA-256 is an integrity aid, not an authenticity signature.

The native runner signals only a PID returned from its own fork and retains it only until reaping. Interruption/setup failures are non-success and can produce incomplete captures. Local QNX 8.0.0/QEMU checks observed owned-child cleanup after SIGINT, SIGTERM and a closed output pipe; a separate harness-owned sentinel remained alive. See [native validation](docs/native-validation.md) for the exercised cases and limits. One VM and these schedules do not establish exhaustive isolation or hardware timing guarantees.

Do not import sensitive or proprietary traces into a public evidence bundle. The examples include labeled synthetic fixtures and the retained local QNX capture documented in the validation record. FaultLab does not automatically publish or transmit reports.

Existing output paths, symlinks and junctions are refused. This does not claim isolation against another privileged process concurrently manipulating the local filesystem. Use a directory you control.

If you find a security issue, contact the repository owner privately before disclosing sensitive details; never attach credentials or proprietary SDK material.
