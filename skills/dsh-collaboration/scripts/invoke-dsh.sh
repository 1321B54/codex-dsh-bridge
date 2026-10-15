#!/bin/bash
set -euo pipefail
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${DSH_PYTHON:-python3}" "$scripts/invoke-dsh.py" "$@"
