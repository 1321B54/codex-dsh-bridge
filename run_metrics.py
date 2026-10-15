"""Numeric-only accounting for the pinned DSH session event protocol."""
from __future__ import annotations

FIELDS = {
    "inputTokens": "input_tokens", "outputTokens": "output_tokens",
    "cacheReadTokens": "cache_read_tokens", "cacheWriteTokens": "cache_write_tokens",
    "totalTokens": "total_tokens", "reasoningTokens": "reasoning_tokens",
}
FINISH_REASONS = {"stop", "tool-calls", "completed", "max-tokens", "error", "aborted", "blocked"}
ERROR_CODES = {"AUTH", "INVALID_CREDENTIAL", "MISSING_CREDENTIAL", "QUOTA", "ACCOUNT_QUOTA",
               "RATE_LIMIT", "SERVER", "NETWORK", "TRANSPORT", "STREAM_CLOSED", "TIMEOUT", "ETIMEDOUT",
               "ECONNRESET", "ECONNREFUSED", "ENOTFOUND", "INVALID_REQUEST", "INVALID_RESPONSE"}


def counters(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return {name: value[key] for key, name in FIELDS.items()
            if type(value.get(key)) is int and value[key] >= 0}


class RunMetrics:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.model_steps = 0
        self.model_attempts = 0
        self.reported_requests = 0
        self.last_finish_reason = None
        self.error_code = None
        self.http_status = None
        self.error_category = None
        self.pending_step = False
        self.sums = {}
        self.seen = set()
        self.incomplete_usage = False

    def observe(self, notification) -> dict:
        """Consume a durable event once. Never retain text, tool arguments or credentials."""
        if notification.method != "session.event":
            return {}
        if notification.payload.get("sessionId", self.session_id) != self.session_id:
            return {}
        event = notification.payload.get("event", {})
        if not isinstance(event, dict):
            return {}
        seq = event.get("seq")
        if type(seq) is int:
            if seq in self.seen:
                return {}
            self.seen.add(seq)
        kind = event.get("type")
        data = event.get("data", {})
        if not isinstance(data, dict):
            data = {}
        if kind == "step/start":
            self.model_steps += 1
            self.pending_step = True
        elif kind == "step/end":
            self.pending_step = False
        if kind in {"assistant/message", "assistant/attempt"}:
            self.model_attempts += 1
            usage = counters(data.get("usage"))
            # Failed attempts may have no data.usage. Stream usage is cumulative:
            # take its LAST snapshot, not the sum of all snapshots or both copies.
            stream_usage = {}
            stream = data.get("stream", [])
            for record in stream if isinstance(stream, list) else []:
                chunk = record.get("chunk", {}) if isinstance(record, dict) else {}
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") == "usage":
                    stream_usage = counters(chunk.get("usage"))
                if chunk.get("type") == "finish":
                    self.observe_reason(chunk.get("reason"))
            usage = usage or stream_usage
            if usage:
                self.reported_requests += 1
                # The pinned SDK defines optional cache counters as disjoint input.
                for field in ("cache_read_tokens", "cache_write_tokens"):
                    usage.setdefault(field, 0)
                if "input_tokens" in usage and "output_tokens" in usage:
                    usage.setdefault("total_tokens", usage["input_tokens"] + usage["output_tokens"]
                                     + usage["cache_read_tokens"] + usage["cache_write_tokens"])
                else:
                    self.incomplete_usage = True
                for field, number in usage.items():
                    self.sums[field] = self.sums.get(field, 0) + number
            else:
                self.incomplete_usage = True
            return usage
        if kind == "turn/end":
            self.observe_reason(data.get("reason"))
        return {}

    def observe_reason(self, reason: object) -> None:
        if not isinstance(reason, dict):
            return
        if reason.get("kind") in FINISH_REASONS:
            self.last_finish_reason = reason["kind"]
            # A successful retry or output-limit finish supersedes an earlier
            # failed attempt. Do not mislabel its final reason with a stale AUTH,
            # QUOTA or TRANSPORT code from the same run.
            if reason["kind"] not in {"error", "aborted"}:
                self.error_code = None
                self.http_status = None
                self.error_category = None
        failure = reason.get("error", reason.get("failure"))
        if isinstance(failure, dict):
            if failure.get("code") in ERROR_CODES:
                self.error_code = failure["code"]
            status = failure.get("status")
            if type(status) is int and 100 <= status <= 599:
                self.http_status = status
            self.error_category = failure_category(code=failure.get("code"), status=self.http_status,
                                                   message=str(failure.get("message", "")))

    def snapshot(self) -> dict:
        usage = {field: self.sums.get(field) for field in FIELDS.values()}
        usage["cache_tokens"] = (usage["cache_read_tokens"] + usage["cache_write_tokens"]
                                  if usage["cache_read_tokens"] is not None and usage["cache_write_tokens"] is not None else None)
        usage["prompt_tokens"] = (usage["input_tokens"] + usage["cache_tokens"]
                                   if usage["input_tokens"] is not None and usage["cache_tokens"] is not None else None)
        status = ("not_reported" if not self.reported_requests else "partial"
                  if self.pending_step or self.incomplete_usage else "reported")
        return {"session_id": self.session_id, "model_steps": self.model_steps,
                "model_attempts": self.model_attempts, "reported_model_requests": self.reported_requests,
                "usage": usage, "usage_status": status, "last_finish_reason": self.last_finish_reason,
                "provider_error_code": self.error_code, "http_status": self.http_status,
                "provider_failure_category": self.error_category}


def failure_category(*, reason=None, code=None, status=None, message="") -> str:
    """Prefer structured provider facts; messages are a fallback for SDK transport errors."""
    if reason == "max-tokens":
        return "max_tokens"
    if reason == "model-step-guard":
        return "model_step_guard"
    if reason == "timeout":
        return "timeout"
    if reason in {"interrupted", "aborted"}:
        return "interrupted"
    if code in {"AUTH", "INVALID_CREDENTIAL"} or status in {401, 403}:
        return "authentication"
    if code in {"QUOTA", "ACCOUNT_QUOTA"} or status == 402:
        return "quota"
    if code == "RATE_LIMIT" or status == 429:
        return "rate_limit"
    if code in {"TIMEOUT", "ETIMEDOUT"}:
        return "timeout"
    if code in {"NETWORK", "TRANSPORT", "STREAM_CLOSED", "ECONNRESET", "ECONNREFUSED", "ENOTFOUND"}:
        return "network"
    if code == "MISSING_CREDENTIAL":
        return "credential_missing"
    if code == "SERVER" or (type(status) is int and status >= 500):
        return "provider"
    text = message.lower()
    if "model-step guard" in text:
        return "model_step_guard"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if any(word in text for word in ("fetch failed", "connection refused", "connection reset", "dns", "network", "stream closed")):
        return "network"
    return "runtime"
