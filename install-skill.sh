#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${DSH_PYTHON:-python3}" "$root/install-skill.py" "$@"
