from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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
        timeout=5,
    )


def _strip_spaces(s: str) -> str:
    return "".join(s.split())


# --- Unit tests for argument parsing ---


def test_parse_arguments_with_equation():
    with patch.object(sys, "argv", ["main.py", "x + 1 = 2"]):
        from main import _parse_arguments

        args = _parse_arguments()
        assert args.equation == "x + 1 = 2"


def test_parse_arguments_without_equation():
    with patch.object(sys, "argv", ["main.py"]):
        from main import _parse_arguments

        args = _parse_arguments()
        assert args.equation is None


# --- Integration tests (subprocess) ---


@pytest.mark.integration
def test_cli_argument_passed():
    result = _run_cli(["x^2 - 5x + 6 = 0"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [_strip_spaces(line) for line in result.stdout.strip().splitlines()]
    assert len(lines) == 4
    assert lines[0] == _strip_spaces("x^2 - 5x + 6 = 0")
    assert "x=2" in lines[2] and "x=3" in lines[2]


@pytest.mark.integration
def test_cli_stdin():
    result = _run_cli([], input_text="x^2 - 5x + 6 = 0")
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    lines = [_strip_spaces(line) for line in result.stdout.strip().splitlines()]
    assert len(lines) == 4
    assert lines[0] == _strip_spaces("x^2 - 5x + 6 = 0")
    assert "x=2" in lines[2] and "x=3" in lines[2]
