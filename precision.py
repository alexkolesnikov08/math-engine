"""Shared numeric-precision helpers for the CLI and the API.

Both front ends dispatch to the same step builders and must therefore
apply ``--precision``/``precision`` identically: recompute the numeric
steps with ``evalf(precision)`` when the engine can reproduce the result,
otherwise keep the builder's own formatting instead of writing garbage.

Silent-keep contract: every early ``None``/unchanged return below means
"precision was NOT applied to this output". The callers intentionally do
not fabricate digits in that case; the tests lock this behaviour
(precision helpers never invent numbers, they only narrow or preserve).
"""

from __future__ import annotations

import re
import sys

from steps import Step

try:
    import sympy
    from engine import (
        _latex_to_sympy,
        _numeric_approx,
        _solve_single,
        _split_into_equations,
    )
    from sympy import Eq
    from sympy import simplify as _sympy_simplify
    from sympy.parsing.latex import parse_latex as _parse_latex
    from sympy.printing.latex import latex as _sympy_latex
except ImportError:
    sympy = None  # type: ignore[assignment]
    _latex_to_sympy = None  # type: ignore[assignment]
    _numeric_approx = None  # type: ignore[assignment]
    _solve_single = None  # type: ignore[assignment]
    _split_into_equations = None  # type: ignore[assignment]
    Eq = None  # type: ignore[assignment]
    _sympy_simplify = None  # type: ignore[assignment]
    _parse_latex = None  # type: ignore[assignment]
    _sympy_latex = None  # type: ignore[assignment]
    _ENGINE_AVAILABLE = False
except Exception as exc:  # noqa: BLE001 - optional import; warn instead of silent skip
    print(
        f"Warning: precision engine helpers unavailable: {exc}",
        file=sys.stderr,
    )
    sympy = None  # type: ignore[assignment]
    _latex_to_sympy = None  # type: ignore[assignment]
    _numeric_approx = None  # type: ignore[assignment]
    _solve_single = None  # type: ignore[assignment]
    _split_into_equations = None  # type: ignore[assignment]
    Eq = None  # type: ignore[assignment]
    _sympy_simplify = None  # type: ignore[assignment]
    _parse_latex = None  # type: ignore[assignment]
    _sympy_latex = None  # type: ignore[assignment]
    _ENGINE_AVAILABLE = False
else:
    _ENGINE_AVAILABLE = True


def _symbolic_left_sides(steps: list[Step]) -> list[str]:
    """Collect left-hand sides of ``=`` from symbolic steps."""
    lefts: list[str] = []
    for step in steps:
        if step.kind != "symbolic":
            continue
        for part in step.latex.split(r"\;"):
            if "=" not in part:
                continue
            left = part.split("=", 1)[0].strip().rstrip(",").strip()
            if left:
                lefts.append(left)
    return lefts


def _has_imaginary_unit(solution_latex: str) -> bool:
    """Return True when a symbolic solution involves ``sympy.I``.

    The right-hand side is parsed and checked structurally via
    ``simplify(expr).has(sympy.I)``, so names that merely contain the
    letter "i" (``\\pi``, ``\\infty``, ``\\sin``, ``\\lim``) are still
    recomputed. Unparseable fragments conservatively count as imaginary
    (left untouched) to avoid writing garbage.
    """
    if _parse_latex is None or sympy is None:
        return True
    try:
        expr = _parse_latex(solution_latex)
    except Exception:
        return True
    try:
        return bool(sympy.simplify(expr).has(sympy.I))
    except Exception:
        return True


def recompute_numeric_latex(
    steps: list[Step], raw_input: str, precision: int
) -> str | None:
    """Recompute the numeric approximation line with the given precision.

    Mirrors ``engine.generate_solution_steps`` solving flow but formats
    numerics with ``evalf(precision)``.

    The recomputation is only trusted when the engine converges on the
    same symbols as the symbolic steps (compared as rendered symbol
    LaTeX). Otherwise the builder owned this input in a way the engine
    cannot reproduce (e.g. matrix or calculus steps), so ``None`` is
    returned and the caller keeps the builder's own numeric line
    instead of writing mismatched numbers.

    Returns None when recomputation is impossible or untrusted.
    """
    if not _ENGINE_AVAILABLE:
        # Engine helpers missing: keep existing formatting, do not invent digits.
        return None
    if (
        _latex_to_sympy is None
        or _numeric_approx is None
        or _solve_single is None
        or _split_into_equations is None
        or Eq is None
        or _sympy_simplify is None
        or _sympy_latex is None
    ):
        return None
    try:
        if r"\begin{cases}" in raw_input:
            match = re.search(
                r"\\begin\{cases\}(.*)\\end\{cases\}", raw_input, re.DOTALL
            )
            if match:
                inner = match.group(1)
                raw_eqs = [
                    line.strip() for line in re.split(r"\\\\", inner) if line.strip()
                ]
            else:
                raw_eqs = []
        else:
            raw_eqs = _split_into_equations(raw_input)
        if not raw_eqs:
            return None
        sympy_eqs = [_latex_to_sympy(eq) for eq in raw_eqs]
        simplified = []
        for eq in sympy_eqs:
            if isinstance(eq, Eq):
                lhs = _sympy_simplify(eq.lhs)
                rhs = _sympy_simplify(eq.rhs)
                simplified.append(Eq(lhs, rhs))
            else:
                simplified.append(_sympy_simplify(eq))
        if len(simplified) == 1:
            symbols, solutions = _solve_single(simplified[0])
        else:
            eq_list = [e if isinstance(e, Eq) else Eq(e, 0) for e in simplified]
            symbols = sorted(
                {s for eq in eq_list for s in eq.free_symbols}, key=lambda x: str(x)
            )
            solutions_raw = sympy.solve(eq_list, symbols, dict=True)
            if not solutions_raw:
                return None
            solutions = []
            for s in symbols:
                vals = [sol_dict.get(s) for sol_dict in solutions_raw]
                solutions.append(vals if len(vals) > 1 else vals[0])
        # Owner check: the engine must speak about the same symbols as the
        # symbolic steps, otherwise its numbers do not belong to this output.
        expected = {_sympy_latex(s) for s in symbols}
        actual = set(_symbolic_left_sides(steps))
        if not actual or expected != actual:
            return None
        numeric_parts = []
        for s, sol in zip(symbols, solutions):
            if isinstance(sol, (list, tuple)):
                for single in sol:
                    numeric_parts.append(
                        f"{_sympy_latex(s)} \\approx {_sympy_latex(_numeric_approx(single, precision))}"
                    )
            else:
                numeric_parts.append(
                    f"{_sympy_latex(s)} \\approx {_sympy_latex(_numeric_approx(sol, precision))}"
                )
        return r",\; ".join(numeric_parts)
    except Exception:
        # Anything the engine cannot handle (unparseable, unsolvable):
        # keep the builder's formatting, do not invent digits.
        return None


def apply_precision(
    steps: list[Step], raw_input: str, precision: int
) -> list[Step]:
    """Rewrite numeric steps with the requested precision.

    The legacy ``generate_steps_structured`` currently ignores precision
    (numeric formatting stays at the engine default), so the front ends
    own precision handling: recompute the numeric line via SymPy with
    ``evalf(precision)``. Extended builders already receive precision;
    recomputation is idempotent for them.

    Steps without a numeric kind, or outputs the engine cannot reproduce
    (``recompute_numeric_latex`` returns None), are returned unchanged:
    precision is never faked.
    """
    numeric_indexes = [i for i, st in enumerate(steps) if st.kind == "numeric"]
    if not numeric_indexes:
        return steps
    recomputed = recompute_numeric_latex(steps, raw_input, precision)
    if recomputed is not None and len(numeric_indexes) == 1:
        idx = numeric_indexes[0]
        original = steps[idx]
        updated = Step(kind=original.kind, title=original.title, latex=recomputed)
        return steps[:idx] + [updated] + steps[idx + 1 :]
    # Fallback: re-evaluate symbolic RHS fragments, skipping genuinely
    # complex solutions (checked structurally, not by substring).
    if _parse_latex is None or _sympy_latex is None or sympy is None:
        # No SymPy available: keep existing formatting, do not invent digits.
        return steps
    symbolic_solutions: list[str] = []
    for st in steps:
        if st.kind != "symbolic":
            continue
        for part in st.latex.split(r",\;"):
            if "=" not in part:
                continue
            _, right = part.split("=", 1)
            symbolic_solutions.append(right.strip())
    if not symbolic_solutions:
        return steps
    rebuilt_steps = list(steps)
    solution_cursor = 0
    for idx in numeric_indexes:
        st = rebuilt_steps[idx]
        fragments = st.latex.split(r",\;")
        rebuilt_fragments: list[str] = []
        for frag in fragments:
            if r"\approx" not in frag:
                rebuilt_fragments.append(frag.strip())
                continue
            if solution_cursor >= len(symbolic_solutions):
                rebuilt_fragments.append(frag.strip())
                solution_cursor += 1
                continue
            left, _old = frag.split(r"\approx", 1)
            symbol_latex = left.strip()
            solution_latex = symbolic_solutions[solution_cursor]
            solution_cursor += 1
            if _has_imaginary_unit(solution_latex):
                rebuilt_fragments.append(frag.strip())
                continue
            try:
                expr = _parse_latex(solution_latex)
                approx = expr.evalf(precision)
                rebuilt_fragments.append(
                    f"{symbol_latex} \\approx {_sympy_latex(approx)}"
                )
            except Exception:
                rebuilt_fragments.append(frag.strip())
        rebuilt_steps[idx] = Step(
            kind=st.kind, title=st.title, latex=r",\; ".join(rebuilt_fragments)
        )
    return rebuilt_steps
