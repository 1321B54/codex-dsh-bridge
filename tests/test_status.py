"""Status, billing-event accounting and a loopback live probe. Never real credentials/API."""
from contextlib import contextmanager, redirect_stdout, ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import io
import json
import os
import socket
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bridge
from run_metrics import RunMetrics, failure_category

USAGE = {"inputTokens": 10, "outputTokens": 5, "cacheReadTokens": 3,
         "cacheWriteTokens": 2, "totalTokens": 20}


def event(kind, data=None, seq=None, session="test-session"):
    value = {"type": kind, "data": data or {}}
    if seq is not None:
        value["seq"] = seq
    return SimpleNamespace(method="session.event", payload={"sessionId": session, "event": value})


class AccountingTests(unittest.TestCase):
    def test_sums_disjoint_usage_once_and_ignores_duplicate_and_other_sessions(self):
        metrics = RunMetrics("test-session")
        notification = event("assistant/message", {"usage": USAGE,
            "stream": [{"type": "chunk", "chunk": {"type": "usage", "usage": USAGE}}]}, seq=1)
        metrics.observe(notification)
        metrics.observe(notification)
        metrics.observe(event("assistant/message", {"usage": USAGE}, seq=2))
        metrics.observe(event("assistant/message", {"usage": USAGE}, seq=3, session="foreign"))
        state = metrics.snapshot()
        self.assertEqual(state["reported_model_requests"], 2)
        self.assertEqual(state["usage"]["input_tokens"], 20)
        self.assertEqual(state["usage"]["cache_tokens"], 10)
        self.assertEqual(state["usage"]["prompt_tokens"], 30)
        self.assertEqual(state["usage"]["total_tokens"], 40)

    def test_failed_attempt_uses_last_cumulative_stream_counter(self):
        metrics = RunMetrics("test-session")
        metrics.observe(event("assistant/attempt", {"stream": [
            {"type": "chunk", "chunk": {"type": "usage", "usage": {**USAGE, "outputTokens": 1}}},
            {"type": "chunk", "chunk": {"type": "usage", "usage": USAGE}},
            {"type": "chunk", "chunk": {"type": "finish", "reason": {"kind": "max-tokens"}}}]}))
        self.assertEqual(metrics.snapshot()["usage"]["total_tokens"], 20)
        self.assertEqual(metrics.snapshot()["last_finish_reason"], "max-tokens")

    def test_missing_usage_is_null_and_partial_usage_is_labelled(self):
        metrics = RunMetrics("test-session")
        self.assertIsNone(metrics.snapshot()["usage"]["total_tokens"])
        self.assertEqual(metrics.snapshot()["usage_status"], "not_reported")
        metrics.observe(event("assistant/message", {"usage": USAGE}))
        metrics.observe(event("step/start"))
        self.assertEqual(metrics.snapshot()["usage_status"], "partial")
        self.assertEqual(metrics.snapshot()["usage"]["total_tokens"], 20)

    def test_unknown_transport_code_classified_without_recording_message(self):
        metrics = RunMetrics("test-session")
        metrics.observe(event("turn/end", {"reason": {"kind": "error", "error": {
            "code": "UNKNOWN", "message": "fetch failed: private-error-message"}}}))
        self.assertEqual(metrics.snapshot()["provider_failure_category"], "network")
        self.assertNotIn("private-error-message", json.dumps(metrics.snapshot()))

    def test_final_max_tokens_after_retry_supersedes_previous_network_error(self):
        metrics = RunMetrics("test-session")
        metrics.observe(event("assistant/attempt", {"stream": [{"type": "chunk", "chunk": {
            "type": "finish", "reason": {"kind": "error", "failure": {"code": "TRANSPORT"}}}}]}))
        metrics.observe(event("assistant/message", {"usage": USAGE, "stream": [{"type": "chunk", "chunk": {
            "type": "finish", "reason": {"kind": "max-tokens"}}}]}))
        metrics.observe(event("turn/end", {"reason": {"kind": "max-tokens"}}))
        state = metrics.snapshot()
        self.assertEqual(state["last_finish_reason"], "max-tokens")
        self.assertIsNone(state["provider_failure_category"])
        self.assertIsNone(state["provider_error_code"])
        self.assertEqual(state["usage"]["total_tokens"], 20)
        self.assertEqual(state["usage_status"], "partial")

    def test_failure_classes_are_distinct_and_rate_limit_is_not_balance(self):
        cases = [({"code": "AUTH", "status": 401}, "authentication"),
                 ({"code": "QUOTA", "status": 402}, "quota"),
                 ({"code": "RATE_LIMIT", "status": 429}, "rate_limit"),
                 ({"code": "NETWORK"}, "network"), ({"code": "TRANSPORT"}, "network"),
                 ({"reason": "max-tokens"}, "max_tokens"),
                 ({"reason": "model-step-guard"}, "model_step_guard"),
                 ({"reason": "timeout"}, "timeout"), ({"status": 503}, "provider"),
                 ({"message": "something failed"}, "runtime")]
        for facts, expected in cases:
            with self.subTest(facts=facts):
                self.assertEqual(failure_category(**facts), expected)


class DispatchTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="status-unit-") as folder, ExitStack() as stack:
            root = Path(folder)
            state = root / "state"
            state.mkdir()
            workspaces = root / "workspaces"
            stack.enter_context(patch.object(bridge, "STATE", state))
            stack.enter_context(patch.object(bridge, "get_token", return_value="dummy-unit-credential-not-real"))
            stack.enter_context(patch.object(bridge, "workspace_path", side_effect=lambda name, settings: workspaces / name))
            stack.enter_context(patch.object(bridge, "probe_network", return_value={
                "status": "passed", "http_status": 405, "error_codes": [], "timed_out": False}))
            yield root, state

    def test_doctor_is_explicitly_offline_and_never_runs_a_prompt(self):
        with self.fixture(), patch.object(bridge, "get_token", side_effect=AssertionError("doctor must not read a credential")):
            @contextmanager
            def offline(options):
                yield SimpleNamespace()
            output = io.StringIO()
            with patch.object(bridge, "managed_harness", side_effect=offline), redirect_stdout(output):
                bridge.doctor()
            result = json.loads(output.getvalue())
            self.assertEqual(result["doctor_mode"], "offline")
            self.assertEqual(result["model_requests_submitted"], 0)
            self.assertIsNone(result["paid_model_tasks"])
            self.assertIsNone(result["credential_valid"])
            self.assertIsNone(result["api_reachable"])
            self.assertEqual(result["live_acceptance"], "not_checked")

    def test_verify_missing_credential_never_dispatches(self):
        with self.fixture() as (_, state), patch.object(bridge, "TOKEN", state / "absent-token"), \
                patch.object(bridge, "get_token", side_effect=bridge.BridgeError("No token configured")), \
                patch.object(bridge, "execute_task") as dispatch:
            output = io.StringIO()
            with redirect_stdout(output):
                code = bridge.verify_live()
            dispatch.assert_not_called()
            result = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertEqual(result["failure_category"], "credential_missing")
            self.assertEqual(result["live_acceptance"], "not_checked")
            self.assertIsNone(result["usage"]["total_tokens"])

    def test_timeout_recovers_checkpoint_into_result_and_rework_remains_compatible(self):
        with self.fixture() as (root, state):
            settings = bridge.config()
            previous = []
            def dispatch(request, timeout):
                previous.append(request)
                metrics = RunMetrics(request["session_id"])
                metrics.observe(event("step/start", session=request["session_id"]))
                metrics.observe(event("assistant/message", {"usage": USAGE,
                    "stream": [{"type": "chunk", "chunk": {"type": "finish", "reason": {"kind": "tool-calls"}}}]}, session=request["session_id"]))
                metrics.observe(event("step/start", session=request["session_id"]))
                bridge.save_json(state / "runs" / request["run_id"] / "metrics.json", metrics.snapshot())
                return 124, {"type": "error", "failure_category": "timeout", "message": "Wall-clock timeout"}
            with patch.object(bridge, "supervise", side_effect=dispatch):
                code, outcome = bridge.execute_task("task", "Offline fixture", settings, "dummy-unit-credential-not-real")
                self.assertEqual(code, 124)
                self.assertEqual(outcome["model_steps"], 2)
                self.assertEqual(outcome["usage"]["total_tokens"], 20)
                self.assertEqual(outcome["usage_status"], "partial")
                self.assertEqual(outcome["last_finish_reason"], "tool-calls")
                self.assertTrue(outcome["session_id"])
                saved = json.loads((state / "runs" / outcome["run_id"] / "result.json").read_text())
                self.assertEqual(saved, outcome)
                _, rework = bridge.execute_task("task", "New contract", settings, "dummy-unit-credential-not-real", outcome["session_id"])
                self.assertNotEqual(rework["session_id"], outcome["session_id"])
                self.assertEqual(rework["continued_from"], outcome["session_id"])
                self.assertIn("Wall-clock timeout", previous[-1]["task"])

    def test_worker_step_guard_preserves_thirteenth_step_prior_usage_and_redacts_token(self):
        with self.fixture() as (_, state):
            run_id = "a" * 32
            run_dir = state / "runs" / run_id
            run_dir.mkdir(parents=True)
            credential = "dummy-unit-credential-not-real"
            class Harness:
                def run(self, task, session_id, on_notification):
                    for step in range(1, 14):
                        on_notification(event("step/start", session=session_id))
                        on_notification(event("assistant/message", {"usage": USAGE,
                            "message": {"content": [{"type": "text", "text": credential}]},
                            "stream": [{"type": "chunk", "chunk": {"type": "finish", "reason": {"kind": "tool-calls"}}}]}, session=session_id))
                        on_notification(event("step/end", session=session_id))
            @contextmanager
            def harness(options):
                yield Harness()
            request = {"workspace": "task", "run_id": run_id, "session_id": "test-session", "task": "Dummy"}
            output = io.StringIO()
            with patch.object(bridge, "managed_harness", side_effect=harness), patch.object(bridge.sys, "stdin", io.StringIO(json.dumps(request))), redirect_stdout(output):
                code = bridge.worker()
            result = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertEqual(result["failure_category"], "model_step_guard")
            self.assertEqual(result["model_steps"], 13)
            self.assertEqual(result["usage"]["total_tokens"], 240)
            self.assertEqual(result["last_finish_reason"], "tool-calls")
            self.assertEqual(result["session_id"], "test-session")
            self.assertNotIn(credential, output.getvalue() + (run_dir / "metrics.json").read_text() + (run_dir / "progress.jsonl").read_text())

    def test_error_and_result_redaction_includes_nonprefixed_encoded_key(self):
        dummy = "dummy-fixture-credential-not-real"
        value = {"message": dummy, "diagnostic": base64.b64encode(dummy.encode()).decode(), "nested": [dummy.encode().hex()]}
        redacted = json.dumps(bridge.redact_result(value, dummy))
        for secret in (dummy, value["diagnostic"], value["nested"][0]):
            self.assertNotIn(secret, redacted)


class LiveProbeTests(unittest.TestCase):
    def exercise(self, status=200, stop="end_turn", reply=bridge.VERIFY_REPLY, live=True, output_tokens=5):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                if status == "disconnect":
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if status != 200:
                    error_type = {401: "authentication_error", 402: "insufficient_balance", 429: "rate_limit_error", 503: "api_error"}[status]
                    data = json.dumps({"type": "error", "error": {"type": error_type, "message": error_type}}).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                else:
                    events = [
                        ("message_start", {"type": "message_start", "message": {"id": "msg_offline", "type": "message", "role": "assistant", "model": "deepseek-flash", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0, "cache_read_input_tokens": 3, "cache_creation_input_tokens": 2}}}),
                        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": reply}}),
                        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": output_tokens}}),
                        ("message_stop", {"type": "message_stop"}),
                    ]
                    data = "".join(f"event: {name}\ndata: {json.dumps(value)}\n\n" for name, value in events).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        if status == "network":
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        original_options = bridge.harness_options
        try:
            with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="live-offline-") as folder, ExitStack() as stack:
                root = Path(folder)
                state = root / "state"
                state.mkdir()
                caller = root / "caller"
                caller.mkdir()
                marker = caller / "AGENTS.md"
                marker.write_text("PRIVATE_CALLER_MARKER_DO_NOT_SEND")
                stack.enter_context(patch.object(bridge, "STATE", state))
                stack.enter_context(patch.object(bridge, "get_token", return_value="dummy-loopback-token-not-real"))
                stack.enter_context(patch.object(bridge, "workspace_path", side_effect=lambda name, settings: root / "workspaces" / name))
                def options(*args):
                    value = original_options(*args)
                    value["base_url"] = f"http://127.0.0.1:{server.server_port}"
                    value["env"] = bridge.clean_environment()
                    return value
                stack.enter_context(patch.object(bridge, "harness_options", side_effect=options))
                def dispatch(request, timeout):
                    stream = io.StringIO()
                    with patch.object(bridge.sys, "stdin", io.StringIO(json.dumps(request))), redirect_stdout(stream):
                        code = bridge.worker()
                    return code, json.loads(stream.getvalue())
                stack.enter_context(patch.object(bridge, "supervise", side_effect=dispatch))
                # Change cwd explicitly to prove callers need not be bridge projects.
                previous_cwd = Path.cwd()
                os.chdir(caller)
                try:
                    output = io.StringIO()
                    with redirect_stdout(output):
                        if live:
                            code = bridge.verify_live()
                        else:
                            contract = root / "contract.md"
                            contract.write_text("One short offline test response")
                            code = bridge.run_task(SimpleNamespace(workspace="normal", task_file=str(contract), continue_from=None))
                finally:
                    os.chdir(previous_cwd)
                result = json.loads(output.getvalue())
                result_path = state / "verify-live.json" if live else state / "runs" / result["run_id"] / "result.json"
                self.assertEqual(json.loads(result_path.read_text()), result)
                self.assertEqual(marker.read_text(), "PRIVATE_CALLER_MARKER_DO_NOT_SEND")
                self.assertEqual({p.name for p in caller.iterdir()}, {"AGENTS.md"})
                self.assertEqual(len(requests), 0 if status == "network" else 1, "No retries or second model step expected")
                if requests:
                    if live:
                        self.assertFalse(requests[0].get("tools"), "No model tools may be offered")
                    else:
                        self.assertTrue(requests[0].get("tools"), "Normal run tools remain available")
                    self.assertEqual(requests[0]["max_tokens"], 393216)
                    self.assertEqual(requests[0]["model"], "deepseek-flash")
                self.assertNotIn("PRIVATE_CALLER_MARKER_DO_NOT_SEND", json.dumps(requests))
                self.assertNotIn("dummy-loopback-token-not-real", json.dumps(requests) + output.getvalue())
                if result.get("live_acceptance") == "passed":
                    self.assertEqual((Path(result["workspace"]) / "verified.txt").read_text(), bridge.VERIFY_REPLY + "\n")
                return code, result
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_real_runtime_single_request_probe_and_usage(self):
        code, result = self.exercise()
        self.assertEqual(code, 0)
        self.assertTrue(result["credential_valid"])
        self.assertTrue(result["api_reachable"])
        self.assertEqual(result["live_acceptance"], "passed")
        self.assertEqual(result["finish_reason"], "completed")
        self.assertEqual(result["model_steps"], 1)
        self.assertEqual(result["usage"]["total_tokens"], 20)
        self.assertEqual(result["usage"]["cache_tokens"], 5)

    def test_normal_run_accepts_output_beyond_previous_8192_limit(self):
        reply = "OFFLINE_LONG_OUTPUT " * 9000
        code, result = self.exercise(live=False, reply=reply, output_tokens=9000)
        self.assertEqual(code, 0)
        self.assertEqual(result["finish_reason"], "completed")
        self.assertEqual(result["usage"]["output_tokens"], 9000)
        self.assertEqual(result["final_response"].strip(), reply.strip())

    def test_real_runtime_max_tokens_keeps_usage_and_finish_reason(self):
        code, result = self.exercise(stop="max_tokens")
        self.assertEqual(code, 2)
        self.assertEqual(result["failure_category"], "max_tokens")
        self.assertEqual(result["last_finish_reason"], "max-tokens")
        self.assertEqual(result["model_steps"], 1)
        self.assertEqual(result["usage"]["total_tokens"], 20)
        self.assertTrue(result["credential_valid"])
        self.assertTrue(result["api_reachable"])
        self.assertEqual(result["live_acceptance"], "failed")

    def test_real_runtime_auth_quota_rate_and_provider_errors_do_not_retry(self):
        for status, category in ((401, "authentication"), (402, "quota"), (429, "rate_limit"), (503, "provider")):
            with self.subTest(status=status):
                code, result = self.exercise(status=status)
                self.assertEqual(code, 2)
                self.assertEqual(result["failure_category"], category)
                self.assertTrue(result["api_reachable"])
                self.assertEqual(result["live_acceptance"], "failed")
                self.assertIsNone(result["usage"]["total_tokens"])
                self.assertEqual(result["credential_valid"], False if status == 401 else None)

    def test_normal_run_provider_error_does_not_retry_six_times(self):
        code, result = self.exercise(status=503, live=False)
        self.assertEqual(code, 2)
        self.assertEqual(result["failure_category"], "provider")
        self.assertEqual(result["model_attempts"], 1)

    def test_failed_preflight_blocks_model_dispatch_with_actionable_error(self):
        code, result = self.exercise(status="network", live=False)
        self.assertEqual(code, 2)
        self.assertEqual(result["finish_reason"], "network-preflight")
        self.assertEqual(result["model_requests_submitted"], 0)
        self.assertEqual(result["model_attempts"], 0)
        self.assertEqual(result["model_steps"], 0)
        self.assertIn("ECONNREFUSED", result["network_diagnostics"]["error_codes"])
        self.assertIsNone(result["usage"]["total_tokens"])

    def test_transport_failure_after_preflight_keeps_safe_runtime_cause_and_does_not_retry(self):
        code, result = self.exercise(status="disconnect", live=False)
        self.assertEqual(code, 2)
        self.assertEqual(result["network_preflight"]["status"], "passed")
        self.assertEqual(result["failure_category"], "network")
        self.assertEqual(result["model_attempts"], 1)
        self.assertTrue(set(result["network_diagnostics"]["error_codes"]) & {"UND_ERR_SOCKET", "ECONNRESET"})
        self.assertIsNone(result["usage"]["total_tokens"])

    def test_probe_rejects_unexpected_response_without_acceptance(self):
        code, result = self.exercise(reply="Unexpected response")
        self.assertEqual(code, 2)
        self.assertEqual(result["failure_category"], "verification_failed")
        self.assertEqual(result["live_acceptance"], "failed")
        self.assertFalse(result["workspace_verified"])

    def test_real_runtime_network_failure_has_unknown_credential_and_usage(self):
        code, result = self.exercise(status="network")
        self.assertEqual(code, 2)
        self.assertEqual(result["failure_category"], "network")
        self.assertFalse(result["api_reachable"])
        self.assertIsNone(result["credential_valid"])
        self.assertIsNone(result["usage"]["total_tokens"])

    def test_normal_run_result_includes_own_usage_without_changing_tool_access(self):
        for stop, finish, expected_code in (("end_turn", "completed", 0), ("max_tokens", "max-tokens", 2)):
            with self.subTest(stop=stop):
                code, result = self.exercise(live=False, stop=stop)
                self.assertEqual(code, expected_code)
                self.assertEqual(result["finish_reason"], finish)
                self.assertEqual(result["last_finish_reason"], finish)
                self.assertEqual(result["usage"]["total_tokens"], 20)
                self.assertEqual(result["model_steps"], 1)
                self.assertEqual(result["usage_status"], "reported")
                self.assertTrue(result["session_id"])


if __name__ == "__main__":
    unittest.main()
