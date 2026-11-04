#!/bin/sh
# Run both owned application variants; retain complete failed-contract evidence.
set -u
if [ "$#" -ne 2 ]; then
    echo "usage: inventory-smoke.sh PRODUCER NEW_OUTPUT_DIR" >&2
    exit 2
fi
producer=$1
out=$2
if ! mkdir "$out"; then exit 2; fi
uname -a > "$out/target.txt" || exit 2
"$producer" --version > "$out/tool-version.txt" || exit 2
for mode in naive idempotent; do
    case_dir=$out/$mode
    mkdir "$case_dir" || exit 2
    "$producer" --implementation "$mode" --state-dir "$case_dir/state" > "$case_dir/capture.partial.ndjson" 2> "$case_dir/diagnostics.txt"
    code=$?
    printf '%s\n' "$code" > "$case_dir/native-exit-code.txt" || exit 2
    expected=0
    if [ "$mode" = naive ]; then expected=1; fi
    if [ "$code" -ne "$expected" ]; then
        echo "$mode producer exit $code, expected $expected; partial evidence retained" >&2
        exit 2
    fi
    mv "$case_dir/capture.partial.ndjson" "$case_dir/capture.ndjson" || exit 2
done
echo "Native pair retained: naive contract FAIL (1), idempotent PASS (0)."
echo "Analyze BOTH captures on the host; retain state journals and actual exit receipts."
