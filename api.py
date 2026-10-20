"""FastAPI service exposing the math-engine solver.

Endpoints:
    GET /health -- liveness probe.
    GET / -- static KaTeX preview page.
    POST /solve -- solve a LaTeX equation, returning structured steps.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from steps import generate_steps_structured, steps_to_json

app = FastAPI(title="math-engine API")

_STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"

# Candidate optional modules that may provide richer step builders.
# They are owned by parallel workstreams; absence is normal.
_OPTIONAL_BUILDER_MODULES: tuple[str, ...] = (
    "step_builders",
    "extensions",
    "linalg",
)

# Candidate builder function names probed inside optional modules.
_OPTIONAL_BUILDER_ATTRS: tuple[str, ...] = (
    "build_derivation_steps",
    "try_extended_solve",
    "try_linalg_solve",
    "generate_steps_structured",
)


class SolveRequest(BaseModel):
    """Request body for POST /solve."""

    latex: str = Field(description="LaTeX equation or system to solve.")
    precision: int = Field(default=15, description="Numeric precision.")


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


def _call_with_precision(fn: Any, latex: str, precision: int) -> Any:
    """Call a builder preferring (latex, precision), falling back to (latex)."""
    try:
        return fn(latex, precision)
    except TypeError:
        return fn(latex)


def _build_steps(latex: str, precision: int) -> Any:
    """Dispatch to the richest available step builder.

    Tries optional ``step_builders``/``extensions``/``linalg`` modules
    first (same dispatch order as the CLI), falling back to
    :func:`steps.generate_steps_structured` when they are absent.

    Never creates those modules; missing imports are silently skipped.
    """
    for module_name in _OPTIONAL_BUILDER_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        except Exception:
            continue
        for attr in _OPTIONAL_BUILDER_ATTRS:
            fn = getattr(module, attr, None)
            if not callable(fn):
                continue
            try:
                result = _call_with_precision(fn, latex, precision)
            except Exception:
                # Optional builder failed; try next candidate.
                continue
            if result is not None:
                return result
            break
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
    """Return the error message when payload is a single error step."""
    if len(payload) == 1 and payload[0].get("kind") == "error":
        return payload[0].get("latex") or "Unknown error."
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
            },
        )
    try:
        payload = _steps_to_payload(steps)
        error = _extract_error(payload)
        return {"input": request.latex, "steps": payload, "error": error}
    except Exception as exc:  # noqa: BLE001 - serialization must not leak 500 HTML
        return JSONResponse(
            status_code=500,
            content={
                "input": request.latex,
                "steps": [],
                "error": f"Internal error: {exc}",
            },
        )
