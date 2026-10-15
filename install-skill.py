"""Install the portable user skill on Linux without replacing an existing directory."""
import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

BASE = Path(__file__).resolve().parent
FILES = ("SKILL.md", "agents/openai.yaml", "scripts/invoke-dsh.ps1",
         "scripts/invoke-dsh.sh", "scripts/invoke-dsh.py", "references/operations.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=Path.home() / ".agents" / "skills")
    args = parser.parse_args()
    if sys.platform != "linux":
        raise RuntimeError("Use Install-Skill.ps1 on Windows.")
    root = args.skill_root
    if not root.is_absolute():
        raise RuntimeError("Skill root must be absolute.")
    destination = root / "dsh-collaboration"
    if os.path.lexists(destination):
        raise RuntimeError("A skill already exists here. Preserve it; choose another skill root or review a manual replacement.")
    source = BASE / "skills" / "dsh-collaboration"
    for file in FILES:
        if not (source / file).is_file():
            raise RuntimeError(f"Skill source is incomplete: {file}")
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".dsh-skill-stage-", dir=root))
    for file in FILES:
        target = stage / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / file, target)
    (stage / "bridge-location.json").write_text(json.dumps({"bridge_root": str(BASE)}), encoding="utf-8")
    # RENAME_NOREPLACE: even an empty directory created concurrently is preserved.
    if rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1):
        code = ctypes.get_errno()
        message = "Existing skill preserved" if code == errno.EEXIST else os.strerror(code)
        raise RuntimeError(f"{message}; staging retained for inspection at {stage}")
    print("User-level skill installed; no credential copied and no model request made.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Skill installation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
