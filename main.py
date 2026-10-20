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
import sys
from pathlib import Path

from steps import Step, generate_steps_structured, steps_to_json
from precision import apply_precision

try:
    from step_builders import build_derivation_steps
except ImportError:
    build_derivation_steps = None  # type: ignore[assignment]
except Exception as exc:  # noqa: BLE001 - optional module; warn instead of silent skip
    sys.stderr.write(
        f"Warning: optional module step_builders failed to import: {exc}\n"
    )
    build_derivation_steps = None  # type: ignore[assignment]

try:
    from extensions import try_extended_solve as _extensions_try_extended
except ImportError:
    _extensions_try_extended = None  # type: ignore[assignment]
except Exception as exc:  # noqa: BLE001 - optional module; warn instead of silent skip
    sys.stderr.write(
        f"Warning: optional module extensions failed to import: {exc}\n"
    )
    _extensions_try_extended = None  # type: ignore[assignment]

try:
    from linalg import try_linalg_solve as _linalg_try_linalg
except ImportError:
    _linalg_try_linalg = None  # type: ignore[assignment]
except Exception as exc:  # noqa: BLE001 - optional module; warn instead of silent skip
    sys.stderr.write(f"Warning: optional module linalg failed to import: {exc}\n")
    _linalg_try_linalg = None  # type: ignore[assignment]

_TITLES_FALLBACK: dict[str, str] = {
    "input": "Input",
    "simplified": "Simplified form",
    "symbolic": "Symbolic solution",
    "numeric": "Numerical approximation",
    "error": "Error",
}


def _positive_int(value: str) -> int:
    """Parse a CLI integer that must be >= 1 (argparse exits 2 otherwise)."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer value: {value!r}")
    if parsed < 1:
        raise argparse.ArgumentTypeError("--precision must be >= 1")
    return parsed


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
        type=_positive_int,
        default=15,
        help="Number of significant digits for numerical approximations. Must be >= 1. Default: 15.",
    )
    parser.add_argument(
        "--full-steps",
        action="store_true",
        help="Show full derivation steps. Without it, json/latex/text "
        "outputs are filtered to the legacy 4 steps "
        "(input/simplified/symbolic/numeric).",
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


def _error_step(message: str) -> Step:
    """Build an error step owning a builder's ValueError message."""
    text = message.strip() or "Unknown error."
    return Step(
        kind="error",
        title=_TITLES_FALLBACK["error"],
        latex=rf"\text{{Error:}} \text{{{text}}}",
    )


# Explicit per-builder call contracts: build_derivation_steps takes only
# (latex) by contract, the rest accept (latex, precision). No try/except
# TypeError probing — the arity is fixed here.
def _candidate_builders() -> list[tuple[object, bool]]:
    """Return (builder, takes_precision) pairs in dispatch order."""
    builders: list[tuple[object, bool]] = []
    if build_derivation_steps is not None:
        builders.append((build_derivation_steps, False))
    if _extensions_try_extended is not None:
        builders.append((_extensions_try_extended, True))
    if _linalg_try_linalg is not None:
        builders.append((_linalg_try_linalg, True))
    return builders


def _get_structured_steps(latex_input: str, precision: int = 15) -> list[Step]:
    """Return structured steps, preferring future extended builders.

    Each candidate builder is tried in order. A builder returning None
    (or an empty list) does not own the input -- dispatch falls through
    to the next one. A builder raising ValueError owns the input but
    failed: its message becomes a single error Step, with no fallback.
    Unexpected exceptions fall through to the next builder. The legacy
    ``generate_steps_structured`` fallback always runs last.

    Args:
        latex_input: Raw LaTeX equation or system.
        precision: Desired numeric precision, forwarded to builders
            that accept it.

    Returns:
        List of structured steps.
    """
    for builder, takes_precision in _candidate_builders():
        try:
            if takes_precision:
                produced = builder(latex_input, precision)  # type: ignore[operator]
            else:
                produced = builder(latex_input)  # type: ignore[operator]
        except ValueError as exc:
            return [_error_step(str(exc))]
        except Exception:
            continue
        if produced is None:
            continue
        normalized = _normalize_extended_result(produced)
        if normalized is not None:
            return normalized
    return generate_steps_structured(latex_input, precision)


def _filter_solution_only(steps: list[Step], only_solution: bool) -> list[Step]:
    """Keep only symbolic/numeric steps when requested."""
    if not only_solution:
        return steps
    filtered = [s for s in steps if s.kind in ("symbolic", "numeric")]
    return filtered if filtered else steps


_LEGACY_TEXT_KINDS: tuple[str, ...] = ("input", "simplified", "symbolic", "numeric")


def _filter_text_legacy(steps: list[Step]) -> list[Step]:
    """Keep only legacy kinds so default outputs stay 4 steps.

    Extended builders add derivation/verification steps; the default
    text/json/latex formats remain backward compatible
    (input/simplified/symbolic/numeric) unless --full-steps is given.
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
    steps = apply_precision(steps, raw_input, args.precision)

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
                "version": "v2",
            }
            print(json.dumps(payload, ensure_ascii=False))
            sys.stderr.write(f"Error: {message}\n")
            sys.exit(2)
        display_steps = _filter_solution_only(steps, args.only_solution)
        if not args.full_steps:
            display_steps = _filter_text_legacy(display_steps)
        payload = {
            "input": raw_input,
            "steps": steps_to_json(display_steps),
            "error": None,
            "version": "v2",
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
        if not args.full_steps:
            display_steps = _filter_text_legacy(display_steps)
        for step in display_steps:
            print(f"\\[{step.latex}\\]")
        return

    if args.full_steps:
        display_steps = _filter_solution_only(steps, args.only_solution)
    else:
        display_steps = _filter_solution_only(
            _filter_text_legacy(steps), args.only_solution
        )
    for step in display_steps:
        print(step.latex)


if __name__ == "__main__":
    main()
