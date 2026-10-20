"""CLI v2 integration tests: formats, precision, exit codes and inputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def test_json_validity_and_shape():
    result = _run_cli(["x^2-5x+6=0", "--format", "json", "--precision", "5"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert set(payload.keys()) >= {"input", "steps", "error"}
    assert payload["input"] == "x^2-5x+6=0"
    assert payload["error"] is None
    assert isinstance(payload["steps"], list)
    assert len(payload["steps"]) >= 4
    for step in payload["steps"]:
        assert set(step.keys()) >= {"kind", "title", "latex"}
    kinds = [s["kind"] for s in payload["steps"]]
    assert "symbolic" in kinds
    assert "numeric" in kinds
    symbolic = next(s["latex"] for s in payload["steps"] if s["kind"] == "symbolic")
    assert "x=2" in _strip_spaces(symbolic)
    assert "x=3" in _strip_spaces(symbolic)


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


def test_exit_code_1_no_input():
    result = _run_cli([], input_text="")
    assert result.returncode == 1
    assert result.stderr.strip() != ""


def test_exit_code_2_no_solution_json():
    result = _run_cli(["x = x + 1", "--format", "json"])
    assert result.returncode == 2
    assert result.stderr.strip() != ""
    payload = json.loads(result.stdout)
    assert payload["error"]
    kinds = [s["kind"] for s in payload["steps"]]
    assert "error" in kinds


def test_exit_code_2_no_solution_text():
    result = _run_cli(["x = x + 1", "--format", "text"])
    assert result.returncode == 2
    assert result.stderr.strip() != ""


def test_only_solution_text():
    result = _run_cli(["x^2-5x+6=0", "--only-solution"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 2
    assert "x=2" in _strip_spaces(lines[0])
    assert "x=3" in _strip_spaces(lines[0])


def test_only_solution_json():
    result = _run_cli(["x^2-5x+6=0", "--format", "json", "--only-solution"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["error"] is None
    kinds = [s["kind"] for s in payload["steps"]]
    assert kinds == ["symbolic", "numeric"]


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


def test_latex_format_wraps_steps():
    result = _run_cli(["x^2-5x+6=0", "--format", "latex"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) >= 4
    for line in lines:
        stripped = line.strip()
        assert stripped.startswith("\\[")
        assert stripped.endswith("\\]")
    joined = _strip_spaces(result.stdout)
    assert "x=2" in joined
