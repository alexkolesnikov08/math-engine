"""Tests for the linalg module (matrices and linear systems)."""

from __future__ import annotations

import re

import pytest

from linalg import _parse_cell, try_linalg_solve


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_det_and_inverse_2x2_with_verification():
    latex_input = r"\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}"
    steps = try_linalg_solve(latex_input)
    assert steps is not None
    kinds = [s.kind for s in steps]
    assert "verification" in kinds
    assert steps[0].kind == "input"

    det_step = next(s for s in steps if "det" in s.latex.lower())
    det_clean = _clean(det_step.latex)
    # Formula ad-bc with numbers: 1*4 - 2*3 = -2.
    assert "1" in det_clean and "4" in det_clean
    assert "-2" in det_clean

    inv_step = next(s for s in steps if s.kind == "symbolic")
    inv_clean = _clean(inv_step.latex)
    assert "-2" in inv_clean
    assert "1" in inv_clean

    ver_step = next(s for s in steps if s.kind == "verification")
    ver_clean = _clean(ver_step.latex)
    # Product A * A^{-1} equals the 2x2 identity.
    assert "1&0\\\\0&1" in ver_clean or "1&0" in ver_clean


def test_rank_present():
    latex_input = r"\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}"
    steps = try_linalg_solve(latex_input)
    assert steps is not None
    joined = " ".join(s.latex for s in steps)
    assert "rank" in joined.lower()
    assert "2" in joined


def test_singular_matrix_raises():
    latex_input = r"\begin{pmatrix}1 & 2 \\ 2 & 4\end{pmatrix}"
    with pytest.raises(ValueError):
        try_linalg_solve(latex_input)


def test_system_2x2_lusolve_and_verification():
    latex_input = r"x + y = 3; 2x - y = 0"
    steps = try_linalg_solve(latex_input)
    assert steps is not None
    kinds = [s.kind for s in steps]
    assert "verification" in kinds
    symbolic = next(s for s in steps if s.kind == "symbolic")
    clean = _clean(symbolic.latex)
    assert "x=1" in clean
    assert "y=2" in clean


def test_system_3x3_solved_and_verified():
    latex_input = "x + 2y + 3z = 14; 2x - y + z = 3; x + y + z = 6"
    steps = try_linalg_solve(latex_input)
    assert steps is not None
    symbolic = next(s for s in steps if s.kind == "symbolic")
    clean = _clean(symbolic.latex)
    assert "x=1" in clean
    assert "y=2" in clean
    assert "z=3" in clean
    ver = next(s for s in steps if s.kind == "verification")
    assert "OK" in ver.latex


def test_system_cases_environment():
    latex_input = (
        r"\begin{cases} x + y = 3 \\ 2x - y = 0 \end{cases}"
    )
    steps = try_linalg_solve(latex_input)
    assert steps is not None
    symbolic = next(s for s in steps if s.kind == "symbolic")
    assert "1" in symbolic.latex and "2" in symbolic.latex


def test_nonlinear_system_returns_none():
    assert try_linalg_solve(r"x^2 + y = 1; x + y = 0") is None


def test_non_matrix_returns_none():
    assert try_linalg_solve(r"x^2 - 5x + 6 = 0") is None
    assert try_linalg_solve("hello world") is None


def test_parse_cell_rejects_code_execution(tmp_path):
    """Malicious cell must raise ValueError without executing anything."""
    marker = tmp_path / "pwned"
    payload = f"__import__('os').system('touch {marker}')"
    with pytest.raises(ValueError):
        _parse_cell(payload)
    assert not marker.exists()


def test_matrix_with_malicious_cell_raises_without_execution(tmp_path):
    """Matrix embedding a payload must raise ValueError, not execute it."""
    marker = tmp_path / "pwned_matrix"
    payload = f"__import__('os').system('touch {marker}')"
    latex_input = (
        r"\begin{pmatrix}1 & 2 \\ 3 & " + payload + r"\end{pmatrix}"
    )
    with pytest.raises(ValueError):
        try_linalg_solve(latex_input)
    assert not marker.exists()
