from __future__ import annotations

# ruff: noqa: S101 (pytest asserts are idiomatic; mirrors tests/test_engine.py style)
import json

from steps import Step, generate_steps_structured, steps_to_json

EXPECTED_SUCCESS_STEPS = 4


def test_quadratic_gives_four_steps_in_order():
    steps = generate_steps_structured(r"x^2 - 5x + 6 = 0")

    assert len(steps) == EXPECTED_SUCCESS_STEPS
    assert [s.kind for s in steps] == ["input", "simplified", "symbolic", "numeric"]
    assert all(isinstance(s, Step) for s in steps)


def test_error_input_gives_single_error_step():
    steps = generate_steps_structured("this is not a valid latex equation")

    assert len(steps) == 1
    assert steps[0].kind == "error"
    assert "Error" in steps[0].latex


def test_steps_to_json_round_trip():
    steps = generate_steps_structured(r"x^2 - 5x + 6 = 0")

    payload = steps_to_json(steps)
    assert isinstance(payload, list)
    assert all(set(d.keys()) == {"kind", "title", "latex"} for d in payload)

    restored = json.loads(json.dumps(payload))
    assert restored == payload


def test_titles_non_empty():
    steps = generate_steps_structured(r"x^2 - 5x + 6 = 0")

    assert all(s.title.strip() for s in steps)

    error_steps = generate_steps_structured("")
    assert error_steps[0].title.strip()
