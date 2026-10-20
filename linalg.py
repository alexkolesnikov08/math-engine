"""Linear algebra solver for matrices and n x n linear systems.

Handles LaTeX inputs containing a single matrix environment
(``matrix``/``pmatrix``/``bmatrix``) or a linear system of equations.
Non-matrix / nonlinear inputs return ``None`` so the core engine can
handle them. Singular matrices raise ``ValueError``.
"""

from __future__ import annotations

import re

import sympy
from sympy import Eq, Matrix
from sympy.parsing.latex import parse_latex
from sympy.printing.latex import latex

from steps import Step

try:  # owned by another agent; may not exist yet.
    from parsing import parse_latex_equations  # type: ignore
except ImportError:
    parse_latex_equations = None  # type: ignore[assignment]

try:  # engine primitives used as fallback when parsing module is absent.
    from engine import _latex_to_sympy as _engine_latex_to_sympy  # type: ignore
    from engine import _split_into_equations as _engine_split  # type: ignore
except ImportError:
    _engine_latex_to_sympy = None  # type: ignore[assignment]
    _engine_split = None  # type: ignore[assignment]

_MATRIX_ENV_RE = re.compile(
    r"\\begin\{(matrix|pmatrix|bmatrix|vmatrix|Vmatrix)\}(.*?)\\end\{\1\}",
    re.DOTALL,
)

_CASES_RE = re.compile(r"\\begin\{cases\}(.*?)\\end\{cases\}", re.DOTALL)


def _parse_cell(cell: str) -> sympy.Basic:
    """Parse one matrix cell using the LaTeX parser only.

    There is intentionally no ``sympy.sympify`` fallback: ``sympify``
    evaluates arbitrary Python code (e.g.
    ``__import__('os').system(...)``), which is a remote code execution
    vulnerability. Unparseable cells raise ``ValueError`` instead.
    """
    text = cell.strip()
    if not text:
        raise ValueError("Empty matrix cell.")
    try:
        result = parse_latex(text)
    except Exception as exc:
        raise ValueError(f"Cannot parse matrix cell: {text!r}") from exc
    if result is None:
        raise ValueError(f"Cannot parse matrix cell: {text!r}")
    return result


def _manual_matrix_parse(body: str) -> Matrix:
    """Parse matrix body by splitting rows on ``\\\\`` and cols on ``&``."""
    raw_rows = [r.strip() for r in re.split(r"\\\\", body.strip()) if r.strip()]
    if not raw_rows:
        raise ValueError("Empty matrix environment.")
    rows = []
    for raw in raw_rows:
        cells = [c.strip() for c in raw.split("&")]
        rows.append([_parse_cell(c) for c in cells])
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise ValueError("Irregular matrix: rows have different lengths.")
    return Matrix(rows)


def _extract_matrices(latex_input: str) -> list[tuple[str, Matrix, str]]:
    """Extract ``(env, matrix, full_match)`` for each matrix environment."""
    found: list[tuple[str, Matrix, str]] = []
    for match in _MATRIX_ENV_RE.finditer(latex_input):
        env = match.group(1)
        body = match.group(2)
        full = match.group(0)
        parsed: Matrix | None = None
        try:
            via_latex = parse_latex(full)
            candidate = Matrix(via_latex)
            if candidate.shape[0] > 0 and candidate.shape[1] > 0:
                parsed = candidate
        except Exception:
            parsed = None
        if parsed is None:
            parsed = _manual_matrix_parse(body)
        found.append((env, parsed, full))
    return found


def _latex_to_sympy_local(eq_latex: str) -> sympy.Basic:
    """Convert one LaTeX equation/expression to SymPy (engine fallback)."""
    if _engine_latex_to_sympy is not None:
        return _engine_latex_to_sympy(eq_latex)
    depth = 0
    split_index = -1
    i = 0
    while i < len(eq_latex):
        ch = eq_latex[i]
        if ch == "\\" and i + 1 < len(eq_latex) and eq_latex[i + 1] in "{}":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
        elif ch == "=" and depth == 0:
            split_index = i
            break
        i += 1
    if split_index != -1:
        lhs = parse_latex(eq_latex[:split_index].strip())
        rhs = parse_latex(eq_latex[split_index + 1 :].strip())
        if lhs is None or rhs is None:
            raise ValueError(f"Cannot parse LaTeX fragment: {eq_latex}")
        return Eq(lhs, rhs)
    result = parse_latex(eq_latex)
    if result is None:
        raise ValueError(f"Cannot parse LaTeX: {eq_latex}")
    return result


def _split_fallback(latex_input: str) -> list[str]:
    """Split input into equation strings using engine primitives if present."""
    if r"\begin{cases}" in latex_input:
        match = _CASES_RE.search(latex_input)
        if match:
            inner = match.group(1)
            return [s.strip() for s in re.split(r"\\\\", inner) if s.strip()]
        return []
    if _engine_split is not None:
        return _engine_split(latex_input)
    parts = re.split(r"(?:\\\\|;|\n)", latex_input)
    return [p.strip() for p in parts if p.strip()]


def _fallback_parse_equations(latex_input: str) -> list[sympy.Basic] | None:
    """Parse equation strings to SymPy objects; None when not equations."""
    if "=" not in latex_input:
        return None
    raw_eqs = _split_fallback(latex_input)
    if len(raw_eqs) < 2:
        return None
    parsed: list[sympy.Basic] = []
    for raw in raw_eqs:
        try:
            parsed.append(_latex_to_sympy_local(raw))
        except Exception:
            return None
    return parsed


def _get_sympy_equations(latex_input: str) -> list[sympy.Basic] | None:
    """Parse input via ``parsing`` module when available, else fallback."""
    if parse_latex_equations is not None:
        try:
            result = parse_latex_equations(latex_input)  # type: ignore[operator]
            if result is None:
                return _fallback_parse_equations(latex_input)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                return list(result)
            return _fallback_parse_equations(latex_input)
        except Exception:
            return _fallback_parse_equations(latex_input)
    return _fallback_parse_equations(latex_input)


def _try_matrix_steps(latex_input: str, precision: int = 15) -> list[Step] | None:
    """Build determinant/inverse/rank steps for a single-matrix input."""
    _ = precision  # exact arithmetic; kept for API compatibility.
    matrices = _extract_matrices(latex_input)
    if len(matrices) != 1:
        return None
    if r"\begin{cases}" in latex_input:
        return None
    _, mat, _ = matrices[0]
    rows, cols = mat.shape
    steps: list[Step] = [Step(kind="input", title="Input", latex=latex_input)]

    if rows != cols:
        rank_val = int(mat.rank())
        steps.append(
            Step(
                kind="derivation",
                title="Rank",
                latex=(
                    r"\operatorname{rank}\left("
                    + latex(mat)
                    + r"\right) = "
                    + latex(rank_val)
                ),
            )
        )
        return steps

    det_val = mat.det()
    if det_val == 0:
        raise ValueError("Matrix is singular; inverse does not exist.")

    if rows == 2:
        a, b, c, d = mat[0, 0], mat[0, 1], mat[1, 0], mat[1, 1]
        det_latex = (
            r"\det\left("
            + latex(mat)
            + r"\right) = "
            + latex(a)
            + r" \cdot "
            + latex(d)
            + " - "
            + latex(b)
            + r" \cdot "
            + latex(c)
            + " = "
            + latex(det_val)
        )
    else:
        det_latex = (
            r"\det\left(" + latex(mat) + r"\right) = " + latex(det_val)
        )
    steps.append(Step(kind="derivation", title="Determinant", latex=det_latex))

    inv_mat = mat.inv()
    steps.append(
        Step(
            kind="symbolic",
            title="Inverse matrix",
            latex=latex(mat) + r"^{-1} = " + latex(inv_mat),
        )
    )

    rank_val = int(mat.rank())
    steps.append(
        Step(
            kind="derivation",
            title="Rank",
            latex=(
                r"\operatorname{rank}\left("
                + latex(mat)
                + r"\right) = "
                + latex(rank_val)
            ),
        )
    )

    product = (mat * inv_mat).applyfunc(sympy.simplify)
    identity = sympy.eye(rows)
    steps.append(
        Step(
            kind="verification",
            title="Verification",
            latex=(
                latex(mat)
                + r" \cdot "
                + latex(inv_mat)
                + " = "
                + latex(product)
                + " = "
                + latex(identity)
            ),
        )
    )
    return steps


def _build_linear_system(
    eqs: list[sympy.Basic],
) -> tuple[Matrix, Matrix, list[sympy.Symbol]] | None:
    """Build ``(A, b, symbols)`` for a square linear system, else None."""
    normed: list[Eq] = []
    for eq in eqs:
        if isinstance(eq, Eq):
            normed.append(eq)
        elif getattr(eq, "free_symbols", set()):
            normed.append(Eq(eq, 0))
        else:
            return None
    symbols = sorted(
        {s for eq in normed for s in eq.free_symbols}, key=lambda x: str(x)
    )
    n = len(normed)
    if n < 2 or len(symbols) != n:
        return None
    try:
        rows: list[list[sympy.Basic]] = []
        rhs: list[sympy.Basic] = []
        for eq in normed:
            expr = sympy.expand(eq.lhs - eq.rhs)
            if expr.atoms(sympy.Function):
                return None
            poly = sympy.Poly(expr, symbols)
            if poly is None or poly.total_degree() > 1:
                return None
            row = [poly.coeff_monomial(s) for s in symbols]
            const = poly.eval({s: 0 for s in symbols})
            rows.append(row)
            rhs.append(-const)
        return Matrix(rows), Matrix(rhs), symbols  # type: ignore[arg-type]
    except Exception:
        return None


def _try_system_steps(latex_input: str, precision: int = 15) -> list[Step] | None:
    """Build matrix-form/solution/substitution steps for a linear system."""
    eqs = _get_sympy_equations(latex_input)
    if eqs is None:
        return None
    built = _build_linear_system(eqs)
    if built is None:
        return None
    coeff, rhs, symbols = built
    if coeff.det() == 0:
        raise ValueError("System has no unique solution; matrix is singular.")
    solution = coeff.LUsolve(rhs)
    sol_map = dict(zip(symbols, list(solution)))

    col_symbols = Matrix(symbols)
    matrix_form = (
        latex(coeff) + " " + latex(col_symbols) + " = " + latex(rhs)
    )
    steps: list[Step] = [
        Step(kind="input", title="Input", latex=latex_input),
        Step(kind="derivation", title="Matrix form", latex=matrix_form),
    ]

    symbolic = r",\; ".join(
        f"{latex(s)} = {latex(v)}" for s, v in zip(symbols, list(solution))
    )
    steps.append(Step(kind="symbolic", title="Solution", latex=symbolic))

    numeric = r",\; ".join(
        f"{latex(s)} \\approx {latex(sympy.simplify(v).evalf(precision))}"
        for s, v in zip(symbols, list(solution))
    )
    steps.append(Step(kind="numeric", title="Numerical values", latex=numeric))

    checks: list[str] = []
    for eq in eqs:
        assert isinstance(eq, Eq)
        lhs_val = sympy.simplify(eq.lhs.subs(sol_map))
        rhs_val = sympy.simplify(eq.rhs.subs(sol_map))
        checks.append(
            latex(eq.lhs)
            + " = "
            + latex(eq.rhs)
            + r" \;\to\; "
            + latex(lhs_val)
            + " = "
            + latex(rhs_val)
            + r" \;\text{OK}"
        )
    steps.append(
        Step(
            kind="verification",
            title="Verification",
            latex=r"\\ ".join(checks),
        )
    )
    return steps


def try_linalg_solve(latex_input: str, precision: int = 15) -> list[Step] | None:
    """Solve matrices (det/inverse/rank) and n x n linear systems.

    Args:
        latex_input: Raw LaTeX with one matrix environment or a system
            of equations.
        precision: Digits used for numeric approximations of system solutions.

    Returns:
        List of :class:`Step` on success, ``None`` when the input is not
        a matrix or a linear system.

    Raises:
        ValueError: If the matrix (or system matrix) is singular.
    """
    if not latex_input or not latex_input.strip():
        return None
    matrix_steps = _try_matrix_steps(latex_input, precision=precision)
    if matrix_steps is not None:
        return matrix_steps
    return _try_system_steps(latex_input, precision=precision)
