#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ! -x "$root/.venv/bin/python" ]]; then
    echo 'Local DSH runtime is missing. Run ./setup.sh first.' >&2
    exit 2
fi
if [[ $# -eq 0 ]]; then set -- doctor; fi
exec "$root/.venv/bin/python" "$root/bridge.py" "$@"
