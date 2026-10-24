"""Opt-in, process-local additional CA trust; never disables TLS validation."""
import hashlib
from pathlib import Path, PureWindowsPath
import re
import ssl


def with_local_ca(base: Path, launch: dict, environment: dict) -> dict:
    """Load only an explicitly approved, hash-pinned public CA from local state.

    Approval/export is a separate local administrative operation. Nothing is
    auto-discovered or imported into the operating system's certificate store.
    """
    env = dict(environment)
    name = launch.get("extra_ca_file")
    expected = launch.get("extra_ca_sha256")
    if name is None and expected is None:
        return env
    if (not isinstance(name, str) or not name or not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected) is None):
        raise RuntimeError("Additional CA requires a local state file and SHA-256 approval.")
    relative = Path(name)
    if (relative.root or PureWindowsPath(name).drive or PureWindowsPath(name).root
            or ".." in relative.parts or ".." in PureWindowsPath(name).parts):
        raise RuntimeError("Additional CA must stay inside local state.")
    state = base / ".state"
    candidate = state / relative
    # Do not follow symlinks/junctions even if their current destination is local.
    for path in (candidate, *candidate.parents):
        if path == base:
            break
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise RuntimeError("Additional CA cannot use linked state paths.")
    target = candidate.resolve(strict=True)
    if not target.is_relative_to(state.resolve(strict=True)) or not target.is_file():
        raise RuntimeError("Additional CA must be a regular local state file.")
    with target.open("rb") as stream:
        data = stream.read(128 * 1024 + 1)
    if len(data) > 128 * 1024 or hashlib.sha256(data).hexdigest() != expected.lower():
        raise RuntimeError("Additional CA does not match its approved SHA-256.")
    text = data.decode("ascii")
    if (text.count("-----BEGIN CERTIFICATE-----") != 1
            or "PRIVATE KEY" in text):
        raise RuntimeError("Additional CA must contain one public certificate, not a key.")
    # Parse the PEM before handing it to Node; an invalid/missing approval fails
    # closed instead of Node merely warning and continuing without the CA.
    ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=text)
    previous = env.get("NODE_EXTRA_CA_CERTS")
    if previous and Path(previous).resolve() != target:
        raise RuntimeError("Additional CA conflicts with inherited Node trust configuration.")
    env["NODE_EXTRA_CA_CERTS"] = str(target)
    return env
