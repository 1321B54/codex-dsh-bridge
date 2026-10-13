#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "$root/.venv/bin/python" "$root/runtime-launch.py" "$@"
