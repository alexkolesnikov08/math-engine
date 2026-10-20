"""Extended solvers for bare expressions, inequalities and basic calculus.

This module complements ``engine`` (equations) with handlers for input
forms the core engine does not cover:

* bare expressions without ``=`` (simplify / factor / expand / sample),
* single-variable inequalities (solution sets as ``Interval``/``Union``),
* basic calculus: derivatives (``\\frac{d}{dx}``), integrals (``\\int``)
  and limits (``\\lim``), each with an independent verification step.

The single public entry point is :func:`try_extended_solve`, which returns
``None`` for input owned by other solvers (e.g. ``Eq`` equations) and
raises :class:`ValueError` for any SymPy failure instead of building an
error :class:`Step` (the upper level owns error steps).
"""

from __future__ import annotations

import re

import sympy
from sympy.core.relational import Relational
from sympy.printing.latex import latex
from sympy.solvers.inequalities import solve_univariate_inequality

from steps import Step

try:  # Optional sibling module owned by another workstream.
    from parsing import normalize_latex, parse_latex_equations

    _PARSING_AVAILABLE = True
except ImportError:  # Fallback to engine helpers; do not create parsing.py.
    normalize_latex = None  # type: ignore[no-redef]
    parse_latex_equations = None  # type: ignore[no-redef]
    _PARSING_AVAILABLE = False

__all__ = ["try_extended_solve"]

# Command detection is done with regexes over the raw LaTeX source so no
# new DSL is introduced: ``\frac{d}{dx}`` (derivative), ``\int`` and ``\lim``.
_DIFF_RE = re.compile(r"\\frac\s*\{d[^}]*\}\s*\{d")
_INT_RE = re.compile(r"\\int\b")
_LIM_RE = re.compile(r"\\lim\b")
_CASES_RE = re.compile(r"\\begin\s*\{cases\}")

_CALCULUS_TYPES = (sympy.Derivative, sympy.Integral, sympy.Limit)
_INEQUALITY_OPS = ("<", "<=", ">", ">=")

_FINITE_DIFF_CANDIDATES = (0, 1, 2, -1)


def _is_calculus(text: str) -> bool:
    """Return True if the raw LaTeX contains a calculus command."""
    return bool(
        _DIFF_RE.search(text) or _INT_RE.search(text) or _LIM_RE.search(text)
    )


def _split_fragments(text: str) -> list:
    """Split the input into equation fragments (only the count matters here)."""
    if _PARSING_AVAILABLE:
        items = parse_latex_equations(normalize_latex(text))
        if isinstance(items, (list, tuple)):
            return list(items)
        return [items]
    from engine import _split_into_equations

    return _split_into_equations(text)


def _parse_single(text: str) -> sympy.Basic | None:
    """Parse one LaTeX fragment to SymPy, or return None if unparseable."""
    if _PARSING_AVAILABLE:
        try:
            result = parse_latex_equations(normalize_latex(text))
            if isinstance(result, (list, tuple)):
                return result[0] if result else None
            return result
        except Exception:
            return None
    try:
        from engine import _latex_to_sympy

        return _latex_to_sympy(text)
    except Exception:
        return None


def _sorted_symbols(expr: sympy.Basic) -> list[sympy.Symbol]:
    """Return free symbols of ``expr`` sorted by name (deterministic)."""
    return sorted(expr.free_symbols, key=lambda s: str(s))


def try_extended_solve(latex_input: str, precision: int = 15) -> list[Step] | None:
    """Try to solve input forms owned by this module.

    Args:
        latex_input: Raw LaTeX string (expression, inequality or calculus).
        precision: Digits used for ``evalf`` numeric demonstrations.

    Returns:
        List of :class:`Step` on success, ``None`` when the input belongs
        to another solver (equations, systems, multi-variable inequalities).

    Raises:
        ValueError: Any SymPy failure while handling an owned input.
    """
    text = latex_input.strip()
    if not text:
        return None
    # Guard: bare prose without any math signal belongs to nobody —
    # SymPy would parse words as a product of symbols (e.g. "this is not..."
    # → a⁴·d·l·...). Require a digit, operator, bracket or LaTeX command.
    if not re.search(r"[\\0-9^_+\-*/=<>!()\[\]|]", text):
        return None
    if _CASES_RE.search(text):
        return None
    if len(_split_fragments(text)) > 1:
        return None

    parsed = _parse_single(text)
    if isinstance(parsed, sympy.Eq):
        # Equations (with ``=``) belong to the core engine.
        return None

    if _is_calculus(text):
        if parsed is None:
            raise ValueError(f"Cannot parse calculus input: {text}")
        if not isinstance(parsed, _CALCULUS_TYPES):
            raise ValueError(f"Unsupported calculus construct: {text}")
        return _calculus_steps(text, parsed, precision)

    if parsed is None:
        return None
    if isinstance(parsed, Relational):
        if parsed.rel_op in _INEQUALITY_OPS:
            return _inequality_steps(text, parsed, precision)
        return None
    if isinstance(parsed, _CALCULUS_TYPES):
        return _calculus_steps(text, parsed, precision)
    return _expression_steps(text, parsed, precision)


# ---------------------------------------------------------------------------
# Bare expressions
# ---------------------------------------------------------------------------


def _numeric_sample(expr: sympy.Basic, precision: int) -> Step | None:
    """Build a numeric demonstration step, or None when ambiguous.

    Constant expressions are evaluated directly; single-variable ones are
    sampled at ``2``; multi-variable expressions are ambiguous, so the step
    is skipped.
    """
    try:
        symbols = _sorted_symbols(expr)
        if not symbols:
            return Step(
                kind="numeric",
                title="Numerical value",
                latex=latex(expr.evalf(precision)),
            )
        if len(symbols) > 1:
            return None
        var = symbols[0]
        value = expr.subs(var, 2).evalf(precision)
        return Step(
            kind="numeric",
            title="Numerical sample",
            latex=f"{latex(var)} = 2 \\Rightarrow "
            f"{latex(expr)} = {latex(value)}",
        )
    except Exception as exc:
        raise ValueError(f"Cannot evaluate expression numerically: {exc}") from exc


def _expression_steps(
    raw: str, expr: sympy.Basic, precision: int
) -> list[Step]:
    """Simplify / factor / expand a bare expression with a numeric sample."""
    try:
        simplified = sympy.simplify(expr)
        factored = sympy.factor(expr)
        expanded = sympy.expand(expr)
    except Exception as exc:
        raise ValueError(f"Cannot process expression: {exc}") from exc
    steps = [
        Step(kind="input", title="Input", latex=raw),
        Step(kind="simplified", title="Simplified form", latex=latex(simplified)),
        Step(kind="derivation", title="Factored form", latex=latex(factored)),
        Step(kind="derivation", title="Expanded form", latex=latex(expanded)),
    ]
    sample = _numeric_sample(expr, precision)
    if sample is not None:
        steps.append(sample)
    return steps


# ---------------------------------------------------------------------------
# Inequalities
# ---------------------------------------------------------------------------


def _inequality_sample_check(
    rel: Relational, var: sympy.Symbol, solution: sympy.Basic
) -> Step | None:
    """Verify the solution set with one sample point, if obtainable."""
    try:
        boundary = sympy.solve(sympy.simplify(rel.lhs - rel.rhs), var)
    except Exception:
        return None
    candidates: list[sympy.Basic] = []
    for root in boundary:
        try:
            if root.is_real:
                candidates.extend([root + 1, root - 1])
        except Exception:
            continue
    candidates.append(sympy.Integer(0))
    for cand in candidates:
        try:
            holds = bool(rel.subs(var, cand))
            in_set = bool(solution.contains(cand))
        except Exception:
            continue
        if holds and in_set:
            return Step(
                kind="verification",
                title="Verification",
                latex=f"{latex(var)} = {latex(cand)} \\Rightarrow "
                f"{latex(rel.subs(var, cand))}",
            )
    return None


def _inequality_steps(
    raw: str, rel: Relational, precision: int
) -> list[Step] | None:
    """Solve a single-variable inequality; None for multi-variable input."""
    _ = precision  # solution sets are exact; kept for API symmetry.
    symbols = _sorted_symbols(rel)
    if len(symbols) != 1:
        return None
    var = symbols[0]
    try:
        simplified = rel.func(sympy.simplify(rel.lhs), sympy.simplify(rel.rhs))
        solution = solve_univariate_inequality(rel, var, relational=False)
    except Exception as exc:
        raise ValueError(f"Cannot solve inequality: {exc}") from exc
    steps = [
        Step(kind="input", title="Input", latex=raw),
        Step(kind="simplified", title="Simplified form", latex=latex(simplified)),
        Step(kind="symbolic", title="Solution set", latex=latex(solution)),
    ]
    check = _inequality_sample_check(rel, var, solution)
    if check is not None:
        steps.append(check)
    return steps


# ---------------------------------------------------------------------------
# Calculus
# ---------------------------------------------------------------------------


def _calculus_steps(
    raw: str, node: sympy.Basic, precision: int
) -> list[Step]:
    """Dispatch a Derivative / Integral / Limit node to its solver."""
    try:
        if isinstance(node, sympy.Derivative):
            return _derivative_steps(raw, node, precision)
        if isinstance(node, sympy.Integral):
            return _integral_steps(raw, node, precision)
        if isinstance(node, sympy.Limit):
            return _limit_steps(raw, node, precision)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Cannot evaluate calculus input: {exc}") from exc
    raise ValueError(f"Unsupported calculus construct: {raw}")


def _derivative_check(
    expr: sympy.Basic, var: sympy.Symbol, result: sympy.Basic, precision: int
) -> Step:
    """Verify a derivative via finite differences, else via expanded form."""
    for cand in _FINITE_DIFF_CANDIDATES:
        try:
            point = sympy.sympify(cand)
            analytic = result.subs(var, point).evalf(precision)
            h = sympy.Float(10) ** -6
            numeric = (
                (expr.subs(var, point + h) - expr.subs(var, point - h)) / (2 * h)
            ).evalf(precision)
            a_f, n_f = float(analytic), float(numeric)
            if abs(a_f - n_f) <= 1e-4 * max(1.0, abs(a_f)):
                return Step(
                    kind="verification",
                    title="Verification",
                    latex=f"{latex(var)} = {latex(point)} \\Rightarrow "
                    f"{latex(analytic)} \\approx {latex(numeric)}"
                    r" \text{ (finite difference)}",
                )
        except Exception:
            continue
    try:
        alt = sympy.Derivative(sympy.expand(expr), var).doit()
        if sympy.simplify(alt - result) == 0:
            return Step(
                kind="verification",
                title="Verification",
                latex=f"{latex(alt)} = {latex(result)}",
            )
    except Exception as exc:
        raise ValueError(f"Cannot verify derivative: {exc}") from exc
    raise ValueError("Derivative verification failed.")


def _derivative_steps(
    raw: str, node: sympy.Derivative, precision: int
) -> list[Step]:
    """Differentiate a single-variable expression with a verification step."""
    variables = node.variables
    if len(set(variables)) != 1:
        raise ValueError("Only single-variable derivatives are supported.")
    var = variables[0]
    expr = node.expr
    try:
        result = node.doit()
    except Exception as exc:
        raise ValueError(f"Cannot differentiate: {exc}") from exc
    if isinstance(result, sympy.Derivative) or result.has(sympy.Derivative):
        raise ValueError("Derivative could not be evaluated symbolically.")
    return [
        Step(kind="input", title="Input", latex=raw),
        Step(
            kind="symbolic",
            title="Derivative",
            latex=f"{latex(node)} = {latex(result)}",
        ),
        _derivative_check(expr, var, result, precision),
    ]


def _integral_steps(
    raw: str, node: sympy.Integral, precision: int
) -> list[Step]:
    """Integrate (indefinite or definite) with an independent check step."""
    limits = node.limits
    if len(limits) != 1:
        raise ValueError("Only single-variable integrals are supported.")
    spec = limits[0]
    var = spec[0]
    integrand = node.function
    try:
        result = node.doit()
    except Exception as exc:
        raise ValueError(f"Cannot integrate: {exc}") from exc
    if result.has(sympy.Integral):
        raise ValueError("Integral could not be evaluated symbolically.")

    if len(spec) == 1:
        # Indefinite integral: differentiating the antiderivative must
        # reproduce the integrand.
        try:
            back = sympy.diff(result, var)
            check = sympy.simplify(back - integrand)
        except Exception as exc:
            raise ValueError(f"Cannot verify integral: {exc}") from exc
        if check != 0:
            raise ValueError("Integral verification failed.")
        return [
            Step(kind="input", title="Input", latex=raw),
            Step(
                kind="symbolic",
                title="Antiderivative",
                latex=f"{latex(node)} = {latex(result)}",
            ),
            Step(
                kind="verification",
                title="Verification",
                latex=f"{latex(back)} = {latex(integrand)}",
            ),
        ]

    # Definite integral: cross-check via antiderivative endpoint values.
    lower, upper = spec[1], spec[2]
    try:
        antideriv = sympy.integrate(integrand, var)
        if antideriv.has(sympy.Integral):
            raise ValueError("Antiderivative could not be evaluated symbolically.")
        endpoint_value = antideriv.subs(var, upper) - antideriv.subs(var, lower)
        check = sympy.simplify(endpoint_value - result)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Cannot verify definite integral: {exc}") from exc
    if check != 0:
        raise ValueError("Definite integral verification failed.")
    return [
        Step(kind="input", title="Input", latex=raw),
        Step(
            kind="symbolic",
            title="Definite integral",
            latex=f"{latex(node)} = {latex(result)}",
        ),
        Step(
            kind="numeric",
            title="Numerical value",
            latex=latex(result.evalf(precision)),
        ),
        Step(
            kind="verification",
            title="Verification",
            latex=f"{latex(endpoint_value)} = {latex(result)}",
        ),
    ]


def _limit_probes(
    func: sympy.Basic, var: sympy.Symbol, point: sympy.Basic, precision: int
) -> list[tuple[sympy.Basic, sympy.Basic]]:
    """Evaluate the function at points approaching the limit point."""
    probes: list[tuple[sympy.Basic, sympy.Basic]] = []
    try:
        if point.is_infinite:
            step = 1 if point == sympy.oo else -1
            candidates = [step * n for n in (10, 100)]
        else:
            candidates = [
                point + sympy.Rational(1, 1000),
                point - sympy.Rational(1, 1000),
            ]
    except Exception:
        return probes
    for cand in candidates:
        try:
            probes.append((cand, func.subs(var, cand).evalf(precision)))
        except Exception:
            continue
    return probes


def _limit_steps(raw: str, node: sympy.Limit, precision: int) -> list[Step]:
    """Evaluate a limit with one-sided and numeric spot checks."""
    func = node.args[0]
    args = node.args
    var, point = args[1], args[2]
    direction = args[3] if len(args) > 3 else "+-"
    try:
        result = node.doit()
    except Exception as exc:
        raise ValueError(f"Cannot evaluate limit: {exc}") from exc
    if isinstance(result, sympy.Limit) or result.has(sympy.Limit):
        raise ValueError("Limit could not be evaluated symbolically.")

    parts: list[str] = []
    if str(direction) not in ("+", "-"):
        for side in ("+", "-"):
            try:
                one_sided = sympy.Limit(func, var, point, dir=side).doit()
            except Exception:
                continue
            if isinstance(one_sided, sympy.Limit) or one_sided.has(sympy.Limit):
                continue
            parts.append(
                f"\\lim_{{{latex(var)} \\to {latex(point)}^{side}}}"
                f" {latex(func)} = {latex(one_sided)}"
            )
    for probe, value in _limit_probes(func, var, point, precision):
        parts.append(
            f"{latex(var)} = {latex(probe)} \\Rightarrow {latex(value)}"
        )
    if not parts:
        raise ValueError("Limit verification failed.")
    return [
        Step(kind="input", title="Input", latex=raw),
        Step(
            kind="symbolic",
            title="Limit",
            latex=f"{latex(node)} = {latex(result)}",
        ),
        Step(
            kind="verification",
            title="Verification",
            latex=r";\; ".join(parts),
        ),
    ]
