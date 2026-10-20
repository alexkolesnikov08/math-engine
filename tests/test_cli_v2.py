"""CLI v2 integration tests: formats, precision, exit codes and inputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from precision import apply_precision, recompute_numeric_latex
from steps import Step

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(
    args: list[str], input_text: str | None = None
) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(PROJECT_ROOT / "main.py")] + args
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=10,
    )


def _strip_spaces(s: str) -> str:
    return "".join(s.split())


@pytest.mark.integration
def test_json_validity_and_shape():
    result = _run_cli(["x^2-5x+6=0", "--format", "json", "--precision", "5"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert set(payload.keys()) >= {"input", "steps", "error", "version"}
    assert payload["version"] == "v2"
    assert payload["input"] == "x^2-5x+6=0"
    assert payload["error"] is None
    assert isinstance(payload["steps"], list)
    # Default json is the legacy contract: exactly 4 steps.
    assert len(payload["steps"]) == 4
    assert [s["kind"] for s in payload["steps"]] == [
        "input",
        "simplified",
        "symbolic",
        "numeric",
    ]
    for step in payload["steps"]:
        assert set(step.keys()) >= {"kind", "title", "latex"}
    symbolic = next(s["latex"] for s in payload["steps"] if s["kind"] == "symbolic")
    assert "x=2" in _strip_spaces(symbolic)
    assert "x=3" in _strip_spaces(symbolic)


@pytest.mark.integration
def test_full_steps_json_returns_derivations():
    result = _run_cli(["x^2-5x+6=0", "--format", "json", "--full-steps"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["version"] == "v2"
    assert payload["error"] is None
    assert len(payload["steps"]) == 10
    kinds = [s["kind"] for s in payload["steps"]]
    assert "derivation" in kinds
    assert "verification" in kinds


@pytest.mark.integration
def test_full_steps_text_returns_ten_lines():
    result = _run_cli(["x^2-5x+6=0", "--full-steps"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 10


@pytest.mark.integration
def test_precision_affects_numeric():
    low = _run_cli(["x^2-2=0", "--format", "json", "--precision", "3"])
    high = _run_cli(["x^2-2=0", "--format", "json", "--precision", "15"])
    assert low.returncode == 0, f"CLI failed: {low.stderr}"
    assert high.returncode == 0, f"CLI failed: {high.stderr}"
    low_numeric = next(
        s["latex"] for s in json.loads(low.stdout)["steps"] if s["kind"] == "numeric"
    )
    high_numeric = next(
        s["latex"] for s in json.loads(high.stdout)["steps"] if s["kind"] == "numeric"
    )
    assert low_numeric != high_numeric
    assert "1.41" in low_numeric
    assert "1.4142" in high_numeric


@pytest.mark.integration
def test_precision_zero_exits_2():
    result = _run_cli(["x^2-5x+6=0", "--precision", "0"])
    assert result.returncode == 2
    assert result.stderr.strip() != ""


@pytest.mark.integration
def test_pi_numeric_stays_accurate():
    result = _run_cli(["x - \\pi = 0", "--format", "json"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["error"] is None
    numeric = next(s["latex"] for s in payload["steps"] if s["kind"] == "numeric")
    assert "3.14159" in numeric


@pytest.mark.integration
def test_exit_code_1_no_input():
    result = _run_cli([], input_text="")
    assert result.returncode == 1
    assert result.stderr.strip() != ""


@pytest.mark.integration
def test_exit_code_2_no_solution_json():
    result = _run_cli(["x = x + 1", "--format", "json"])
    assert result.returncode == 2
    assert result.stderr.strip() != ""
    payload = json.loads(result.stdout)
    assert payload["error"]
    assert payload["version"] == "v2"
    kinds = [s["kind"] for s in payload["steps"]]
    assert "error" in kinds


@pytest.mark.integration
def test_exit_code_2_no_solution_text():
    result = _run_cli(["x = x + 1", "--format", "text"])
    assert result.returncode == 2
    assert result.stderr.strip() != ""


@pytest.mark.integration
def test_only_solution_text():
    result = _run_cli(["x^2-5x+6=0", "--only-solution"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 2
    assert "x=2" in _strip_spaces(lines[0])
    assert "x=3" in _strip_spaces(lines[0])


@pytest.mark.integration
def test_only_solution_json():
    result = _run_cli(["x^2-5x+6=0", "--format", "json", "--only-solution"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["error"] is None
    kinds = [s["kind"] for s in payload["steps"]]
    assert kinds == ["symbolic", "numeric"]


@pytest.mark.integration
def test_file_input(tmp_path: Path):
    target = tmp_path / "equation.tex"
    target.write_text("x^2-5x+6=0", encoding="utf-8")
    result = _run_cli(["--file", str(target), "--format", "json", "--precision", "5"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["input"] == "x^2-5x+6=0"
    assert payload["error"] is None
    symbolic = next(s["latex"] for s in payload["steps"] if s["kind"] == "symbolic")
    assert "x=2" in _strip_spaces(symbolic)


@pytest.mark.integration
def test_latex_format_wraps_steps():
    result = _run_cli(["x^2-5x+6=0", "--format", "latex"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    # Default latex mirrors the legacy 4-step contract.
    assert len(lines) == 4
    for line in lines:
        stripped = line.strip()
        assert stripped.startswith("\\[")
        assert stripped.endswith("\\]")
    joined = _strip_spaces(result.stdout)
    assert "x=2" in joined


@pytest.mark.integration
def test_latex_full_steps_wraps_all():
    result = _run_cli(["x^2-5x+6=0", "--format", "latex", "--full-steps"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 10
    for line in lines:
        stripped = line.strip()
        assert stripped.startswith("\\[")
        assert stripped.endswith("\\]")


# --- Pure unit tests for precision.py (no subprocess, no marker) ---


def _legacy_steps(symbolic: str, numeric: str) -> list[Step]:
    return [
        Step(kind="input", title="Input", latex="x - \\pi = 0"),
        Step(kind="simplified", title="Simplified form", latex="x - \\pi = 0"),
        Step(kind="symbolic", title="Symbolic solution", latex=symbolic),
        Step(kind="numeric", title="Numerical approximation", latex=numeric),
    ]


def test_precision_fallback_recomputes_pi_despite_letter_i():
    # "" is unparseable so the engine recompute is skipped and the
    # symbolic-RHS fallback runs: \\pi must NOT be skipped the way the old
    # substring guard ("i" in latex) did. Parsed in isolation it stays the
    # symbol \\pi, but the fragment is re-evaluated, not left untouched.
    steps = _legacy_steps(r"x = \pi", r"x \approx 3.14159265358979")
    updated = apply_precision(steps, "", 3)
    numeric = next(s.latex for s in updated if s.kind == "numeric")
    assert numeric == r"x \approx \pi"


def test_precision_fallback_leaves_imaginary_untouched():
    steps = _legacy_steps(r"x = \sqrt{-1}", r"x \approx \sqrt{-1}")
    updated = apply_precision(steps, "", 3)
    numeric = next(s.latex for s in updated if s.kind == "numeric")
    assert numeric == r"x \approx \sqrt{-1}"


def test_precision_without_numeric_steps_returns_unchanged():
    # Quiet branch: nothing to recompute (error output) stays as-is
    # instead of fabricating digits.
    steps = [Step(kind="error", title="Error", latex=r"\text{Error: bad}")]
    assert apply_precision(steps, "x = x + 1", 3) == steps


def test_recompute_rejects_mismatched_symbols():
    # The engine solves for x, but the symbolic step speaks about y:
    # its numbers must not overwrite the builder's numeric line.
    steps = _legacy_steps("y = 1", r"y \approx 1")
    assert recompute_numeric_latex(steps, "x = 1", 5) is None
