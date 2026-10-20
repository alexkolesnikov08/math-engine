"""FastAPI service exposing the math-engine solver.

Endpoints:
    GET /health -- liveness probe.
    GET / -- static KaTeX preview page.
    POST /solve -- solve a LaTeX equation, returning structured steps.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from precision import apply_precision
from steps import Step, generate_steps_structured, steps_to_json

app = FastAPI(title="math-engine API")

_STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"

# Explicit per-builder call contracts in dispatch order: attribute name
# mapped to whether it accepts (latex, precision). step_builders owns a
# single-argument builder by contract; the rest take precision.
_BUILDER_SPECS: dict[str, tuple[tuple[str, bool], ...]] = {
    "step_builders": (("build_derivation_steps", False),),
    "extensions": (("try_extended_solve", True),),
    "linalg": (("try_linalg_solve", True),),
}

_LEGACY_KINDS: tuple[str, ...] = ("input", "simplified", "symbolic", "numeric")


class SolveRequest(BaseModel):
    """Request body for POST /solve."""

    latex: str = Field(description="LaTeX equation or system to solve.")
    precision: int = Field(default=15, ge=1, le=50, description="Numeric precision.")
    verbose: bool = Field(
        default=False,
        description="Return full derivation steps instead of the legacy 4.",
    )


class StepModel(BaseModel):
    """One solution step."""

    kind: str
    title: str
    latex: str


class SolveResponse(BaseModel):
    """Response body for POST /solve."""

    input: str
    steps: list[StepModel]
    error: str | None = None
    version: str = "v2"


def _error_step(message: str) -> Step:
    """Build an error step owning a builder's ValueError message."""
    text = message.strip() or "Unknown error."
    return Step(kind="error", title="Error", latex=rf"\text{{Error:}} \text{{{text}}}")


def _build_steps(latex: str, precision: int) -> Any:
    """Dispatch to the richest available step builder.

    Tries optional ``step_builders``/``extensions``/``linalg`` modules
    first (same dispatch order as the CLI), falling back to
    :func:`steps.generate_steps_structured` when they are absent.

    A builder returning None (or an empty list) does not own the input --
    dispatch falls through to the next one. A builder raising ValueError
    owns the input but failed: its message becomes a single error Step,
    with no fallback. Missing modules are silently skipped; modules that
    fail to import for another reason emit a stderr warning.
    """
    for module_name, specs in _BUILDER_SPECS.items():
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        except Exception as exc:  # noqa: BLE001 - warn instead of silent skip
            print(
                f"Warning: optional builder module {module_name!r} "
                f"failed to import: {exc}",
                file=sys.stderr,
            )
            continue
        for attr, takes_precision in specs:
            fn = getattr(module, attr, None)
            if not callable(fn):
                continue
            try:
                if takes_precision:
                    result = fn(latex, precision)
                else:
                    result = fn(latex)
            except ValueError as exc:
                return [_error_step(str(exc))]
            except Exception:
                # Optional builder failed; try next candidate.
                continue
            if result is None:
                continue
            if isinstance(result, (list, tuple)) and len(result) == 0:
                continue
            return result
    return generate_steps_structured(latex, precision)


def _steps_to_payload(steps: Any) -> list[dict]:
    """Normalize builder output to a list of {kind, title, latex} dicts."""
    if not steps:
        return []
    first = steps[0]
    if isinstance(first, dict):
        return [
            {
                "kind": s.get("kind", "derivation"),
                "title": s.get("title") or s.get("kind", "step"),
                "latex": s.get("latex", ""),
            }
            for s in steps
        ]
    if isinstance(first, str):
        return [
            {"kind": "derivation", "title": f"Step {i + 1}", "latex": s}
            for i, s in enumerate(steps)
        ]
    # Assume list[Step] dataclass instances.
    return steps_to_json(steps)


def _extract_error(payload: list[dict]) -> str | None:
    """Return the error message when any step reports kind == error."""
    for step in payload:
        if isinstance(step, dict) and step.get("kind") == "error":
            return step.get("latex") or "Unknown error."
    return None


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the static KaTeX preview page."""
    return FileResponse(str(_STATIC_INDEX), media_type="text/html")


@app.post("/solve", response_model=SolveResponse)
def solve(request: SolveRequest) -> JSONResponse | dict:
    """Solve a LaTeX equation and return structured steps."""
    if not request.latex.strip():
        raise HTTPException(status_code=422, detail="latex must not be empty.")
    try:
        steps = _build_steps(request.latex, request.precision)
    except Exception as exc:  # noqa: BLE001 - mapped to 500 below
        return JSONResponse(
            status_code=500,
            content={
                "input": request.latex,
                "steps": [],
                "error": f"Internal error: {exc}",
                "version": "v2",
            },
        )
    if (
        isinstance(steps, list)
        and steps
        and all(isinstance(item, Step) for item in steps)
    ):
        steps = apply_precision(steps, request.latex, request.precision)
    try:
        payload = _steps_to_payload(steps)
        error = _extract_error(payload)
        if error is None and not request.verbose:
            filtered = [s for s in payload if s.get("kind") in _LEGACY_KINDS]
            payload = filtered if filtered else payload
        return {
            "input": request.latex,
            "steps": payload,
            "error": error,
            "version": "v2",
        }
    except Exception as exc:  # noqa: BLE001 - serialization must not leak 500 HTML
        return JSONResponse(
            status_code=500,
            content={
                "input": request.latex,
                "steps": [],
                "error": f"Internal error: {exc}",
                "version": "v2",
            },
        )
