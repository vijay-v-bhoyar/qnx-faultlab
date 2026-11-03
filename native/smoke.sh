#!/bin/sh
# Acceptance harness for an isolated, licensed QNX 8.0 target.
# NOT executed by host tests. Captures stay native observations, not synthetic fixtures.
set -eu
probe=${1:-./faultlab_probe}
output=${2:-./faultlab-native-smoke}
if [ -e "$output" ]; then
    printf '%s\n' "Refusing existing output: $output" >&2
    exit 2
fi
mkdir "$output"
"$probe" --version > "$output/tool-version.txt"
uname -a > "$output/target.txt"
if "$probe" --timeout-ms 250 > "$output/capture.partial.ndjson" 2> "$output/diagnostics.txt"; then
    printf '%s\n' 0 > "$output/native-exit-code.txt"
    mv "$output/capture.partial.ndjson" "$output/capture.ndjson"
else
    probe_exit=$?
    printf '%s\n' "$probe_exit" > "$output/native-exit-code.txt"
    printf '%s\n' "Native producer failed (exit $probe_exit); retaining partial bytes for diagnosis only." >&2
    exit "$probe_exit"
fi
if "$probe" --timeout-ms 0 > "$output/invalid-args.stdout" 2> "$output/invalid-args.stderr"; then
    printf '%s\n' "FAIL: invalid timeout was accepted" >&2
    exit 1
else
    invalid_exit=$?
    if [ "$invalid_exit" -ne 2 ]; then
        printf '%s\n' "FAIL: invalid timeout must exit 2" >&2
        exit 1
    fi
fi
printf '%s\n' "Capture completed. Transfer this directory and validate capture.ndjson with the host CLI."
printf '%s\n' "Retain native-exit-code.txt with the capture; NDJSON alone does not certify producer success."
printf '%s\n' "This harness does not by itself establish interruption cleanup or unrelated-process isolation."
