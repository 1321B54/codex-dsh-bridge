"""Linux credential permissions and real detached-process cleanup; no API calls."""
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import bridge


@unittest.skipUnless(sys.platform == "linux", "Linux-specific behavior")
class LinuxTests(unittest.TestCase):
    def test_hidden_dummy_credential_roundtrip_and_private_permissions(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            state = Path(folder) / "private-state"
            token = state / "token.credentials"
            with patch.object(bridge, "STATE", state), patch.object(bridge, "TOKEN", token), \
                    patch.object(sys.stdin, "isatty", return_value=True), \
                    patch.object(bridge.getpass, "getpass", return_value="offline-dummy-not-a-real-token"):
                bridge.set_token()
                self.assertEqual(bridge.get_token(), "offline-dummy-not-a-real-token")
                self.assertEqual(state.stat().st_mode & 0o777, 0o700)
                self.assertEqual(token.stat().st_mode & 0o777, 0o600)

    def test_credential_rejects_public_mode_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            state = Path(folder)
            token = state / "token.credentials"
            source = state / "source"
            source.write_text("offline-dummy-not-a-real-token")
            source.chmod(0o600)
            with patch.object(bridge, "STATE", state), patch.object(bridge, "TOKEN", token):
                token.write_bytes(source.read_bytes())
                token.chmod(0o644)
                with self.assertRaises(bridge.BridgeError):
                    bridge.get_token()
                token.unlink()
                token.symlink_to(source)
                with self.assertRaises(OSError):
                    bridge.get_token()
                token.unlink()
                os.link(source, token)
                with self.assertRaises(bridge.BridgeError):
                    bridge.get_token()

    def test_state_symlink_is_rejected_without_changing_destination(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            target = Path(folder) / "target"
            target.mkdir(mode=0o755)
            target.chmod(0o755)
            alias = Path(folder) / "alias"
            alias.symlink_to(target, target_is_directory=True)
            with patch.object(bridge, "STATE", alias), self.assertRaises(bridge.BridgeError):
                bridge.protect_state()
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)

    def test_linux_environment_keeps_home_and_locale_but_not_injected_options(self):
        with patch.dict(os.environ, {"HOME": "/tmp/dummy-home", "LANG": "C.UTF-8",
                                    "NODE_OPTIONS": "--require=untrusted.js", "BASH_ENV": "/tmp/untrusted",
                                    "LD_PRELOAD": "/tmp/untrusted.so", "AWS_SECRET_ACCESS_KEY": "dummy"}):
            env = bridge.clean_environment()
        self.assertEqual(env["HOME"], "/tmp/dummy-home")
        self.assertEqual(env["LANG"], "C.UTF-8")
        for key in ("NODE_OPTIONS", "BASH_ENV", "LD_PRELOAD", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(key, env)

    def assert_stopped(self, pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
            except FileNotFoundError:
                return
            if state == "Z":
                return
            time.sleep(0.05)
        self.fail(f"Fixture descendant {pid} survived cleanup")

    def child_script(self, pid_file, finish=False):
        return ("import subprocess,sys,time,json; from pathlib import Path; sys.stdin.read(); "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True); "
                f"Path({str(pid_file)!r}).write_text(str(p.pid)); "
                + ("print(json.dumps({'type':'result','model_completed':True}))" if finish else "time.sleep(60)"))

    def test_timeout_cleans_detached_descendant(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            pid_file = Path(folder) / "child.pid"
            script = self.child_script(pid_file)
            with patch.object(bridge, "worker_command", return_value=[sys.executable, "-c", script]):
                code, outcome = bridge.supervise({"task": "offline fixture"}, 1)
            self.assertEqual(code, 124)
            self.assertEqual(outcome["type"], "error")
            self.assert_stopped(int(pid_file.read_text()))

    def test_completion_cleans_detached_descendant(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            pid_file = Path(folder) / "child.pid"
            script = self.child_script(pid_file, finish=True)
            with patch.object(bridge, "worker_command", return_value=[sys.executable, "-c", script]):
                code, outcome = bridge.supervise({"task": "offline fixture"}, 5)
            self.assertEqual(code, 0)
            self.assertTrue(outcome["model_completed"])
            self.assert_stopped(int(pid_file.read_text()))

    def test_coordinator_sigkill_cleans_detached_descendant(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            pid_file = Path(folder) / "child.pid"
            worker = self.child_script(pid_file)
            coordinator = ("import bridge,sys; "
                           f"bridge.worker_command=lambda: [sys.executable,'-c',{worker!r}]; "
                           "bridge.supervise({'task':'offline fixture'},60)")
            process = subprocess.Popen([sys.executable, "-c", coordinator], cwd=bridge.BASE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pid_file.exists(), "Fixture worker did not initialize")
                process.kill()
                process.wait(timeout=5)
                self.assert_stopped(int(pid_file.read_text()))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)

    def test_interrupt_returns_130_and_cleans_detached_descendant(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            pid_file = Path(folder) / "child.pid"
            result_file = Path(folder) / "outcome.json"
            worker = self.child_script(pid_file)
            coordinator = ("import bridge,sys,json; from pathlib import Path; "
                           f"bridge.worker_command=lambda: [sys.executable,'-c',{worker!r}]; "
                           "code,outcome=bridge.supervise({'task':'offline fixture'},60); "
                           f"Path({str(result_file)!r}).write_text(json.dumps([code,outcome]))")
            process = subprocess.Popen([sys.executable, "-c", coordinator], cwd=bridge.BASE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pid_file.exists(), "Fixture worker did not initialize")
                process.send_signal(signal.SIGINT)
                process.wait(timeout=5)
                code, outcome = json.loads(result_file.read_text())
                self.assertEqual(code, 130)
                self.assertEqual(outcome["type"], "error")
                self.assert_stopped(int(pid_file.read_text()))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
