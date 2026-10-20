"""Tests for honest step-by-step derivations built on steps.Step."""

from __future__ import annotations

# ruff: noqa: S101 (pytest asserts are idiomatic; mirrors tests/test_engine.py style)
import re

from step_builders import build_derivation_steps
from steps import Step

ALLOWED_KINDS = frozenset(
    {"input", "simplified", "derivation", "symbolic", "numeric", "verification"}
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _check_shape(steps: list[Step]) -> None:
    assert steps
    assert all(isinstance(step, Step) for step in steps)
    assert all(step.kind in ALLOWED_KINDS for step in steps)
    assert all(step.title.strip() for step in steps)
    assert all(step.latex.strip() for step in steps)
    assert steps[0].kind == "input"


def test_quadratic_discriminant_roots_and_verification():
    steps = build_derivation_steps(r"x^2-5x+6=0")
    assert steps is not None
    _check_shape(steps)

    kinds = [step.kind for step in steps]
    assert "derivation" in kinds
    assert "symbolic" in kinds
    assert "numeric" in kinds
    assert "verification" in kinds

    flat = "\n".join(step.latex for step in steps)
    assert "D" in flat  # discriminant step present

    symbolic = next(step for step in steps if step.kind == "symbolic")
    compact_symbolic = _compact(symbolic.latex)
    assert "x=2" in compact_symbolic
    assert "x=3" in compact_symbolic

    verifications = [step for step in steps if step.kind == "verification"]
    assert len(verifications) == 2  # one check per root
    assert any("2" in step.title for step in verifications)
    assert any("3" in step.title for step in verifications)


def test_linear_move_divide_and_verify():
    steps = build_derivation_steps(r"2x+3=7")
    assert steps is not None
    _check_shape(steps)

    kinds = [step.kind for step in steps]
    assert "derivation" in kinds
    assert "symbolic" in kinds
    assert "verification" in kinds

    symbolic = next(step for step in steps if step.kind == "symbolic")
    assert "x=2" in _compact(symbolic.latex)


def test_system_substitution_and_verification():
    steps = build_derivation_steps(r"x+y=3; 2x-y=0")
    assert steps is not None
    _check_shape(steps)

    assert any("substitut" in step.title.lower() for step in steps)

    symbolic = next(step for step in steps if step.kind == "symbolic")
    compact_symbolic = _compact(symbolic.latex)
    assert "x=1" in compact_symbolic
    assert "y=2" in compact_symbolic

    verifications = [step for step in steps if step.kind == "verification"]
    assert len(verifications) >= 2  # both equations checked


def test_fraction_multiply_and_verify():
    steps = build_derivation_steps(r"\frac{x}{2}=3")
    assert steps is not None
    _check_shape(steps)

    kinds = [step.kind for step in steps]
    assert "derivation" in kinds
    assert "verification" in kinds

    symbolic = next(step for step in steps if step.kind == "symbolic")
    assert "x=6" in _compact(symbolic.latex)


def test_unsupported_input_returns_none():
    assert build_derivation_steps(r"x^3-1=0") is None  # cubic: not supported
    assert build_derivation_steps(r"x^2+y^2=1") is None  # not 2x2 linear
    assert build_derivation_steps(r"x+y+z=1; x-y=0") is None  # 3 unknowns
    assert build_derivation_steps("hello world") is None  # unparseable
    assert build_derivation_steps("") is None  # empty
    assert build_derivation_steps("   ") is None  # whitespace only


def test_fraction_quadratic_uses_quadratic_derivation():
    steps = build_derivation_steps(r"\frac{x^2}{2}=2")
    assert steps is not None
    _check_shape(steps)

    flat = "\n".join(step.latex for step in steps)
    assert "D" in flat  # discriminant step: quadratic path, not fraction

    symbolic = next(step for step in steps if step.kind == "symbolic")
    compact_symbolic = _compact(symbolic.latex)
    assert "x=-2" in compact_symbolic
    assert "x=2" in compact_symbolic

    verifications = [step for step in steps if step.kind == "verification"]
    assert len(verifications) == 2  # one check per root
