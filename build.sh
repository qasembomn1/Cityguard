#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PYINSTALLER="$ROOT_DIR/cityguard/bin/pyinstaller"

if [[ -x "$LOCAL_PYINSTALLER" ]]; then
    PYINSTALLER="$LOCAL_PYINSTALLER"
else
    PYINSTALLER="${PYINSTALLER:-pyinstaller}"
fi

exec "$PYINSTALLER" --noconfirm --clean "$ROOT_DIR/Cityguard.spec"
