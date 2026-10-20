"""Transport diagnostics and retry prevention; fake credentials and loopback only."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import io
import json
import subprocess
import tempfile
import threading
import unittest

import bridge
from run_metrics import RunMetrics


class NetworkTests(unittest.TestCase):
    def test_head_probe_has_no_credentials_body_or_redirect_following(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_HEAD(self):
                seen.append((self.path, dict(self.headers)))
                self.send_response(302)
                self.send_header("Location", "/must-not-follow")
                self.end_headers()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(bridge.os.environ, {"DEEPSEEK_API_KEY": "dummy-probe-must-not-send",
                                               "OPENAI_API_KEY": "dummy-openai-must-not-send"}):
                result = bridge.probe_network(f"http://127.0.0.1:{server.server_port}")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["http_status"], 302)
            self.assertEqual(len(seen), 1)
            path, headers = seen[0]
            self.assertEqual(path, "/v1/messages")
            self.assertNotIn("authorization", {k.lower() for k in headers})
            self.assertNotIn("dummy-", json.dumps(seen))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_nested_runtime_errors_only_emit_allowlisted_codes(self):
        node = json.loads((bridge.STATE / "runtime-launch.json").read_text(encoding="utf-8-sig"))["node_path"]
        module = str(bridge.BASE / "runtime-network.cjs")
        script = """
const secret = 'dummy-header-and-stack-secret';
globalThis.fetch = async () => {throw new Error(secret, {cause: new AggregateError([
  Object.assign(new Error(secret), {code:'ECONNRESET'}),
  Object.assign(new Error(secret), {code:secret})])});};
require(process.argv[1]);
fetch('https://api.deepseek.com/anthropic/v1/messages', {headers:{authorization:secret}}).catch(()=>{});
"""
        result = subprocess.run([node, "-e", script, module], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("dummy-header-and-stack-secret", result.stderr)
        self.assertNotIn("api.deepseek.com", result.stderr)
        facts = json.loads(result.stderr.removeprefix("DSH_NETWORK_FACTS "))
        self.assertEqual(facts, {"codes": ["ECONNRESET"], "phase": "request"})

    def test_diagnostic_reader_discards_unknown_text_urls_and_codes(self):
        secret = "dummy-private-token"
        harness = SimpleNamespace(client=SimpleNamespace(_stderr_lines=[
            secret,
            'DSH_NETWORK_FACTS ' + json.dumps({"codes": ["ECONNRESET", secret, {"token":secret}],
                "phase":"request", "message":secret, "url":"https://private.invalid/"}),
            'DSH_NETWORK_FACTS invalid-json',
        ]))
        metrics = RunMetrics("test")
        bridge.observe_runtime_network(harness, metrics)
        diagnostics = metrics.snapshot()["network_diagnostics"]
        self.assertEqual(diagnostics, {"error_codes": ["ECONNRESET"], "phases": ["request"]})
        self.assertNotIn(secret, json.dumps(metrics.snapshot()))

    def test_probe_timeout_and_invalid_launcher_output_are_safe(self):
        with patch.object(bridge.subprocess, "run", side_effect=subprocess.TimeoutExpired("dummy", 12)):
            result = bridge.probe_network("https://api.deepseek.com/anthropic")
        self.assertTrue(result["timed_out"])
        with patch.object(bridge.subprocess, "run", return_value=SimpleNamespace(
                stdout="dummy-untrusted-launcher-secret", returncode=2)):
            result = bridge.probe_network("https://api.deepseek.com/anthropic")
        self.assertTrue(result["probe_error"])
        self.assertNotIn("dummy-", json.dumps(result))

    def test_network_command_never_reads_credential_or_dispatches_model(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="network-unit-") as folder, \
                patch.object(bridge, "STATE", Path(folder)), \
                patch.object(bridge, "get_token", side_effect=AssertionError("credential read")), \
                patch.object(bridge, "managed_harness", side_effect=AssertionError("model dispatch")), \
                patch.object(bridge, "probe_network", return_value={"status":"failed",
                    "http_status":None, "error_codes":["ECONNRESET"], "timed_out":False}):
            output = io.StringIO()
            with redirect_stdout(output):
                code = bridge.check_network()
            result = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertEqual(result["model_requests_submitted"], 0)
            self.assertEqual(result["failure_category"], "network")
            self.assertIsNone(result["credential_valid"])
            self.assertEqual(json.loads((Path(folder) / "network-check.json").read_text()), result)


if __name__ == "__main__":
    unittest.main()
