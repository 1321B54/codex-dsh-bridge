import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import bridge


class BridgeUnitTests(unittest.TestCase):
    def test_shared_agent_home_is_task_local(self):
        home = bridge.STATE / "test-isolated-home"
        options = bridge.harness_options(bridge.BASE, home, bridge.config())
        self.assertEqual(options["env"]["DSH_AGENTS_HOME"], str(home / "agents"))

    def test_config_matches_installed_version(self):
        self.assertEqual(bridge.config()["sdk_version"], "0.2.1rc2")

    def test_valid_workspace(self):
        root = bridge.BASE / ".workspaces"
        self.assertEqual(bridge.workspace_path("test_01", bridge.config()), (root / "test_01").resolve())

    def test_rejects_workspace_paths_and_reserved_names(self):
        for value in ("../escape", r"C:\secret", ".", "", "CON", "com1", "a/b", "a\\b", "a.b"):
            with self.subTest(value=value), self.assertRaises(bridge.BridgeError):
                bridge.workspace_path(value, bridge.config())

    def test_rejects_unreviewed_root(self):
        cfg = bridge.config()
        cfg["workspace_root"] = "."
        with self.assertRaises(bridge.BridgeError):
            bridge.workspace_path("example", cfg)

    def test_rejects_junction_task_root(self):
        self.check_junction_boundary(root_alias=True)

    def test_rejects_junction_workspace_escape(self):
        self.check_junction_boundary(root_alias=False)

    def check_junction_boundary(self, root_alias):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="junction-test-") as folder:
            fixture = Path(folder).resolve()
            base = fixture / "bridge"
            base.mkdir()
            outside = fixture / "outside"
            outside.mkdir()
            root = base / ".workspaces"
            alias = root if root_alias else root / "example"
            if not root_alias:
                root.mkdir()
            if os.name == "nt":
                command = subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"),
                                          "/c", "mklink", "/J", str(alias), str(outside)], capture_output=True)
                self.assertEqual(command.returncode, 0, command.stderr)
            else:
                alias.symlink_to(outside, target_is_directory=True)
            try:
                with patch.object(bridge, "BASE", base), self.assertRaises(bridge.BridgeError):
                    bridge.workspace_path("example", {"workspace_root": ".workspaces"})
            finally:
                # Remove only the known fixture junction, never its destination.
                os.rmdir(alias) if os.name == "nt" else alias.unlink()

    def test_redacts_exact_key_and_key_patterns(self):
        self.assertEqual(bridge.redact("secret-value", "secret-value"), "[REDACTED]")
        self.assertNotIn("sk-", bridge.redact("a sk-0123456789abcdef0123 z"))

    def test_environment_scrubs_unrelated_credentials(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret", "DEEPSEEK_API_KEY": "test-secret",
                                    "DSH_PERMISSION_MODE": "danger-full-access"}):
            env = bridge.clean_environment()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("DEEPSEEK_API_KEY", env)
        self.assertEqual(env["DSH_PERMISSION_MODE"], "workspace-write")
        self.assertEqual(env["DSH_TELEMETRY_DISABLED"], "1")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_dpapi_roundtrip_without_real_token(self):
        value = b"offline-unit-test-not-a-real-token"
        cipher = bridge.dpapi(value)
        self.assertNotIn(value, cipher)
        self.assertEqual(bridge.dpapi(cipher, decrypt=True), value)

    def test_no_token_fails_before_task_execution(self):
        with patch.object(bridge, "TOKEN", bridge.STATE / "does-not-exist-test.dpapi"):
            with self.assertRaises(bridge.BridgeError):
                bridge.get_token()

    def test_actual_nonprefixed_credential_rejected_before_dispatch(self):
        dummy = "fixture-nonprefixed-credential-not-real"
        with tempfile.TemporaryDirectory(dir=bridge.STATE) as folder:
            task = Path(folder) / "task.md"
            task.write_text("Never transmit " + dummy, encoding="utf-8")
            args = SimpleNamespace(workspace="credential-reject", task_file=str(task), continue_from=None)
            with patch.object(bridge, "get_token", return_value=dummy), patch.object(bridge, "supervise") as dispatch:
                with self.assertRaises(bridge.BridgeError):
                    bridge.run_task(args)
                dispatch.assert_not_called()

    def test_token_input_refuses_noninteractive_pipe(self):
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(bridge.BridgeError):
                bridge.set_token()

    def test_profile_has_no_automatic_escalation(self):
        content = bridge.PATCH.read_text(encoding="utf-8")
        self.assertNotIn("danger-full-access", content)
        for item in ("policy: never", "mode: workspace-write", "id: session-log-deepseek",
                     "id: session-telemetry-otel", "id: tool-subagent"):
            self.assertIn(item, content)

    def test_harness_options_use_full_sdk_and_matching_directory(self):
        opts = bridge.harness_options(Path("C:/task"), Path("C:/state"), bridge.config())
        self.assertEqual(opts["profile"], "sdk")
        self.assertEqual(opts["cwd"], opts["runtime_cwd"])
        self.assertEqual(opts["model"], "deepseek-flash")
        self.assertEqual(opts["max_tokens"], 393216)

    def test_step_start_is_counted(self):
        notification = SimpleNamespace(method="session.event", payload={"event": {"type": "step/start"}})
        self.assertEqual(bridge.count_model_step(notification, 0, 12), 1)

    def test_step_guard_rejects_thirteenth_step(self):
        notification = SimpleNamespace(method="session.event", payload={"event": {"type": "step/start"}})
        with self.assertRaises(bridge.BridgeError):
            bridge.count_model_step(notification, 12, 12)

    def test_other_events_do_not_consume_step_limit(self):
        for method, event in (("session.status", {}), ("session.event", {"type": "assistant/message"})):
            notification = SimpleNamespace(method=method, payload={"event": event})
            self.assertEqual(bridge.count_model_step(notification, 3, 12), 3)

    @unittest.skipUnless(os.name == "nt", "Windows Job")
    def test_windows_job_stops_descendant_processes(self):
        script = ("import subprocess,sys,time; sys.stdin.readline(); "
                  "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                  "print(p.pid,flush=True); time.sleep(60)")
        parent = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        job = None
        try:
            job = bridge.WindowsJob(parent)
            parent.stdin.write("start\n")
            parent.stdin.flush()
            child_pid = int(parent.stdout.readline())
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x100000, False, child_pid)
            self.assertTrue(handle)
            try:
                job.close()
                parent.wait(timeout=5)
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                kernel.CloseHandle(handle)
        finally:
            if job:
                job.close()
            if parent.poll() is None:
                parent.kill()
            parent.communicate()

    def test_supervisor_collects_worker_result(self):
        script = "import sys,json; sys.stdin.read(); print(json.dumps({'type':'result','model_completed':True}))"
        with patch.object(bridge, "worker_command", return_value=[sys.executable, "-c", script]):
            code, result = bridge.supervise({"task": "offline fixture"}, 5)
        self.assertEqual(code, 0)
        self.assertTrue(result["model_completed"])

    def test_supervisor_timeout_is_failure(self):
        script = "import sys,time; sys.stdin.read(); time.sleep(60)"
        with patch.object(bridge, "worker_command", return_value=[sys.executable, "-c", script]):
            code, result = bridge.supervise({"task": "offline fixture"}, 0.2)
        self.assertEqual(code, 124)
        self.assertEqual(result["type"], "error")

    def test_supervisor_rejects_malformed_output(self):
        script = "import sys; sys.stdin.read(); print('not JSON')"
        with patch.object(bridge, "worker_command", return_value=[sys.executable, "-c", script]):
            code, result = bridge.supervise({"task": "offline fixture"}, 5)
        self.assertEqual(code, 2)
        self.assertEqual(result["type"], "error")


if __name__ == "__main__":
    unittest.main()
