from __future__ import annotations

import re

from engine import generate_solution_steps


def _strip_latex_spaces(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_quadratic_equation_steps():
    latex_input = r"x^2 - 5x + 6 = 0"
    steps = generate_solution_steps(latex_input)

    assert len(steps) == 4

    assert _strip_latex_spaces(steps[0]) == _strip_latex_spaces(latex_input)

    assert "x" in steps[1]
    assert "=" in steps[1]

    assert "x=2" in _strip_latex_spaces(steps[2]) or "x = 2" in steps[2]
    assert "x=3" in _strip_latex_spaces(steps[2]) or "x = 3" in steps[2]

    numeric_clean = _strip_latex_spaces(steps[3])
    assert "x\\approx2." in numeric_clean
    assert "x\\approx3." in numeric_clean


def test_linear_system_steps():
    latex_input = r"""
        \begin{cases}
            x + y = 3 \\
            2x - y = 0
        \end{cases}
    """
    steps = generate_solution_steps(latex_input)

    assert len(steps) >= 4

    symbolic = _strip_latex_spaces(steps[2])
    assert "x=1" in symbolic or "x = 1" in steps[2]
    assert "y=2" in symbolic or "y = 2" in steps[2]

    numeric = _strip_latex_spaces(steps[3])
    assert "x\\approx1." in numeric
    assert "y\\approx2." in numeric


def test_malformed_input_error():
    malformed = "this is not a valid latex equation"
    steps = generate_solution_steps(malformed)

    assert isinstance(steps, list)
    assert len(steps) == 1

    error_block = steps[0]
    assert r"\text{Error:}" in error_block or "Error" in error_block


def test_complex_roots():
    latex_input = r"x^2 + 1 = 0"
    steps = generate_solution_steps(latex_input)

    assert len(steps) == 4

    symbolic = _strip_latex_spaces(steps[2])
    assert "i" in symbolic.lower()

    numeric = _strip_latex_spaces(steps[3])
    assert "i" in numeric.lower()


def test_no_solution():
    latex_input = r"x = x + 1"
    steps = generate_solution_steps(latex_input)

    assert isinstance(steps, list)
    assert len(steps) == 1

    error_block = steps[0]
    assert r"\text{Error:}" in error_block or "Error" in error_block


def test_infinite_solutions():
    latex_input = r"x = x"
    steps = generate_solution_steps(latex_input)

    assert isinstance(steps, list)
    assert len(steps) == 1

    error_block = steps[0]
    assert r"\text{Error:}" in error_block or "Error" in error_block


def test_semicolon_separator():
    latex_input = r"x + y = 3; 2x - y = 0"
    steps = generate_solution_steps(latex_input)

    assert len(steps) >= 4

    symbolic = _strip_latex_spaces(steps[2])
    assert "x=1" in symbolic or "x = 1" in steps[2]
    assert "y=2" in symbolic or "y = 2" in steps[2]


def test_newline_separator():
    latex_input = "x + y = 3\n2x - y = 0"
    steps = generate_solution_steps(latex_input)

    assert len(steps) >= 4

    symbolic = _strip_latex_spaces(steps[2])
    assert "x=1" in symbolic or "x = 1" in steps[2]
    assert "y=2" in symbolic or "y = 2" in steps[2]


def test_empty_input():
    latex_input = ""
    steps = generate_solution_steps(latex_input)

    assert isinstance(steps, list)
    assert len(steps) == 1

    error_block = steps[0]
    assert r"\text{Error:}" in error_block or "Error" in error_block


def test_trigonometric():
    latex_input = r"sin(x) = 1"
    steps = generate_solution_steps(latex_input)

    assert len(steps) == 4

    symbolic = _strip_latex_spaces(steps[2]).lower()
    assert "pi" in symbolic


def test_fraction():
    latex_input = r"\frac{x}{2} = 3"
    steps = generate_solution_steps(latex_input)

    assert len(steps) == 4

    symbolic = _strip_latex_spaces(steps[2])
    assert "6" in symbolic


def test_underdetermined_single_equation_returns_error():
    latex_input = r"x + y = 1"
    steps = generate_solution_steps(latex_input)

    assert isinstance(steps, list)
    assert len(steps) == 1

    error_block = steps[0]
    assert r"\text{Error:}" in error_block or "Error" in error_block
    assert "None" not in error_block


def test_underdetermined_system_returns_error():
    latex_input = "x + y + z = 1; x - y = 2"
    steps = generate_solution_steps(latex_input)

    assert isinstance(steps, list)
    assert len(steps) == 1

    error_block = steps[0]
    assert r"\text{Error:}" in error_block or "Error" in error_block
    assert "None" not in error_block


def test_duplicate_solutions_deduplicated():
    latex_input = r"x^2 = 4; y = 1; z = 2"
    steps = generate_solution_steps(latex_input)

    assert len(steps) == 4

    symbolic = _strip_latex_spaces(steps[2])
    assert symbolic.count("y=1") == 1

    numeric = _strip_latex_spaces(steps[3])
    assert numeric.count("y\\approx1.") == 1


def test_pi_is_constant_not_unknown():
    latex_input = r"x - \pi = 0"
    steps = generate_solution_steps(latex_input)

    assert len(steps) == 4

    symbolic = _strip_latex_spaces(steps[2]).lower()
    assert "x=" in symbolic
    assert "pi" in symbolic
    assert "none" not in symbolic
