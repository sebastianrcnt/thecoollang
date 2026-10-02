#!/bin/sh
# Verify compiler convergence without replacing the committed seed.
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
tools/native/prepare.sh
mkdir -p build/bootstrap
compiler=$ROOT/coolc/seed/Compiler.BIN
for generation in 1 2 3; do
    output=$ROOT/build/bootstrap/gen$generation.BIN
    if ! COOLC_COMPILER_BIN="$compiler" gtimeout 90 build/coolc \
        build/native-src/Native.cool "$output" > "$output.log" 2>&1; then
        tail -20 "$output.log"
        exit 1
    fi
    grep -q 'Errs:0 ' "$output.log"
    echo "compiler generation $generation: PASS"
    compiler=$output
done
cmp build/bootstrap/gen2.BIN build/bootstrap/gen3.BIN
echo 'bootstrap convergence (gen2 == gen3): PASS'
