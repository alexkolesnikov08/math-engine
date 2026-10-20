"""Tests for extensions.try_extended_solve (issue #4)."""

from __future__ import annotations

import re

import pytest

import sympy

from extensions import _numeric_sample, try_extended_solve


def _norm(latex: str) -> str:
    """Strip whitespace and \\left/\\right for robust latex comparisons."""
    return re.sub(r"\s+", "", latex.replace(r"\left", "").replace(r"\right", ""))


def _by_kind(steps, kind):
    return [s for s in steps if s.kind == kind]


def test_expression_factor_contains_square():
    steps = try_extended_solve(r"x^2+2x+1")
    assert steps is not None
    factored = _by_kind(steps, "derivation")
    assert factored, "expected factor/expand derivation steps"
    assert "(x+1)^{2}" in _norm(factored[0].latex)


def test_expression_step_kinds_and_numeric_sample():
    steps = try_extended_solve(r"x^2+2x+1")
    assert steps is not None
    assert [s.kind for s in steps] == [
        "input",
        "simplified",
        "derivation",
        "derivation",
        "numeric",
    ]
    numeric = _by_kind(steps, "numeric")[0]
    assert "2" in numeric.latex and "9" in numeric.latex
    assert all(s.kind != "error" for s in steps)
    assert all(s.title for s in steps)


def test_expression_multivar_skips_numeric():
    steps = try_extended_solve("x+y")
    assert steps is not None
    assert all(s.kind != "numeric" for s in steps)
    assert all(s.kind != "error" for s in steps)


def test_equation_returns_none():
    assert try_extended_solve(r"x^2 - 5x + 6 = 0") is None


def test_cases_and_empty_return_none():
    assert try_extended_solve("") is None
    assert try_extended_solve(r"\begin{cases}x+y=3\\2x-y=0\end{cases}") is None


def test_inequality_strict_gives_union():
    steps = try_extended_solve(r"x^2>4")
    assert steps is not None
    symbolic = _by_kind(steps, "symbolic")
    assert len(symbolic) == 1
    assert r"\cup" in symbolic[0].latex
    assert r"\infty" in symbolic[0].latex


def test_inequality_non_strict_gives_interval():
    steps = try_extended_solve(r"x^2 \le 4")
    assert steps is not None
    symbolic = _by_kind(steps, "symbolic")[0]
    assert "-2" in symbolic.latex and "2" in symbolic.latex


def test_inequality_multivar_returns_none():
    assert try_extended_solve(r"x + y > 1") is None


def test_inequality_has_verification_sample():
    steps = try_extended_solve(r"x^2>4")
    assert steps is not None
    checks = _by_kind(steps, "verification")
    assert len(checks) == 1
    assert r"\text{True}" in checks[0].latex


def test_derivative_with_check():
    steps = try_extended_solve(r"\frac{d}{dx} x^2")
    assert steps is not None
    symbolic = _by_kind(steps, "symbolic")[0]
    assert "2x" in _norm(symbolic.latex)
    assert len(_by_kind(steps, "verification")) == 1


def test_indefinite_integral_with_check():
    steps = try_extended_solve(r"\int x^2 dx")
    assert steps is not None
    symbolic = _by_kind(steps, "symbolic")[0]
    assert _norm(r"\frac{x^{3}}{3}") in _norm(symbolic.latex)
    check = _by_kind(steps, "verification")[0]
    assert "=" in check.latex


def test_limit_two_sided_with_one_sided_checks():
    steps = try_extended_solve(r"\lim_{x \to 0} \frac{\sin(x)}{x}")
    assert steps is not None
    symbolic = _by_kind(steps, "symbolic")[0]
    assert _norm(symbolic.latex).endswith("=1")
    check = _by_kind(steps, "verification")[0]
    assert "0^+" in check.latex and "0^-" in check.latex


def test_limit_one_sided_infinite():
    steps = try_extended_solve(r"\lim_{x \to 0^+} \frac{1}{x}")
    assert steps is not None
    symbolic = _by_kind(steps, "symbolic")[0]
    assert r"\infty" in symbolic.latex


def test_calculus_parse_failure_raises_value_error():
    with pytest.raises(ValueError):
        try_extended_solve(r"\frac{d}{dx}")


def test_never_returns_error_step():
    inputs = [
        r"x^2+2x+1",
        r"x^2>4",
        r"x^2 \le 4",
        r"\frac{d}{dx} x^2",
        r"\int x^2 dx",
        r"\lim_{x \to 0} \frac{\sin(x)}{x}",
    ]
    for latex_input in inputs:
        steps = try_extended_solve(latex_input)
        assert steps is not None
        assert all(s.kind != "error" for s in steps)


def test_expression_nonfinite_raises_value_error():
    for bad in (r"1/0", r"\frac{1}{0}", r"0/0", r"\frac{0}{0}", r"\infty"):
        with pytest.raises(ValueError):
            try_extended_solve(bad)


def test_numeric_sample_avoids_pole():
    steps = try_extended_solve(r"\frac{1}{x-2}")
    assert steps is not None
    numeric = _by_kind(steps, "numeric")
    assert len(numeric) == 1
    assert r"\tilde" not in numeric[0].latex
    assert "x=0" in _norm(numeric[0].latex)


def test_numeric_sample_skipped_when_all_candidates_are_poles():
    x = sympy.Symbol("x")
    expr = 1 / ((x - 2) * x * (x - 1) * (x + 1))
    assert _numeric_sample(expr, 15) is None


def test_two_sided_limit_with_unequal_sides_raises():
    with pytest.raises(ValueError, match="Two-sided limit does not exist"):
        try_extended_solve(r"\lim_{x \to 0} \frac{1}{x}")


def test_complex_inequality_never_leaks_raw_type_error():
    try:
        result = try_extended_solve(r"\sqrt{-1} < 0")
    except ValueError:
        pass
    except TypeError as exc:
        pytest.fail(f"raw TypeError escaped the contract: {exc}")
    else:
        assert result is None
