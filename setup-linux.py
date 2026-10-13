"""Install only local, pinned Linux dependencies, then initialize without a model call."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent


def executable(name: str) -> Path:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Missing executable: {name}. Install it from its official source first.")
    # Keep symlink names: some CLI dispatchers use argv[0] to choose their behavior.
    return Path(os.path.abspath(found))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--bash", default="bash")
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() not in {"x86_64", "aarch64"}:
        raise RuntimeError("Linux x86_64/aarch64 with glibc is supported.")
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Python 3.14 is the tested version; set DSH_PYTHON to its executable.")
    os.umask(0o077)
    node, npm, bash = (executable(x) for x in (args.node, args.npm, args.bash))
    if bash.name != "bash":
        raise RuntimeError("The Bash executable must be named bash; DSH resolves it through PATH.")
    version = subprocess.check_output([str(node), "--version"], text=True).strip()
    if not version.startswith("v24."):
        raise RuntimeError("Node.js 24 is the tested version; use --node to select it.")
    subprocess.run([str(bash), "--version"], check=True, stdout=subprocess.DEVNULL)
    python = BASE / ".venv" / "bin" / "python"
    if not python.is_file():
        if (BASE / ".venv").exists():
            raise RuntimeError("Existing .venv is incomplete; preserve it and review a manual replacement.")
        subprocess.run([sys.executable, "-m", "venv", str(BASE / ".venv")], check=True)
    subprocess.run([str(python), "-c", "import sys; assert sys.version_info[:2] == (3,14), 'Existing virtualenv must use Python 3.14'"], check=True)
    subprocess.run([str(python), "-m", "pip", "--isolated", "install", "--index-url", "https://pypi.org/simple",
                    "--disable-pip-version-check", "--require-hashes", "--only-binary=:all:",
                    "-r", str(BASE / "requirements-linux.lock.txt")], check=True)
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join((str(node.parent), str(npm.parent), env.get("PATH", "")))
    subprocess.run([str(npm), "ci", "--ignore-scripts", "--no-audit", "--no-fund",
                    "--registry=https://registry.npmjs.org"], cwd=BASE, env=env, check=True)
    subprocess.run([str(python), "-c", "import bridge; bridge.protect_state()"], cwd=BASE, check=True)
    (BASE / ".state" / "runtime-launch.json").write_text(
        json.dumps({"node_path": str(node), "bash_path": str(bash)}, indent=2), encoding="utf-8")
    subprocess.run([str(python), str(BASE / "bridge.py"), "doctor"], cwd=BASE, check=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Linux setup failed: {exc}. No permission fallback performed.", file=sys.stderr)
        raise SystemExit(2)
