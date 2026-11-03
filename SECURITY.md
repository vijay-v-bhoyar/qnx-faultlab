# Security boundary
FaultLab is a local prototype for its own disposable example service, not a production fault injector.

The host CLI reads a user-selected bounded capture and writes a new user-selected directory. Capture text cannot select output paths, execute commands, fetch URLs or produce executable HTML. Reports have no scripts, remote assets or network service. The SHA-256 is an integrity aid, not an authenticity signature.

The native runner signals only a PID returned from its own fork and retains it only until reaping. Interruption/setup failures are non-success and can produce incomplete captures. Native process-isolation and cleanup behavior still needs actual QNX validation.

Do not import sensitive or proprietary traces into a public evidence bundle. The included examples use self-authored synthetic observations. FaultLab does not automatically publish or transmit reports.

Existing output paths, symlinks and junctions are refused. This does not claim isolation against another privileged process concurrently manipulating the local filesystem. Use a directory you control.

If you find a security issue, contact the repository owner privately before disclosing sensitive details; never attach credentials or proprietary SDK material.
