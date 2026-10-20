"""Structured solution steps built on top of ``engine.generate_solution_steps``.

This module adds a small typed wrapper around the legacy ``List[str]``
API so API/UI/CLI consumers can rely on ``kind``/``title`` metadata
without breaking existing behaviour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

StepKind = Literal[
    "input",
    "simplified",
    "derivation",
    "symbolic",
    "numeric",
    "verification",
    "error",
]

_VALID_KINDS: tuple[str, ...] = (
    "input",
    "simplified",
    "derivation",
    "symbolic",
    "numeric",
    "verification",
    "error",
)


@dataclass(frozen=True)
class Step:
    """One solution step with machine-readable kind and display metadata."""

    kind: str
    title: str
    latex: str

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            msg = f"Unknown step kind: {self.kind!r}"
            raise ValueError(msg)
        if not self.title:
            msg = "Step title must not be empty."
            raise ValueError(msg)


_TITLES: dict[str, str] = {
    "input": "Input",
    "simplified": "Simplified form",
    "symbolic": "Symbolic solution",
    "numeric": "Numerical approximation",
    "error": "Error",
}

_KINDS_BY_INDEX: tuple[str, ...] = ("input", "simplified", "symbolic", "numeric")


def generate_steps_structured(latex_input: str, precision: int = 15) -> list[Step]:
    """Build structured steps from the legacy string-based engine.

    Args:
        latex_input: Raw LaTeX equation or system of equations.
        precision: Desired numeric precision. Currently accepted for
            forward compatibility; numeric formatting is still done
            by ``engine.generate_solution_steps`` (CLI agent owns it).

    Returns:
        List of :class:`Step`. Success → 4 steps
        (input/simplified/symbolic/numeric); failure → 1 error step.
    """
    from engine import (  # noqa: PLC0415 (lazy: avoids cycle with engine re-export)
        generate_solution_steps,
    )

    _ = precision  # reserved for future evalf precision handling
    raw_steps: list[str] = generate_solution_steps(latex_input)

    if len(raw_steps) == 1 and (
        "Error" in raw_steps[0] or r"\text{Error" in raw_steps[0]
    ):
        return [Step(kind="error", title=_TITLES["error"], latex=raw_steps[0])]

    steps: list[Step] = []
    for index, fragment in enumerate(raw_steps):
        kind = (
            _KINDS_BY_INDEX[index]
            if index < len(_KINDS_BY_INDEX)
            else "derivation"
        )
        steps.append(Step(kind=kind, title=_TITLES.get(kind, kind), latex=fragment))
    return steps


def steps_to_json(steps: list[Step]) -> list[dict]:
    """Convert steps to plain JSON-serializable dicts."""
    return [asdict(s) for s in steps]
