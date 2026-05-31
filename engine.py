"""
Engine module for solving mathematical equations expressed in LaTeX.

The module provides a high‑level ``generate_solution_steps`` function that takes a
LaTeX string, parses it, solves it (symbolically and numerically when possible),
and returns a list of LaTeX strings representing each step of the solution.

Typical usage::

    from engine import generate_solution_steps

    latex_input = r"x^2 - 5x + 6 = 0"
    steps = generate_solution_steps(latex_input)
    for step in steps:
        print(step)

The implementation relies on **SymPy** for symbolic manipulation and parsing.
All public functions follow the Google Python style guide.
"""

from __future__ import annotations

import re
from typing import List, Tuple, Union, cast

import sympy
from sympy import Eq, Symbol
from sympy.parsing.latex import parse_latex
from sympy.printing.latex import latex

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _split_into_equations(latex: str) -> List[str]:
    """Split a LaTeX source that may contain several equations.

    The function recognises the following separators:

    * ``\\\\`` – typical line break in LaTeX environments.
    * ``\\n`` – a plain newline character.
    * ``;``   – a semicolon used by some authors.

    Empty fragments are discarded.

    Args:
        latex: Raw LaTeX string possibly containing several equations.

    Returns:
        A list of LaTeX strings, each representing a single equation.
    """
    # Normalise line endings and split.
    parts = re.split(r"(?:\\\\|;|\n)", latex)
    return [p.strip() for p in parts if p.strip()]


def _latex_to_sympy(eq_latex: str) -> sympy.Basic:
    """Convert a single LaTeX equation/expression to a SymPy object.

    If the LaTeX contains an ``=`` sign the left‑ and right‑hand sides are
    parsed separately and combined into a ``sympy.Eq`` instance.  Otherwise the
    expression is parsed as a plain SymPy expression.

    Args:
        eq_latex: LaTeX representing an equation or an expression.

    Returns:
        ``sympy.Eq`` for equations, otherwise a ``sympy.Expr``.
    """
    # Detect top‑level equality.  We avoid splitting on ``=`` inside
    # LaTeX commands (e.g. ``\\frac{a=b}{c}``) by using a simple heuristic:
    # split at the first ``=`` that is not inside braces.
    depth = 0
    split_index = -1
    for i, ch in enumerate(eq_latex):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
        elif ch == "=" and depth == 0:
            split_index = i
            break

    if split_index != -1:
        left = eq_latex[:split_index].strip()
        right = eq_latex[split_index + 1 :].strip()
        lhs = parse_latex(left)
        rhs = parse_latex(right)
        if lhs is None or rhs is None:
            raise ValueError(f"Cannot parse LaTeX fragment: {eq_latex}")
        return Eq(lhs, rhs)
    else:
        result = parse_latex(eq_latex)
        if result is None:
            raise ValueError(f"Cannot parse LaTeX: {eq_latex}")
        return result


def _solve_single(
    eq: sympy.Basic,
) -> Tuple[List[Symbol], List[Union[sympy.Expr, List[sympy.Expr]]]]:
    """Solve a single equation or expression for **all** free symbols at once.

    * If ``eq`` is not an ``Eq`` we treat it as ``eq == 0``.
    * ``sympy.solve`` is called with the full list of symbols.  For a single
      variable it returns a list of solutions (e.g. ``[2, 3]``).  For multiple
      variables it returns a list of dictionaries mapping each symbol to its
      solution – we take the first dictionary.
    * The return value mirrors the original contract: ``symbols`` is a list of the
      symbols solved for, and ``solutions`` is a list where each entry corresponds
      to the solution(s) for the symbol at the same index.  If a symbol has
      several solutions the entry is a list; otherwise it is a single SymPy
      expression.
    """
    # Ensure we work with an ``Eq``; otherwise treat expression as ``expr == 0``.
    if not isinstance(eq, Eq):
        eq = Eq(eq, 0)

    symbols = sorted(eq.free_symbols, key=lambda x: str(x))
    if not symbols:
        raise ValueError("No free symbols to solve for.")

    # ``sympy.solve`` with a list of symbols returns a list of dicts (or a list
    # of solutions for a single variable when ``dict=True`` is omitted).  Using
    # ``dict=True`` forces the dictionary form for multi‑variable cases.
    sol = sympy.solve(eq, symbols, dict=True)
    if not sol:
        # Fall back to solving each symbol individually if the system is
        # under‑determined.
        solutions: List[Union[sympy.Expr, List[sympy.Expr]]] = []
        for s in symbols:
            single = sympy.solve(eq, s)
            solutions.append(single)
        return cast(List[Symbol], symbols), solutions

    # Collect all solutions for each symbol from the list of dictionaries.
    # ``sol`` is a list of dicts, each dict representing one possible solution.
    collected: List[Union[sympy.Expr, List[sympy.Expr]]] = []
    for s in symbols:
        # Gather the value of ``s`` from every solution dict.
        vals = [d.get(s) for d in sol]
        # If there is only one distinct value keep it as a scalar, otherwise keep the list.
        if len(vals) == 1:
            collected.append(vals[0])
        else:
            collected.append(vals)
    return cast(List[Symbol], symbols), collected


def _numeric_approx(solution: sympy.Expr) -> sympy.Expr:
    """Return a numerical approximation (``evalf``) of ``solution``."""
    return solution.evalf()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_solution_steps(latex_input: str) -> List[str]:
    """Generate a LaTeX‑formatted solution chain for the given input.

    The function performs the following steps:

    1. **Parsing** – split the input into individual equations (or a system).
    2. **Simplification** – apply ``sympy.simplify`` to each equation.
    3. **Solving** – attempt a symbolic solution.  If a symbolic result exists,
       also compute a numerical approximation with ``evalf``.
    4. **Formatting** – each intermediate result is turned back into LaTeX.

    The returned list contains LaTeX strings in the order they should be shown
    to the user.  In case of an error a single LaTeX block explaining the
    problem is returned.

    Args:
        latex_input: Raw LaTeX string representing a single equation or a system
            of equations.

    Returns:
        List of LaTeX strings, each representing a step of the solution.
    """
    steps: List[str] = []

    try:
        # 1. Split input.
        # Early validation: the input must contain either an equality sign or a
        # LaTeX cases environment.  Otherwise we treat it as malformed.
        if "=" not in latex_input and r"\begin{cases}" not in latex_input:
            raise ValueError("Input does not contain a recognizable equation.")
        # Extract equations, handling a possible ``cases`` environment.
        if r"\begin{cases}" in latex_input:
            # Grab the content between \begin{cases} … \end{cases}
            match = re.search(
                r"\\begin\{cases\}(.*)\\end\{cases\}", latex_input, re.DOTALL
            )
            if match:
                inner = match.group(1)
                raw_eqs = [
                    line.strip() for line in re.split(r"\\\\", inner) if line.strip()
                ]
            else:
                raw_eqs = []
        else:
            raw_eqs = _split_into_equations(latex_input)
        if not raw_eqs:
            raise ValueError("No equations detected in the input.")

        sympy_eqs = [_latex_to_sympy(eq) for eq in raw_eqs]

        # 2. Show original input.
        steps.append(latex_input)

        # 3. Simplify each equation and display.
        simplified = []
        for eq in sympy_eqs:
            if isinstance(eq, Eq):
                lhs = sympy.simplify(eq.lhs)
                rhs = sympy.simplify(eq.rhs)
                simplified.append(Eq(lhs, rhs))
            else:
                simplified.append(sympy.simplify(eq))
        simpl_latex = r"\\ ".join(latex(s) for s in simplified)
        steps.append(simpl_latex)

        # 4. Solve.
        if len(simplified) == 1:
            # Single equation.
            symbols, solutions = _solve_single(simplified[0])
        else:
            # System of equations – solve simultaneously.
            eq_list = [e if isinstance(e, Eq) else Eq(e, 0) for e in simplified]
            symbols = sorted(
                {s for eq in eq_list for s in eq.free_symbols}, key=lambda x: str(x)
            )
            solutions_raw = sympy.solve(eq_list, symbols, dict=True)
            if not solutions_raw:
                raise ValueError("System could not be solved symbolically.")
            solutions = []
            for s in symbols:
                vals = [sol_dict.get(s) for sol_dict in solutions_raw]
                solutions.append(vals if len(vals) > 1 else vals[0])

        # 5. Format symbolic solutions.
        symbolic_parts = []
        for s, sol in zip(symbols, solutions):
            if isinstance(sol, (list, tuple)):
                for single in sol:
                    symbolic_parts.append(f"{latex(s)} = {latex(single)}")
            else:
                symbolic_parts.append(f"{latex(s)} = {latex(sol)}")
        steps.append(r",\; ".join(symbolic_parts))

        # 6. Numerical approximations.
        numeric_parts = []
        for s, sol in zip(symbols, solutions):
            if isinstance(sol, (list, tuple)):
                for single in sol:
                    numeric_parts.append(
                        f"{latex(s)} \\approx {latex(_numeric_approx(single))}"
                    )
            else:
                numeric_parts.append(
                    f"{latex(s)} \\approx {latex(_numeric_approx(sol))}"
                )
        steps.append(r",\; ".join(numeric_parts))

    except Exception as exc:  # pylint: disable=broad-except
        # Return a user‑friendly LaTeX error block.
        error_msg = f"\\text{{Error:}} \\text{{{str(exc)}}}"
        steps = [error_msg]

    return steps
