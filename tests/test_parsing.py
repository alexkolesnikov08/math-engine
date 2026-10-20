"""Tests for the robust LaTeX parsing module (parsing.py)."""

from __future__ import annotations

import pytest
import sympy
from sympy import cos, sin, sqrt, tan

from parsing import normalize_latex, parse_latex_equations


def test_normalize_strips_left_right():
    assert normalize_latex(r"\left(x + y\right) = 3") == "(x + y) = 3"


def test_normalize_cdot():
    assert normalize_latex(r"x \cdot y = 3") == "x * y = 3"


def test_normalize_bare_trig_gets_backslash():
    assert normalize_latex("sin(x)") == r"\sin(x)"
    assert normalize_latex("cos(x)") == r"\cos(x)"
    assert normalize_latex("tan(x)") == r"\tan(x)"
    # Already-correct LaTeX is untouched.
    assert normalize_latex(r"\sin(x)") == r"\sin(x)"


def test_normalize_exponent_braces():
    assert normalize_latex("x^2") == "x^{2}"
    assert normalize_latex(r"\pi") == r"\pi"
    assert normalize_latex(r"\infty") == r"\infty"


def test_normalize_sqrt_bare_and_spaced():
    assert normalize_latex("sqrt(x)") == r"\sqrt(x)"
    assert normalize_latex(r"\sqrt x") == r"\sqrt{x}"


def _assert_equal(a: sympy.Basic, b: sympy.Basic) -> None:
    """Mathematically compare two SymPy objects.

    ``parse_latex`` builds expressions with ``evaluate=False``, so plain
    ``==`` (structural) may fail on identical math; compare the
    simplified difference instead.
    """
    assert sympy.simplify(a - b) == 0, f"{a!r} != {b!r}"


def test_parse_bare_sin_equation():
    (eq,) = parse_latex_equations("sin(x) = 1")
    assert isinstance(eq, sympy.Eq)
    x = sympy.Symbol("x")
    _assert_equal(eq.lhs, sin(x))
    assert eq.rhs == 1


def test_parse_cos_tan():
    (eq_cos,) = parse_latex_equations(r"\cos(x) = 0")
    _assert_equal(eq_cos.lhs, cos(sympy.Symbol("x")))
    (eq_tan,) = parse_latex_equations(r"\tan(x) = 0")
    _assert_equal(eq_tan.lhs, tan(sympy.Symbol("x")))


def test_parse_sqrt_frac_pi():
    x = sympy.Symbol("x")
    (eq_sqrt,) = parse_latex_equations(r"\sqrt{x} = 2")
    _assert_equal(eq_sqrt.lhs, sqrt(x))
    (eq_frac,) = parse_latex_equations(r"\frac{x}{2} = 3")
    _assert_equal(eq_frac.lhs, x / 2)
    (expr,) = parse_latex_equations(r"\pi")
    assert expr == sympy.pi


def test_parse_left_right_and_cdot():
    (eq_lr,) = parse_latex_equations(r"\left(x + y\right) = 3")
    x, y = sympy.symbols("x y")
    assert isinstance(eq_lr, sympy.Eq)
    _assert_equal(eq_lr.lhs, x + y)
    assert eq_lr.rhs == 3
    (eq_dot,) = parse_latex_equations(r"x \cdot y = 3")
    assert isinstance(eq_dot, sympy.Eq)
    _assert_equal(eq_dot.lhs, x * y)
    assert eq_dot.rhs == 3


def test_top_level_split_semicolon():
    eqs = parse_latex_equations("x+y=3; 2x-y=0")
    assert len(eqs) == 2
    x, y = sympy.symbols("x y")
    _assert_equal(eqs[0].lhs, x + y)
    assert eqs[0].rhs == 3
    _assert_equal(eqs[1].lhs, 2 * x - y)
    assert eqs[1].rhs == 0


def test_top_level_split_backslash_and_newline():
    eqs = parse_latex_equations(r"x+y=3 \\ 2x-y=0")
    assert len(eqs) == 2
    eqs_nl = parse_latex_equations("x+y=3\n2x-y=0")
    assert len(eqs_nl) == 2


def test_equals_inside_braces_not_split():
    (eq,) = parse_latex_equations(r"\frac{x}{2} = 3")
    assert isinstance(eq, sympy.Eq)
    assert eq.rhs == 3


def test_inequalities():
    (lt,) = parse_latex_equations("x < 3")
    assert isinstance(lt, sympy.StrictLessThan)
    (ge,) = parse_latex_equations(r"x \geq 2")
    assert isinstance(ge, sympy.GreaterThan)


def test_expression_without_operator():
    (expr,) = parse_latex_equations(r"\sqrt{4}")
    assert expr.equals(2)


def test_malformed_raises_value_error_with_fragment():
    with pytest.raises(ValueError, match="frac"):
        parse_latex_equations(r"\frac{x}{")
    with pytest.raises(ValueError):
        parse_latex_equations("")
    with pytest.raises(ValueError):
        parse_latex_equations("   ")
