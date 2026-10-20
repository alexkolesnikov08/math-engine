#!/usr/bin/env python3
# math-engine/main.py
"""Command-line interface for the LaTeX equation solver.

Usage:
    python main.py "x^2 - 5x + 6 = 0"
    echo "x^2 - 5x + 6 = 0" | python main.py
    python main.py --file equation.tex --format json --precision 5

The script reads a LaTeX string representing one equation or a system,
builds structured solution steps (via ``steps.generate_steps_structured``
with fallback to future extended builders), and prints them in the
requested format.

Exit codes:
    0 -- success.
    1 -- no input provided (missing argument, empty stdin, unreadable file).
    2 -- the input could not be solved (error step) or invalid CLI usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from steps import Step, generate_steps_structured, steps_to_json

try:
    from step_builders import build_derivation_steps
except ImportError:
    build_derivation_steps = None  # type: ignore[assignment]

try:
    from extensions import try_extended_solve as _extensions_try_extended
except ImportError:
    _extensions_try_extended = None  # type: ignore[assignment]

try:
    from linalg import try_linalg_solve as _linalg_try_linalg
except ImportError:
    _linalg_try_linalg = None  # type: ignore[assignment]

try:
    from engine import (
        _latex_to_sympy,
        _numeric_approx,
        _solve_single,
        _split_into_equations,
    )
except ImportError:
    _latex_to_sympy = None  # type: ignore[assignment]
    _numeric_approx = None  # type: ignore[assignment]
    _solve_single = None  # type: ignore[assignment]
    _split_into_equations = None  # type: ignore[assignment]

try:
    from sympy import Eq
    from sympy import simplify as _sympy_simplify
    from sympy.parsing.latex import parse_latex as _parse_latex
    from sympy.printing.latex import latex as _sympy_latex
except ImportError:
    Eq = None  # type: ignore[assignment]
    _sympy_simplify = None  # type: ignore[assignment]
    _parse_latex = None  # type: ignore[assignment]
    _sympy_latex = None  # type: ignore[assignment]

_TITLES_FALLBACK: dict[str, str] = {
    "input": "Input",
    "simplified": "Simplified form",
    "symbolic": "Symbolic solution",
    "numeric": "Numerical approximation",
    "error": "Error",
}


def _parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Solve LaTeX equations and output step-by-step LaTeX solution."
    )
    parser.add_argument(
        "equation",
        nargs="?",
        help=(
            "LaTeX string of the equation or system to solve. "
            "If omitted, the script reads from standard input or --file."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "latex"],
        default="text",
        help="Output format: text (one LaTeX step per line), json, or latex (each step in \\[...\\]). Default: text.",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=15,
        help="Number of significant digits for numerical approximations. Default: 15.",
    )
    parser.add_argument(
        "--only-solution",
        action="store_true",
        help="Output only symbolic and numeric solution steps.",
    )
    parser.add_argument(
        "--file",
        dest="file",
        metavar="PATH",
        default=None,
        help="Read the equation from a file instead of the argument or stdin.",
    )
    return parser.parse_args()


def _normalize_extended_result(result: object) -> list[Step] | None:
    """Normalize a future extended builder result to a list of Steps."""
    if result is None:
        return None
    if not isinstance(result, (list, tuple)):
        return None
    items = list(result)
    if not items:
        return None
    first = items[0]
    if isinstance(first, Step):
        return [s for s in items if isinstance(s, Step)]
    if isinstance(first, dict):
        try:
            normalized: list[Step] = []
            for entry in items:
                if not isinstance(entry, dict):
                    return None
                kind = str(entry["kind"])
                latex_fragment = str(entry["latex"])
                title = str(entry.get("title", _TITLES_FALLBACK.get(kind, kind)))
                normalized.append(Step(kind=kind, title=title, latex=latex_fragment))
            return normalized
        except (KeyError, ValueError, TypeError):
            return None
    if isinstance(first, str):
        kinds_by_index = ("input", "simplified", "symbolic", "numeric")
        wrapped: list[Step] = []
        for index, fragment in enumerate(items):
            if not isinstance(fragment, str):
                return None
            kind = kinds_by_index[index] if index < len(kinds_by_index) else "derivation"
            wrapped.append(
                Step(
                    kind=kind,
                    title=_TITLES_FALLBACK.get(kind, kind),
                    latex=fragment,
                )
            )
        return wrapped
    return None


def _get_structured_steps(latex_input: str, precision: int = 15) -> list[Step]:
    """Return structured steps, preferring future extended builders.

    Each candidate builder is tried in order; a builder returning None
    (cannot handle the input) falls through to the next one. The legacy
    ``generate_steps_structured`` fallback always runs last.

    Args:
        latex_input: Raw LaTeX equation or system.
        precision: Desired numeric precision, forwarded to builders.

    Returns:
        List of structured steps.
    """
    candidates = (
        build_derivation_steps,
        _extensions_try_extended,
        _linalg_try_linalg,
    )
    for builder in candidates:
        if builder is None:
            continue
        try:
            try:
                produced = builder(latex_input, precision)  # type: ignore[operator]
            except TypeError:
                produced = builder(latex_input)  # type: ignore[operator]
        except Exception:
            continue
        if produced is None:
            continue
        normalized = _normalize_extended_result(produced)
        if normalized is not None:
            return normalized
    return generate_steps_structured(latex_input, precision)


def _recompute_numeric_latex(raw_input: str, precision: int) -> str | None:
    """Recompute the numeric approximation line with the given precision.

    Mirrors ``engine.generate_solution_steps`` solving flow but formats
    numerics with ``evalf(precision)`` so ``--precision`` visibly affects
    irrational results. Returns None when recomputation is impossible.
    """
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
            import sympy

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
        return None


def _apply_precision(
    steps: list[Step], raw_input: str, precision: int
) -> list[Step]:
    """Rewrite numeric steps with the requested precision.

    The legacy ``generate_steps_structured`` currently ignores precision
    (numeric formatting stays at the engine default), so the CLI owns
    precision handling: recompute the numeric line via SymPy with
    ``evalf(precision)``. Extended builders already receive precision;
    recomputation is idempotent for them.
    """
    numeric_indexes = [i for i, st in enumerate(steps) if st.kind == "numeric"]
    if not numeric_indexes:
        return steps
    recomputed = _recompute_numeric_latex(raw_input, precision)
    if recomputed is not None and len(numeric_indexes) == 1:
        idx = numeric_indexes[0]
        original = steps[idx]
        updated = Step(kind=original.kind, title=original.title, latex=recomputed)
        return steps[:idx] + [updated] + steps[idx + 1 :]
    # Fallback: re-evaluate symbolic RHS fragments (real-valued only).
    if _parse_latex is None or _sympy_latex is None:
        return steps
    symbolic_symbols: list[str] = []
    symbolic_solutions: list[str] = []
    for st in steps:
        if st.kind != "symbolic":
            continue
        for part in st.latex.split(r",\;"):
            if "=" not in part:
                continue
            left, right = part.split("=", 1)
            symbolic_symbols.append(left.strip())
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
            if "i" in solution_latex.lower():
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


def _filter_solution_only(steps: list[Step], only_solution: bool) -> list[Step]:
    """Keep only symbolic/numeric steps when requested."""
    if not only_solution:
        return steps
    filtered = [s for s in steps if s.kind in ("symbolic", "numeric")]
    return filtered if filtered else steps


_LEGACY_TEXT_KINDS: tuple[str, ...] = ("input", "simplified", "symbolic", "numeric")


def _filter_text_legacy(steps: list[Step]) -> list[Step]:
    """Keep only legacy kinds so default text stays 4 lines.

    Extended builders add derivation/verification steps; the default text
    format remains backward compatible (input/simplified/symbolic/numeric).
    """
    filtered = [s for s in steps if s.kind in _LEGACY_TEXT_KINDS]
    return filtered if filtered else steps


def _read_input(args: argparse.Namespace) -> str | None:
    """Resolve the equation from --file, positional arg, or stdin."""
    if args.file:
        try:
            return Path(args.file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            sys.stderr.write(f"Error: Cannot read file: {exc}\n")
            return None
    if args.equation:
        return str(args.equation).strip()
    if sys.stdin.isatty():
        return ""
    try:
        return sys.stdin.read().strip()
    except Exception:
        return ""


def main() -> None:
    """Entry point for the CLI utility."""
    args = _parse_arguments()

    raw_input = _read_input(args)
    if raw_input is None:
        sys.exit(1)
    if not raw_input:
        sys.stderr.write("Error: No equation provided.\n")
        sys.exit(1)

    steps = _get_structured_steps(raw_input, args.precision)
    steps = _apply_precision(steps, raw_input, args.precision)

    is_error = any(st.kind == "error" for st in steps)

    if args.format == "json":
        if is_error:
            message = next(
                (st.latex for st in steps if st.kind == "error"), "Solution error."
            )
            payload = {
                "input": raw_input,
                "steps": steps_to_json(steps),
                "error": message,
            }
            print(json.dumps(payload, ensure_ascii=False))
            sys.stderr.write(f"Error: {message}\n")
            sys.exit(2)
        display_steps = _filter_solution_only(steps, args.only_solution)
        payload = {
            "input": raw_input,
            "steps": steps_to_json(display_steps),
            "error": None,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    if is_error:
        message = next(
            (st.latex for st in steps if st.kind == "error"), "Solution error."
        )
        sys.stderr.write(f"Error: {message}\n")
        sys.exit(2)

    if args.format == "latex":
        display_steps = _filter_solution_only(steps, args.only_solution)
        for step in display_steps:
            print(f"\\[{step.latex}\\]")
        return

    display_steps = _filter_solution_only(
        _filter_text_legacy(steps), args.only_solution
    )
    for step in display_steps:
        print(step.latex)


if __name__ == "__main__":
    main()
