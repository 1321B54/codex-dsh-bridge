"""Private Linux guardian: clean a worker process group even if its coordinator dies."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading


def main() -> int:
    lifetime_fd = int(sys.argv[1])
    # DSH shell runners start their own sessions. Adopt orphaned grandchildren so
    # they remain discoverable by ancestry even after setsid() or worker death.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0):  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "Unable to enable Linux child supervision")
    # Only the guardian retains the read end. No child inherits the lifetime pipe.
    process = subprocess.Popen(sys.argv[2:], start_new_session=True)

    cleanup_lock = threading.Lock()

    def descendants():
        parents = {}
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                try:
                    fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                    parents[int(entry.name)] = (int(fields[1]), fields[0])
                except (OSError, ValueError, IndexError):
                    pass  # Process exited during enumeration.
        found = {os.getpid()}
        while True:
            added = {pid for pid, (parent, _) in parents.items() if parent in found} - found
            if not added:
                break
            found.update(added)
        return {pid for pid in found if pid != os.getpid() and parents[pid][1] != "Z"}

    def stop_group(*_args):
        # Freeze before killing to prevent ordinary child-spawn races. This is
        # lifecycle management for a trusted account, not a hostile-process jail.
        with cleanup_lock:
            for _ in range(10):
                targets = descendants()
                if not targets:
                    break
                for sig in (signal.SIGSTOP, signal.SIGKILL):
                    for pid in targets:
                        try:
                            os.kill(pid, sig)
                        except ProcessLookupError:
                            pass
            kill_group()

    def kill_group():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def watch_coordinator():
        try:
            while os.read(lifetime_fd, 1):
                pass
        finally:
            stop_group()
            os.close(lifetime_fd)

    def handle_signal(*_args):
        # A signal can interrupt cleanup on this same thread; avoid reacquiring
        # its non-reentrant lock. An in-progress cleanup already owns the tree.
        if cleanup_lock.locked():
            kill_group()
        else:
            stop_group()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    threading.Thread(target=watch_coordinator, daemon=True).start()
    try:
        returncode = process.wait()
        return returncode if returncode >= 0 else 128 - returncode
    finally:
        stop_group()
        # Reap adopted children rather than leaving zombies for the desktop's PID 1.
        while True:
            try:
                os.waitpid(-1, 0)
            except ChildProcessError:
                break


if __name__ == "__main__":
    raise SystemExit(main())
