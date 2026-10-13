"""Resolve the local bridge without modifying the caller's project or reinstalling."""
import argparse
import json
import os
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "run"), nargs="?", default="doctor")
    parser.add_argument("--workspace")
    parser.add_argument("--task-file", type=Path)
    parser.add_argument("--continue-from")
    args = parser.parse_args()
    skill = Path(__file__).resolve().parent.parent
    mapping = skill / "bridge-location.json"
    root = Path(json.loads(mapping.read_text(encoding="utf-8-sig"))["bridge_root"]) if mapping.is_file() else skill.parent.parent
    if not root.is_absolute():
        raise RuntimeError("The DSH bridge path must be absolute.")
    python = root / ".venv" / "bin" / "python"
    for file in (python, root / "bridge.py", root / "safe-profile.patch.yml"):
        if not file.is_file():
            raise RuntimeError(f"DSH installation is missing: {file}. No automatic reinstall or permission fallback.")
    command = [str(python), str(root / "bridge.py"), args.command]
    if args.command == "run":
        if not args.workspace or not args.task_file:
            raise RuntimeError("A paid run requires an explicit workspace and task contract.")
        contract = args.task_file.resolve(strict=True)
        if not contract.is_file():
            raise RuntimeError("Task contract must be a file.")
        command.extend(("--workspace", args.workspace, "--task-file", str(contract)))
        if args.continue_from:
            command.extend(("--continue-from", args.continue_from))
    os.execv(str(python), command)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
