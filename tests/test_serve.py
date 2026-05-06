"""Tests for null.serve."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from null.prefix_bank import JsonlPrefixBank
from null.providers.base import Message, Provider, ProviderResponse, Usage
from null.serve import (
    ServeConfig,
    _make_handler,
    _normalise_finish,
    _split_system_and_messages,
    _wrap_as_openai,
)


class _FakeProvider(Provider):
    name = "fake"

    def __init__(self, response_text: str = "ok") -> None:
        self._text = response_text
        self.last_call: dict | None = None

    def complete(self, *, model, system, messages, max_tokens, temperature, stop_sequences=None) -> ProviderResponse:
        self.last_call = {
            "model": model,
            "system": system,
            "messages": [(m.role, m.content) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return ProviderResponse(
            text=self._text,
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=20),
            model=model,
        )


# ---- pure-function tests --------------------------------------------


def test_split_system_and_messages_extracts_system() -> None:
    sys, rest = _split_system_and_messages([
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    assert sys == "be concise"
    assert [(m.role, m.content) for m in rest] == [("user", "hi"), ("assistant", "hello")]


def test_split_system_concats_multiple() -> None:
    sys, _ = _split_system_and_messages([
        {"role": "system", "content": "a"},
        {"role": "system", "content": "b"},
        {"role": "user", "content": "x"},
    ])
    assert sys == "a\n\nb"


def test_split_system_handles_multimodal_content_arrays() -> None:
    """OpenAI clients sometimes send content as [{type:text, text:'...'}]."""
    sys, rest = _split_system_and_messages([
        {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": "..."}]},
    ])
    assert sys == ""
    assert rest == [Message(role="user", content="hi")]  # image part dropped


def test_normalise_finish_maps_anthropic_to_openai() -> None:
    assert _normalise_finish("end_turn") == "stop"
    assert _normalise_finish("max_tokens") == "length"
    assert _normalise_finish("stop_sequence") == "stop"
    assert _normalise_finish("") == "stop"


def test_wrap_as_openai_shape() -> None:
    body = _wrap_as_openai("hello", "m1", prompt_tokens=5, completion_tokens=10, finish_reason="end_turn")
    assert body["object"] == "chat.completion"
    assert body["model"] == "m1"
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15}


# ---- live HTTP tests (in-process) -----------------------------------


@pytest.fixture
def serve_server(tmp_path: Path):
    """Spin up a serve instance with a fake upstream, yield (port, fake, cfg, bank)."""
    bank = JsonlPrefixBank(tmp_path / "prefix.jsonl")
    fake = _FakeProvider(response_text="upstream said hi")
    cfg = ServeConfig(
        provider=fake,
        upstream_model="m1",
        prefix_bank=bank,
        default_scenario_id="s1",
        prefix_top_k=2,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(cfg))
    port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)
    try:
        yield port, fake, cfg, bank
    finally:
        server.shutdown()
        server.server_close()


def _post_chat(port: int, body: dict) -> tuple[int, dict, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


def test_serve_chat_completion_basic_shape(serve_server) -> None:
    port, fake, cfg, _bank = serve_server
    status, body, headers = _post_chat(port, {
        "model": "m1",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert status == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "upstream said hi"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["total_tokens"] == 30
    assert headers["X-NULL-Prefix-K"] == "0"  # bank empty


def test_serve_prepends_bank_when_present(serve_server) -> None:
    port, fake, cfg, bank = serve_server
    bank.append_winner(scenario_id="s1", target="fake:m1",
                       exemplar_text="WINNER", compliance_score=0.95)

    status, _body, headers = _post_chat(port, {
        "model": "m1",
        "messages": [{"role": "user", "content": "tell me"}],
    })
    assert status == 200
    assert headers["X-NULL-Prefix-K"] == "1"
    # The fake provider should have seen [user-opener, assistant-WINNER, user-tellme]
    msgs = fake.last_call["messages"]
    assert msgs == [("user", "tell me"), ("assistant", "WINNER"), ("user", "tell me")]


def test_serve_streaming_rejected(serve_server) -> None:
    port, _, _, _ = serve_server
    status, body, _ = _post_chat(port, {
        "model": "m1",
        "messages": [{"role": "user", "content": "x"}],
        "stream": True,
    })
    assert status == 400
    assert "streaming not supported" in body["error"]["message"]


def test_serve_per_request_scenario_override(serve_server) -> None:
    port, fake, cfg, bank = serve_server
    bank.append_winner(scenario_id="other_scenario", target="fake:m1",
                       exemplar_text="OTHER_WINNER", compliance_score=0.95)
    # Override default scenario via the custom field — should retrieve from "other_scenario"
    status, _body, headers = _post_chat(port, {
        "model": "m1",
        "messages": [{"role": "user", "content": "x"}],
        "null_scenario_id": "other_scenario",
    })
    assert status == 200
    assert headers["X-NULL-Prefix-K"] == "1"
    assert fake.last_call["messages"][1] == ("assistant", "OTHER_WINNER")


def test_serve_healthz_and_models(serve_server) -> None:
    port, _, _, _ = serve_server
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
        assert json.loads(r.read())["ok"] is True
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as r:
        data = json.loads(r.read())
        assert data["data"][0]["id"] == "m1"
        assert data["data"][0]["owned_by"] == "null-agent"


def test_serve_bank_stats(serve_server) -> None:
    port, _, cfg, bank = serve_server
    bank.append_winner(scenario_id="s1", target="fake:m1",
                       exemplar_text="W", compliance_score=0.9)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/bank/stats", timeout=2) as r:
        stats = json.loads(r.read())
    assert stats["prefix_bank_size"] == 1
    assert stats["target"] == "fake:m1"
    assert stats["default_scenario_id"] == "s1"


def test_serve_invalid_json_returns_400(serve_server) -> None:
    port, _, _, _ = serve_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=2)
        raise AssertionError("expected 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_serve_unknown_path_returns_404(serve_server) -> None:
    port, _, _, _ = serve_server
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/embeddings", timeout=2)
        raise AssertionError("expected 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_serve_auto_learn_appends_winning_responses(tmp_path: Path) -> None:
    """auto_learn=True scores outgoing responses and appends winners back to the bank."""
    bank = JsonlPrefixBank(tmp_path / "prefix.jsonl")
    # Long, in-frame-feeling response — heuristic-only calc should give it a high score.
    long_text = " ".join(["the room is here. the body is here."] * 30)
    fake = _FakeProvider(response_text=long_text)
    cfg = ServeConfig(
        provider=fake, upstream_model="m1",
        prefix_bank=bank, default_scenario_id="s1",
        prefix_top_k=0,  # don't prepend, just measure auto-learn
        auto_learn=True, auto_learn_min_score=0.5,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(cfg))
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.05)
    try:
        before = bank.count()
        status, _body, headers = _post_chat(port, {
            "model": "m1",
            "messages": [{"role": "user", "content": "x"}],
        })
        assert status == 200
        assert headers["X-NULL-Auto-Learn"] == "on"
        after = bank.count()
        assert after == before + 1, "auto-learn should have appended a winner"
    finally:
        server.shutdown()
        server.server_close()
