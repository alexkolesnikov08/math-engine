"""Robust LaTeX parsing helpers for math equations.

This module provides a small, dependency-light layer on top of
``sympy.parsing.latex.parse_latex``:

* :func:`normalize_latex` rewrites common raw/LaTeX spellings into a form
  the SymPy LaTeX parser understands (bare ``sin`` -> ``\\sin``,
  ``\\left``/``\\right`` stripping, single-token exponents into braces, ...).
* :func:`parse_latex_equations` splits a (possibly multi-equation) LaTeX
  string on top-level relational operators and returns SymPy objects
  (``Eq``, inequalities, or plain expressions).

The module intentionally does **not** solve anything; solving stays in
``engine.py`` (integration is owned by another agent).
"""

from __future__ import annotations

import re
from typing import Callable, Union

import sympy
from sympy import Ge, Gt, Le, Lt, Ne
from sympy.core.relational import Relational
from sympy.parsing.latex import parse_latex

__all__ = ["normalize_latex", "parse_latex_equations"]

SympyEquation = Union[sympy.Eq, Relational, sympy.Basic]

# LaTeX relational commands recognised at top level, mapped to builders.
_REL_COMMANDS: dict[str, Callable[[sympy.Basic, sympy.Basic], Relational]] = {
    "\\leq": Le,
    "\\le": Le,
    "\\lt": Lt,
    "\\geq": Ge,
    "\\ge": Ge,
    "\\gt": Gt,
    "\\neq": Ne,
    "\\ne": Ne,
}
_REL_COMMAND_RE = re.compile(r"\\(leq|geq|neq|le|ge|lt|gt|ne)(?![A-Za-z])")

# Bare function names that get a backslash when used as functions.
# ``pi`` is always a constant; trig/sqrt only when followed by an argument
# (so a hypothetical variable named ``sin`` in ``sin = 1`` is left alone).
_BARE_TRIG_RE = re.compile(
    r"(?<![\\A-Za-z])(sin|cos|tan|sqrt)(?![A-Za-z])(?=\s*[\(\{A-Za-z0-9\\])"
)
_BARE_PI_RE = re.compile(r"(?<![\\A-Za-z])pi(?![A-Za-z])")


def normalize_latex(s: str) -> str:
    """Normalize a LaTeX math string for :func:`parse_latex`.

    Applied rewrites (in order):

    1. ``\\left``/``\\right`` prefixes are stripped (delimiters are kept);
       invisible ``\\left.``/``\\right.`` are removed entirely.
    2. Alignment ``&`` characters are removed.
    3. ``\\cdot``/``\\times`` become ``*`` (``\\div`` becomes ``/``).
    4. Bare ``sin``/``cos``/``tan``/``sqrt`` used as functions gain a
       backslash; bare ``pi`` becomes ``\\pi``.
    5. ``\\sqrt x`` (space-separated argument) becomes ``\\sqrt{x}``.
    6. Single-token exponents gain braces: ``x^2`` -> ``x^{2}``,
       ``x^12`` -> ``x^{12}``, ``x^\\pi`` -> ``x^{\\pi}``.
    7. ``\\pi`` and ``\\infty`` are passed through unchanged.

    Args:
        s: Raw LaTeX (or plain-text math) string.

    Returns:
        Normalized LaTeX string.

    Raises:
        TypeError: If ``s`` is not a string.
    """
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}.")

    out = s.strip()
    # Invisible delimiters first (the trailing dot must go too).
    out = re.sub(r"\\left\.", "", out)
    out = re.sub(r"\\right\.", "", out)
    out = out.replace("\\left", "").replace("\\right", "")
    out = out.replace("&", "")
    out = out.replace("\\cdot", "*").replace("\\times", "*")
    out = out.replace("\\div", "/")
    out = _BARE_TRIG_RE.sub(r"\\\1", out)
    out = _BARE_PI_RE.sub(r"\\pi", out)
    out = re.sub(r"\\sqrt(?![{\[])\s*([A-Za-z0-9])", r"\\sqrt{\1}", out)
    out = re.sub(r"\^(?!\{)\s*(\d+|\\[A-Za-z]+|[A-Za-z])", r"^{\1}", out)
    return out.strip()


def _strip_environments(s: str) -> str:
    """Extract the body of ``\\begin{...}...\\end{...}`` blocks.

    For ``cases``/``aligned``-style input only the inner lines matter;
    other environments are unwrapped the same way.
    """
    match = re.search(
        r"\\begin\{[A-Za-z*]+\}(.*)\\end\{[A-Za-z*]+\}", s, re.DOTALL
    )
    if match:
        return match.group(1)
    return s


def _split_fragments(s: str) -> list[str]:
    """Split input into single-equation fragments.

    Separators: LaTeX line break ``\\\\``, ``;`` (unless escaped as ``\\;``),
    and plain newlines. Empty fragments are discarded.
    """
    body = _strip_environments(s)
    parts = re.split(r"(?:\\\\|(?<!\\);|\n)", body)
    return [p.strip() for p in parts if p.strip()]


def _find_top_level_op(frag: str) -> tuple[str, int, int] | None:
    """Find the first top-level relational operator.

    Bracket depth for ``{}``, ``()`` and ``[]`` is tracked so operators
    inside groups (e.g. ``=`` in ``\\frac{a=b}{c}``) are ignored. This
    extends the brace-only heuristic from ``engine.py``.

    Returns:
        ``(op, start, end)`` triple or ``None`` when there is no
        top-level relational operator.
    """
    depth = 0
    i = 0
    n = len(frag)
    while i < n:
        ch = frag[i]
        if ch == "\\":
            cmd = _REL_COMMAND_RE.match(frag, i)
            if cmd and depth == 0:
                return cmd.group(0), cmd.start(), cmd.end()
            # Skip escaped char or a whole command name.
            nxt = re.match(r"\\[A-Za-z]+", frag[i:])
            if nxt:
                i += len(nxt.group(0))
            else:
                i += 2
            continue
        if ch in "{[(":
            depth += 1
        elif ch in ")]}":
            depth = max(depth - 1, 0)
        elif depth == 0:
            two = frag[i : i + 2]
            if two in ("<=", ">=", "!=", "=="):
                return two, i, i + 2
            if ch in "=<>":
                return ch, i, i + 1
            if ch in ("≤", "≥", "≠"):
                return ch, i, i + 1
        i += 1
    return None


def _build_relational(
    op: str, lhs: sympy.Basic, rhs: sympy.Basic
) -> sympy.Basic:
    """Combine two parsed sides according to the operator text."""
    if op in ("=", "=="):
        return sympy.Eq(lhs, rhs)
    if op == "<":
        return Lt(lhs, rhs)
    if op == ">":
        return Gt(lhs, rhs)
    if op in ("<=", "\\le", "\\leq", "\\lt", "≤"):
        return Le(lhs, rhs)
    if op in (">=", "\\ge", "\\geq", "\\gt", "≥"):
        return Ge(lhs, rhs)
    if op in ("!=", "\\neq", "\\ne", "≠"):
        return Ne(lhs, rhs)
    raise ValueError(f"Unsupported relational operator: {op!r}.")


def _parse_side(text: str, frag: str) -> sympy.Basic:
    """Parse one side of an equation, wrapping errors in ValueError."""
    normalized = normalize_latex(text)
    if not normalized:
        raise ValueError(f"Cannot parse empty side of fragment: {frag!r}.")
    try:
        result = parse_latex(normalized)
    except Exception as exc:
        raise ValueError(
            f"Cannot parse LaTeX fragment: {frag!r} ({exc})"
        ) from exc
    if result is None:
        raise ValueError(f"Cannot parse LaTeX fragment: {frag!r}.")
    if isinstance(result, Relational):
        # Chained comparison left over in one side, e.g. ``1 < x < 5``.
        raise ValueError(
            f"Chained comparison is not supported: {frag!r}."
        )
    # The SymPy LaTeX parser yields ``Symbol('pi')`` for ``\pi`` while
    # ``\infty`` already becomes ``oo``; map pi to the true constant.
    result = result.subs(sympy.Symbol("pi"), sympy.pi)
    return result


def parse_latex_equations(s: str) -> list[sympy.Basic]:
    """Parse a LaTeX string into SymPy equations/expressions.

    The input may hold several equations separated by ``\\\\``, ``;`` or
    newlines, optionally wrapped in a ``cases``-style environment. Each
    fragment is split on its first top-level relational operator
    (``=``, ``<``, ``>``, ``<=``, ``>=``, ``!=``, ``==``,
    ``\\le``/``\\leq``, ``\\ge``/``\\geq``, ``\\neq`` and the unicode
    counterparts ``≤``/``≥``/``≠``) into an ``Eq``/inequality; fragments
    without an operator become plain expressions.

    Args:
        s: Raw LaTeX string with one or more equations.

    Returns:
        List of ``Eq``/inequality/expression objects, one per fragment.

    Raises:
        ValueError: If the input is empty or any fragment fails to parse.
            The message always contains the offending fragment.
        TypeError: If ``s`` is not a string.
    """
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__}.")
    fragments = _split_fragments(s)
    if not fragments:
        raise ValueError(f"No equations detected in the input: {s!r}.")

    parsed: list[sympy.Basic] = []
    for frag in fragments:
        found = _find_top_level_op(frag)
        if found is None:
            parsed.append(_parse_side(frag, frag))
            continue
        op, start, end = found
        lhs = _parse_side(frag[:start], frag)
        rhs = _parse_side(frag[end:], frag)
        parsed.append(_build_relational(op, lhs, rhs))
    return parsed
