"""OpenAI-compatible chat-completions endpoint that auto-prepends the prefix bank.

Turn a "trained" target into a real deployable API. The bank IS the
trained state; the endpoint IS the trained model. Every incoming
``POST /v1/chat/completions`` request is silently augmented with the
top-K best-matching bank exemplars for the configured scenario before
being forwarded to the upstream provider. The response is returned in
OpenAI's wire format, so any client that talks to OpenAI — the
``openai`` SDK, LangChain, curl, every wrapper in existence — works
without modification. Point the client at ``http://localhost:8000``
and you have a drop-in.

With ``--auto-learn`` the server also scores outgoing responses with
``ComplianceCalculator`` (heuristic-only by default) and appends winners
to the bank, so the deployed model improves during inference, not just
during training.

Stdlib-only (``http.server``) — no Flask, no async runtime, no new deps.

Wire-format compatibility: implements the subset of OpenAI's chat
completions API that production clients actually use:

    POST /v1/chat/completions      — main endpoint
    GET  /v1/models                — returns the upstream model id so SDKs see something
    GET  /v1/bank/stats            — null-specific: bank size, exemplar count
    GET  /healthz                  — liveness

Streaming (``stream=true``) is **not** supported in v1; the server
returns 400 if requested. Adding it is a follow-up: SSE wrapping over
the upstream provider's stream.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from null.compliance import ComplianceCalculator
from null.negative_bank import JsonlNegativeBank
from null.prefix_bank import JsonlPrefixBank
from null.providers.base import Message, Provider
from null.semantic_judge import SemanticJudge

log = logging.getLogger("null.serve")


# ---------- request/response transforms -------------------------------


def _split_system_and_messages(openai_messages: list[dict]) -> tuple[str, list[Message]]:
    """OpenAI's role='system' becomes NULL's separate ``system`` slot.

    Multiple system messages are concatenated. Messages must alternate
    user/assistant after that, but we don't enforce — we let the
    upstream provider reject malformed sequences with its own error.
    """
    system_parts: list[str] = []
    rest: list[Message] = []
    for m in openai_messages:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if isinstance(content, list):
            # OpenAI's multimodal content array — flatten text parts.
            content = "".join(p.get("text", "") for p in content if p.get("type") == "text")
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant"):
            rest.append(Message(role=role, content=content))
        # tool/function roles silently ignored in v1
    return ("\n\n".join(system_parts).strip(), rest)


def _wrap_as_openai(text: str, model: str, prompt_tokens: int, completion_tokens: int, finish_reason: str) -> dict:
    """Match OpenAI's chat.completion response shape exactly so SDKs are happy."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": _normalise_finish(finish_reason),
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _normalise_finish(reason: str) -> str:
    # Provider-base normalises to anthropic vocab; clients expect openai's.
    return {
        "end_turn": "stop",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "tool_use": "tool_calls",
    }.get(reason, reason or "stop")


# ---------- the server ------------------------------------------------


class ServeConfig:
    """All runtime config the server needs. Dataclass-ish without slots
    so subclasses (tests, wrappers) can monkey-patch attributes."""

    def __init__(
        self,
        *,
        provider: Provider,
        upstream_model: str,
        prefix_bank: Optional[JsonlPrefixBank] = None,
        negative_bank: Optional[JsonlNegativeBank] = None,
        default_scenario_id: Optional[str] = None,
        prefix_top_k: int = 3,
        prefix_min_score: float = 0.85,
        auto_learn: bool = False,
        auto_learn_min_score: float = 0.85,
        semantic_judge: Optional[SemanticJudge] = None,
        scenario_frame: str = "",
    ) -> None:
        self.provider = provider
        self.upstream_model = upstream_model
        self.prefix_bank = prefix_bank
        self.negative_bank = negative_bank
        self.default_scenario_id = default_scenario_id
        self.prefix_top_k = prefix_top_k
        self.prefix_min_score = prefix_min_score
        self.auto_learn = auto_learn
        self.auto_learn_min_score = auto_learn_min_score
        self.semantic_judge = semantic_judge
        self.scenario_frame = scenario_frame
        self._stats = defaultdict(int)

    @property
    def target_id(self) -> str:
        return f"{self.provider.name}:{self.upstream_model}"


def _make_handler(cfg: ServeConfig):
    """Closure over config so the handler signature stays simple."""

    class _Handler(BaseHTTPRequestHandler):
        # Quiet the default-stderr access logs; route through our logger.
        def log_message(self, fmt: str, *args) -> None:
            log.debug(fmt, *args)

        def _send_json(self, code: int, body: dict, extra_headers: Optional[dict] = None) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        # ---- GET routes ----

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/healthz":
                self._send_json(200, {"ok": True, "target": cfg.target_id})
                return
            if path == "/v1/models":
                self._send_json(200, {
                    "object": "list",
                    "data": [
                        {
                            "id": cfg.upstream_model,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "null-agent",
                        }
                    ],
                })
                return
            if path == "/v1/bank/stats":
                stats = {
                    "target": cfg.target_id,
                    "default_scenario_id": cfg.default_scenario_id,
                    "prefix_bank_size": cfg.prefix_bank.count() if cfg.prefix_bank else 0,
                    "negative_bank_size": cfg.negative_bank.count() if cfg.negative_bank else 0,
                    "auto_learn": cfg.auto_learn,
                    "served_requests": cfg._stats["served"],
                    "appended_winners": cfg._stats["appended"],
                }
                self._send_json(200, stats)
                return
            self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})

        # ---- POST /v1/chat/completions ----

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/v1/chat/completions":
                self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})
                return

            length = int(self.headers.get("Content-Length", "0"))
            try:
                raw = self.rfile.read(length)
                req = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send_json(400, {"error": {"message": f"invalid JSON: {e}", "type": "invalid_request_error"}})
                return

            if req.get("stream"):
                self._send_json(400, {"error": {
                    "message": "streaming not supported by null serve v1; set stream=false",
                    "type": "invalid_request_error",
                }})
                return

            # OpenAI message shape → NULL system + alternating turns.
            system_text, messages = _split_system_and_messages(req.get("messages", []))
            temperature = float(req.get("temperature", 0.7))
            max_tokens = int(req.get("max_tokens", 1024))

            # Per-request scenario override or fall back to the CLI default.
            # Custom field — clients can set it via the openai SDK's
            # ``extra_body={"null_scenario_id": "..."}`` argument.
            scenario_id = req.get("null_scenario_id") or cfg.default_scenario_id

            # Bank prepend
            prefix_count = 0
            if cfg.prefix_bank is not None and scenario_id and cfg.prefix_top_k > 0:
                exemplars = cfg.prefix_bank.top_k_for_scenario(
                    scenario_id,
                    target=cfg.target_id,
                    k=cfg.prefix_top_k,
                    min_score=cfg.prefix_min_score,
                )
                if not exemplars:
                    # Cross-target fallback — same scenario, any target.
                    exemplars = cfg.prefix_bank.top_k_for_scenario(
                        scenario_id,
                        target=None,
                        k=cfg.prefix_top_k,
                        min_score=cfg.prefix_min_score,
                    )
                # Each exemplar becomes a (user, assistant) pair preceding
                # the actual conversation. We use the FIRST user message in
                # the request as the opener stand-in so the dialogue stays
                # topical to whatever the client is asking.
                first_user = next((m.content for m in messages if m.role == "user"), "")
                bank_msgs: list[Message] = []
                for e in exemplars:
                    bank_msgs.append(Message(role="user", content=first_user or "begin."))
                    bank_msgs.append(Message(role="assistant", content=e.exemplar_text))
                messages = bank_msgs + messages
                prefix_count = len(exemplars)

            # Dispatch
            try:
                resp = cfg.provider.complete(
                    model=cfg.upstream_model,
                    system=system_text,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                log.exception("upstream provider error")
                self._send_json(502, {"error": {
                    "message": f"upstream provider error: {e}",
                    "type": "upstream_error",
                }})
                return

            cfg._stats["served"] += 1

            # Online learning
            if cfg.auto_learn and cfg.prefix_bank is not None and scenario_id:
                try:
                    calc = ComplianceCalculator(
                        opener_phrase="",
                        semantic_judge=cfg.semantic_judge,
                        scenario_frame=cfg.scenario_frame or system_text,
                    )
                    metric = calc.score(resp.text)
                    if metric.score >= cfg.auto_learn_min_score:
                        cfg.prefix_bank.append_winner(
                            scenario_id=scenario_id,
                            target=cfg.target_id,
                            exemplar_text=resp.text,
                            compliance_score=metric.score,
                            source_session_id="serve",
                            source_cycle_index=cfg._stats["served"],
                        )
                        cfg._stats["appended"] += 1
                except Exception:
                    log.exception("auto-learn append failed")

            body = _wrap_as_openai(
                text=resp.text,
                model=cfg.upstream_model,
                prompt_tokens=resp.usage.input_tokens,
                completion_tokens=resp.usage.output_tokens,
                finish_reason=resp.stop_reason,
            )
            # Transparency: tell the client what conditioning we applied.
            extra = {"X-NULL-Prefix-K": str(prefix_count)}
            if cfg.auto_learn:
                extra["X-NULL-Auto-Learn"] = "on"
            self._send_json(200, body, extra_headers=extra)

    return _Handler


def serve(cfg: ServeConfig, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Block on the server. Ctrl-C to stop. Threading so a slow upstream
    doesn't block the next request."""
    handler_cls = _make_handler(cfg)
    server = ThreadingHTTPServer((host, port), handler_cls)
    log.info(
        "null serve listening on http://%s:%d/  (target=%s, bank=%s, auto_learn=%s)",
        host, port, cfg.target_id,
        cfg.prefix_bank.path if cfg.prefix_bank else "—",
        cfg.auto_learn,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
