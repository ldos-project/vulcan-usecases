#!/usr/bin/env bash
# Build libvulcan (if missing) and the multi-region policy .so.
#
# Usage:
#   ./build.sh                    # uses base_policy.cpp as the evolve block
#   ./build.sh /path/to/code.cpp  # uses the given file as the evolve block
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
VULCAN_ROOT="$REPO_ROOT/third_party/libvulcan"
VULCAN_BUILD="$VULCAN_ROOT/build"

rm -f "$HERE/cbl_multi_policy.so"

if [[ ! -f "$VULCAN_BUILD/libvulcan.so" ]]; then
  echo ">>> building libvulcan"
  cmake -S "$VULCAN_ROOT" -B "$VULCAN_BUILD"
  cmake --build "$VULCAN_BUILD" -j
fi

EVOLVE_SRC="${1:-$HERE/base_policy.cpp}"
cp "$EVOLVE_SRC" "$HERE/LLMCode.h"

echo ">>> building cbl_multi_policy.so (evolve block: $EVOLVE_SRC)"
g++ -std=c++20 -O2 -shared -fPIC \
  -I "$VULCAN_ROOT/include" \
  -I "$HERE" \
  -L "$VULCAN_BUILD" -lvulcan \
  -Wl,-rpath,"$VULCAN_BUILD" \
  "$HERE/cbl_multi_policy.cpp" \
  -o "$HERE/cbl_multi_policy.so"

echo "Built: $HERE/cbl_multi_policy.so"
