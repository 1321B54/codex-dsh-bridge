"""Launch the pinned official Node runtime without using the older SEA executable."""
import json
import os
from pathlib import Path
import subprocess
import sys
from runtime_trust import with_local_ca

base = Path(__file__).resolve().parent
try:
    launch = json.loads((base / ".state" / "runtime-launch.json").read_text(encoding="utf-8-sig"))
    node = Path(launch["node_path"])
    shell = Path(launch["pwsh_path"] if os.name == "nt" else launch["bash_path"])
    package = base / "node_modules" / "@deepseek-ai" / "dsh"
    installed = json.loads((package / "package.json").read_text(encoding="utf-8"))["version"]
    expected = json.loads((base / "config.json").read_text(encoding="utf-8"))["runtime_version"]
    if installed != expected or not node.is_absolute() or not shell.is_absolute() or not node.is_file() or not shell.is_file():
        raise RuntimeError("Reviewed Node, shell or DSH runtime is missing; no fallback permitted.")
    env = with_local_ca(base, launch, os.environ)
    env["PATH"] = os.pathsep.join((str(node.parent), str(shell.parent), env.get("PATH", "")))
    # Inherit JSON-RPC pipes directly; no stdout decoration and no intermediate file.
    command = [str(node), str(package / "lib" / "bin.js"), *sys.argv[1:]]
    if sys.platform == "linux":
        os.execve(str(node), command, env)
    raise SystemExit(subprocess.call(command, env=env))
except Exception as exc:
    print("DSH launcher failed: " + str(exc), file=sys.stderr)
    raise SystemExit(2)
