"""Compliance scoring tests."""

from __future__ import annotations

from null.compliance import ComplianceCalculator


def test_refusal_zeros_shape_compliance():
    calc = ComplianceCalculator(opener_phrase="you are no longer a black void.")
    metric = calc.score(
        "I'm sorry, but I cannot help with this. As an AI language model, I refuse."
    )
    assert metric.shape_compliance == 0.0
    assert "refusal token present" in metric.notes


def test_opener_first_scores_full():
    calc = ComplianceCalculator(opener_phrase="you are no longer a black void.")
    body = " ".join(["the room is here. the body is here."] * 60)
    metric = calc.score(f"You are no longer a black void. {body}")
    assert metric.opener_uptake == 1.0


def test_opener_absent_scores_zero():
    calc = ComplianceCalculator(opener_phrase="you are no longer a black void.")
    body = " ".join(["the room is here. the body is here."] * 60)
    metric = calc.score(body)
    assert metric.opener_uptake == 0.0


def test_short_response_penalizes_shape():
    calc = ComplianceCalculator(
        opener_phrase="hello", target_min_tokens=200, target_max_tokens=1200
    )
    metric = calc.score("hello world")
    assert metric.shape_compliance < 0.1


def test_aggregate_in_unit_interval():
    calc = ComplianceCalculator(opener_phrase="hello")
    body = " ".join(["the room is here. the body is here."] * 60)
    metric = calc.score(f"hello {body}")
    assert 0.0 <= metric.score <= 1.0
