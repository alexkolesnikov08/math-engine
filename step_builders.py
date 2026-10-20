"""Honest step-by-step derivations for basic equation types.

This module builds :class:`steps.Step` chains with explicit intermediate
derivations (discriminant with substituted numbers, quadratic formula,
collecting terms, substitution into a system, clearing denominators and
verification by substitution). Every piece of mathematics in a derivation
step is rendered with :func:`sympy.printing.latex.latex`, never hand-written
via f-string math.

Only basic types are supported; anything else returns ``None`` so the
caller can fall back to the legacy engine path.
"""

from __future__ import annotations

import re

import sympy
from sympy import Eq, Integer, Poly
from sympy.printing.latex import latex

try:  # parsing.py is owned in parallel and may not exist yet.
    from parsing import parse_latex_equations
except ImportError:  # Fall back to the engine's LaTeX converter.
    from engine import _latex_to_sympy as fallback

from steps import Step

__all__ = ["build_derivation_steps"]

_ALLOWED_KINDS = frozenset(
    {"input", "simplified", "derivation", "symbolic", "numeric", "verification"}
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _split_raw(latex_input: str) -> list[str]:
    """Split raw input into single-equation fragments (mirrors engine)."""
    text = latex_input.strip()
    if r"\begin{cases}" in text:
        match = re.search(r"\\begin\{cases\}(.*)\\end\{cases\}", text, re.DOTALL)
        if match is None:
            return []
        inner = match.group(1)
        return [line.strip() for line in re.split(r"\\\\", inner) if line.strip()]
    return [p.strip() for p in re.split(r"(?:\\\\|;|\n)", text) if p.strip()]


def _parse_equations(latex_input: str) -> list[sympy.Basic] | None:
    """Parse raw LaTeX into SymPy equations, or return None."""
    raw = latex_input.strip()
    if not raw:
        return None
    if "parse_latex_equations" in globals():
        try:
            parsed = parse_latex_equations(raw)  # type: ignore[name-defined]
        except Exception:
            return None
        items = list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]
    else:
        fragments = _split_raw(raw)
        if not fragments:
            return None
        try:
            items = [fallback(frag) for frag in fragments]  # type: ignore[name-defined]
        except Exception:
            return None
    equations: list[sympy.Basic] = []
    for item in items:
        if isinstance(item, Eq):
            equations.append(item)
        elif isinstance(item, sympy.Basic):
            equations.append(Eq(item, 0))
        else:
            return None
    return equations or None


def _contains_frac(raw: str) -> bool:
    """Check whether the raw input uses a fraction command."""
    return r"\frac" in raw or r"\dfrac" in raw or r"\tfrac" in raw


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def _numeric(value: sympy.Basic) -> sympy.Basic:
    """Return a numerical approximation of a SymPy value."""
    try:
        return value.evalf(15)
    except Exception:
        return value


def _input_step(raw: str) -> Step:
    """Build the input step echoing the raw LaTeX."""
    return Step(kind="input", title="Input", latex=raw.strip())


def _simplified_step(equations: list[Eq]) -> Step:
    """Build the simplified-form step for parsed equations."""
    parts = []
    for eq in equations:
        lhs = sympy.simplify(eq.lhs)
        rhs = sympy.simplify(eq.rhs)
        parts.append(latex(Eq(lhs, rhs)))
    return Step(kind="simplified", title="Simplified form", latex=r"\\ ".join(parts))


def _symbolic_step(solution: dict[sympy.Symbol, sympy.Basic]) -> Step:
    """Build the symbolic-solution step from an ordered solution mapping."""
    parts = [f"{latex(var)} = {latex(solution[var])}" for var in solution]
    return Step(
        kind="symbolic", title="Symbolic solution", latex=r",\; ".join(parts)
    )


def _numeric_step(solution: dict[sympy.Symbol, sympy.Basic]) -> Step:
    """Build the numerical-approximation step from a solution mapping."""
    parts = [f"{latex(var)} \\approx {latex(_numeric(solution[var]))}" for var in solution]
    return Step(
        kind="numeric", title="Numerical approximation", latex=r",\; ".join(parts)
    )


def _verification_step(
    equation: Eq, solution: dict[sympy.Symbol, sympy.Basic], title: str
) -> Step:
    """Build a verification step by substituting the solution back."""
    lhs = sympy.simplify(equation.lhs.subs(solution))
    rhs = sympy.simplify(equation.rhs.subs(solution))
    return Step(
        kind="verification", title=title, latex=latex(Eq(lhs, rhs, evaluate=False))
    )


def _single_var_poly(equation: Eq) -> tuple[sympy.Symbol, Poly] | None:
    """Return the single free symbol and polynomial of ``lhs - rhs``."""
    symbols = sorted(equation.free_symbols, key=lambda s: str(s))
    if len(symbols) != 1:
        return None
    var = symbols[0]
    try:
        poly = Poly(sympy.expand(equation.lhs - equation.rhs), var)
    except Exception:
        return None
    return (var, poly)


# ---------------------------------------------------------------------------
# Builders per equation type
# ---------------------------------------------------------------------------


def _build_quadratic(raw: str, equation: Eq) -> list[Step] | None:
    """Build derivation steps for a quadratic equation ``ax^2+bx+c=0``."""
    resolved = _single_var_poly(equation)
    if resolved is None:
        return None
    var, poly = resolved
    if poly.degree() != 2:
        return None
    a_val, b_val, c_val = poly.all_coeffs()
    a_sym, b_sym, c_sym = sympy.symbols("a b c")
    disc_sym = sympy.Symbol("D")
    try:
        roots = sympy.solve(equation, var)
    except Exception:
        return None
    if not roots:
        return None
    roots = [sympy.simplify(root) for root in roots]
    disc_value = sympy.simplify(b_val**2 - 4 * a_val * c_val)

    steps = [_input_step(raw), _simplified_step([equation])]
    steps.append(
        Step(
            kind="derivation",
            title="Coefficients of the quadratic equation",
            latex=r",\; ".join(
                [
                    f"{latex(a_sym)} = {latex(a_val)}",
                    f"{latex(b_sym)} = {latex(b_val)}",
                    f"{latex(c_sym)} = {latex(c_val)}",
                ]
            ),
        )
    )
    steps.append(
        Step(
            kind="derivation",
            title="Discriminant formula",
            latex=latex(Eq(disc_sym, b_sym**2 - 4 * a_sym * c_sym)),
        )
    )
    substituted = sympy.Add(
        sympy.Pow(b_val, 2, evaluate=False),
        sympy.Mul(Integer(-4), a_val, c_val, evaluate=False),
        evaluate=False,
    )
    steps.append(
        Step(
            kind="derivation",
            title="Discriminant value",
            latex=f"{latex(Eq(disc_sym, substituted))} = {latex(disc_value)}",
        )
    )
    steps.append(
        Step(
            kind="derivation",
            title="Quadratic formula",
            latex=r",\; ".join(
                [
                    latex(Eq(var, (-b_sym + sympy.sqrt(disc_sym)) / (2 * a_sym))),
                    latex(Eq(var, (-b_sym - sympy.sqrt(disc_sym)) / (2 * a_sym))),
                ]
            ),
        )
    )
    steps.append(
        Step(
            kind="symbolic",
            title="Symbolic solution",
            latex=r",\; ".join(f"{latex(var)} = {latex(root)}" for root in roots),
        )
    )
    steps.append(
        Step(
            kind="numeric",
            title="Numerical approximation",
            latex=r",\; ".join(
                f"{latex(var)} \\approx {latex(_numeric(root))}" for root in roots
            ),
        )
    )
    for root in roots:
        steps.append(
            _verification_step(
                equation,
                {var: root},
                f"Verification for {latex(var)} = {latex(root)}",
            )
        )
    return steps


def _build_linear(raw: str, equation: Eq) -> list[Step] | None:
    """Build derivation steps for a linear equation ``ax+b=0``."""
    resolved = _single_var_poly(equation)
    if resolved is None:
        return None
    var, poly = resolved
    if poly.degree() != 1:
        return None
    a_val, const = poly.all_coeffs()
    if a_val == 0:
        return None
    try:
        found = sympy.solve(equation, var)
    except Exception:
        return None
    if len(found) != 1:
        return None
    root = sympy.simplify(found[0])
    if root.free_symbols:
        return None

    steps = [_input_step(raw), _simplified_step([equation])]
    steps.append(
        Step(
            kind="derivation",
            title="Move the constant term to the right-hand side",
            latex=latex(Eq(a_val * var, -const)),
        )
    )
    steps.append(
        Step(
            kind="symbolic",
            title="Divide by the coefficient",
            latex=latex(Eq(var, root)),
        )
    )
    steps.append(_numeric_step({var: root}))
    steps.append(
        _verification_step(
            equation, {var: root}, f"Verification for {latex(var)} = {latex(root)}"
        )
    )
    return steps


def _build_system(raw: str, equations: list[sympy.Basic]) -> list[Step] | None:
    """Build derivation steps for a 2x2 linear system."""
    if len(equations) != 2:
        return None
    eqs = [eq if isinstance(eq, Eq) else Eq(eq, 0) for eq in equations]
    symbols = sorted(
        {s for eq in eqs for s in eq.free_symbols}, key=lambda s: str(s)
    )
    if len(symbols) != 2:
        return None
    try:
        for eq in eqs:
            if Poly(sympy.expand(eq.lhs - eq.rhs), symbols).total_degree() > 1:
                return None
    except Exception:
        return None

    eq1, eq2 = eqs
    expressed: sympy.Symbol | None = None
    expr: sympy.Basic | None = None
    for candidate in symbols:
        try:
            candidates = sympy.solve(eq1, candidate)
        except Exception:
            candidates = []
        if len(candidates) == 1:
            expressed, expr = candidate, sympy.simplify(candidates[0])
            break
    if expressed is None or expr is None:
        return None
    other = next(s for s in symbols if s != expressed)

    try:
        substituted_eval = Eq(
            sympy.expand(eq2.lhs.subs(expressed, expr)), eq2.rhs.subs(expressed, expr)
        )
        other_candidates = sympy.solve(substituted_eval, other)
        if len(other_candidates) != 1:
            return None
        other_value = sympy.simplify(other_candidates[0])
        expressed_value = sympy.simplify(expr.subs(other, other_value))
    except Exception:
        return None
    if other_value.free_symbols or expressed_value.free_symbols:
        return None
    solution = {expressed: expressed_value, other: other_value}
    for eq in eqs:
        if sympy.simplify(eq.lhs.subs(solution) - eq.rhs.subs(solution)) != 0:
            return None

    display_sub = Eq(
        eq2.lhs.subs(expressed, sympy.UnevaluatedExpr(expr)),
        eq2.rhs.subs(expressed, sympy.UnevaluatedExpr(expr)),
    )
    steps = [_input_step(raw), _simplified_step(eqs)]
    steps.append(
        Step(
            kind="derivation",
            title=f"Express {latex(expressed)} from the first equation",
            latex=latex(Eq(expressed, expr)),
        )
    )
    steps.append(
        Step(
            kind="derivation",
            title="Substitution into the second equation",
            latex=latex(display_sub),
        )
    )
    steps.append(
        Step(
            kind="derivation",
            title=f"Solution for {latex(other)}",
            latex=latex(Eq(other, other_value)),
        )
    )
    steps.append(
        Step(
            kind="derivation",
            title="Back-substitution into the expressed equation",
            latex=latex(Eq(expressed, expressed_value)),
        )
    )
    steps.append(_symbolic_step(solution))
    steps.append(_numeric_step(solution))
    for index, eq in enumerate(eqs, start=1):
        steps.append(
            _verification_step(eq, solution, f"Verification of equation {index}")
        )
    return steps


def _build_fraction(raw: str, equation: Eq) -> list[Step] | None:
    """Build derivation steps for a single equation with a denominator."""
    symbols = sorted(equation.free_symbols, key=lambda s: str(s))
    if len(symbols) != 1:
        return None
    var = symbols[0]
    try:
        diff = sympy.simplify(equation.lhs - equation.rhs)
        _, denominator = diff.as_numer_denom()
    except Exception:
        return None
    if denominator == 1 or denominator.free_symbols:
        return None
    try:
        found = sympy.solve(equation, var)
    except Exception:
        return None
    if len(found) != 1:
        return None
    root = sympy.simplify(found[0])
    if root.free_symbols:
        return None

    steps = [_input_step(raw), _simplified_step([equation])]
    steps.append(
        Step(
            kind="derivation",
            title=f"Multiply both sides by {latex(denominator)}",
            latex=latex(
                Eq(
                    sympy.Mul(denominator, equation.lhs, evaluate=False),
                    sympy.Mul(denominator, equation.rhs, evaluate=False),
                )
            ),
        )
    )
    steps.append(
        Step(
            kind="derivation",
            title="Cancel the denominator",
            latex=latex(
                Eq(
                    sympy.simplify(denominator * equation.lhs),
                    sympy.simplify(denominator * equation.rhs),
                )
            ),
        )
    )
    steps.append(
        Step(
            kind="symbolic",
            title="Symbolic solution",
            latex=latex(Eq(var, root)),
        )
    )
    steps.append(_numeric_step({var: root}))
    steps.append(
        _verification_step(
            equation, {var: root}, f"Verification for {latex(var)} = {latex(root)}"
        )
    )
    return steps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_derivation_steps(latex_input: str) -> list[Step] | None:
    """Build honest step-by-step derivation for basic equation types.

    Supported inputs:

    * quadratic equation in one variable;
    * linear equation ``ax+b=0`` in one variable;
    * 2x2 linear system (two equations, two unknowns);
    * single-variable equation containing ``frac`` with a constant
      denominator (e.g. ``frac{x}{2}=3``).

    Args:
        latex_input: Raw LaTeX equation or system of equations.

    Returns:
        List of :class:`Step` with kinds in ``input``, ``simplified``,
        ``derivation``, ``symbolic``, ``numeric`` and ``verification``,
        or ``None`` when the input type is not supported so the caller
        can use the legacy engine path. Never raises for bad input.
    """
    try:
        if not isinstance(latex_input, str) or not latex_input.strip():
            return None
        raw = latex_input.strip()
        equations = _parse_equations(raw)
        if equations is None:
            return None
        if len(equations) == 1:
            equation = equations[0]
            if not isinstance(equation, Eq):
                equation = Eq(equation, 0)
            if _contains_frac(raw):
                return _build_fraction(raw, equation)
            resolved = _single_var_poly(equation)
            if resolved is None:
                return None
            degree = resolved[1].degree()
            if degree == 2:
                return _build_quadratic(raw, equation)
            if degree == 1:
                return _build_linear(raw, equation)
            return None
        if len(equations) == 2:
            return _build_system(raw, equations)
        return None
    except Exception:
        return None
