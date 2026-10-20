# Engine Documentation

## Overview

The **engine** module (`engine.py`) provides a high‑level API for solving mathematical
equations expressed in LaTeX. It parses the LaTeX, performs symbolic simplification,
produces a symbolic solution, and optionally a numerical approximation.

All steps are returned as **LaTeX math fragments**. Before rendering, wrap each fragment
in `$$...$$` (display math) or `\\(...\\)` (inline math).

For a quick‑start guide and CLI usage see [`README.md`](README.md).

---

## Public API

### `generate_solution_steps(latex_input: str) -> List[str]`

#### Description

Parses an equation or system of equations written in LaTeX and returns an ordered
list of LaTeX fragments representing each stage of the solution.

#### Parameters

| Parameter      | Type   | Description                                                    |
|----------------|--------|----------------------------------------------------------------|
| `latex_input`  | `str`  | LaTeX source containing one equation or several equations (system). Equations can be separated by `\\`, `;`, or newlines. |

#### Returns

`List[str]` — ordered list of LaTeX math fragments (each should be wrapped in math
mode delimiters before rendering):

| Index | Step                       | Description                               |
|-------|----------------------------|-------------------------------------------|
| 0     | Original input             | The raw LaTeX string as provided.         |
| 1     | Simplified form            | Each equation simplified via `sympy.simplify`. |
| 2     | Symbolic solution(s)       | Solutions in `variable = expression` format. |
| 3     | Numerical approximations   | Approximate numeric values (`\approx`).   |

If an error occurs, the list contains a single LaTeX block with a readable error
message.

#### Example

```python
from engine import generate_solution_steps

latex = r"x^2 - 5x + 6 = 0"
steps = generate_solution_steps(latex)

for s in steps:
    print(s)
```

Output (each line is a LaTeX math fragment):

```
x^2 - 5x + 6 = 0
x^{2} - 5 x + 6 = 0
x = 2,\; x = 3
x \approx 2.0,\; x \approx 3.0
```

Numeric values use SymPy `evalf` with the engine default precision of 3
significant digits (hence `2.0`, not `2.00000000000000`). See
[Precision defaults](#precision-defaults) for how the CLI/API layers
override this.

To render in a LaTeX document, wrap each fragment:

```latex
\[
x^{2} - 5 x + 6 = 0
\]
```

Or inline: `\(x = 2,\; x = 3\)`.

---

## Internal Workflow (for developers)

1. **Splitting** – `_split_into_equations` breaks the raw LaTeX into separate
   strings using `\\`, `;`, or newline delimiters.
2. **Parsing** – `_latex_to_sympy` converts each fragment into a `sympy.Eq` or
   `sympy.Expr`. It respects top‑level equality while ignoring `=` inside braces.
3. **Simplification** – each equation is simplified with `sympy.simplify`.
4. **Solving**
   * Single equation → `_solve_single` solves for every free symbol.
   * System → `sympy.solve` with a list of `Eq` objects, returning a dict of
     solutions.
   * Underdetermined systems (more unknowns than independent equations)
     raise `ValueError` instead of returning partial solutions (see
     [Underdetermined systems](#underdetermined-systems)).
5. **Formatting** – symbolic and numeric results are turned back into LaTeX
   using `sympy.printing.latex.latex`. Numerics go through
   `_numeric_approx` (`evalf` with the engine default precision of 3 —
   see [Precision defaults](#precision-defaults)).
6. **Error handling** – any exception is caught and converted into a user‑friendly
   LaTeX error block.

---

## Importing the Engine

```python
from engine import generate_solution_steps
```

The function is pure; it does not perform I/O, making it safe to use in
web services, notebooks, or other applications.

---

## Dependencies

- **Python 3.10+**
- **SymPy** – symbolic mathematics library; plus `antlr4-python3-runtime==4.11.*` (see `pyproject.toml` `[project] dependencies`)
- **Dev extras** (`pytest`, `ruff`) and **server extras** (`fastapi`, `uvicorn`, `httpx`) live in `pyproject.toml` `[project.optional-dependencies]`

Install with `uv sync` (add `--extra dev --extra server` as needed); `requirements.txt` is a pip fallback that re-exports the project.

---

## Precision defaults

This documents the current code as a matter of fact. Three layers each have
their own default today:

| Layer | Default | Behaviour |
|-------|---------|-----------|
| `engine._numeric_approx` | `precision: int = 3` | `solution.evalf(3)`; this is what plain `generate_solution_steps` produces. |
| `steps.generate_steps_structured` | `precision: int = 15` | Accepted for forward compatibility but currently ignored (numeric formatting still comes from the engine default). |
| CLI `main.py` / API `api.py` | `--precision 15` / `precision: int = 15` | Precision is applied afterwards via `precision.apply_precision` (recomputing the numeric line with `evalf(precision)`), so `--precision` visibly affects CLI/API output only. Values `< 1` are rejected by the CLI with exit code 2. |

Concretely, `uv run python main.py --precision 5 "x^2 - 2 = 0"` prints
`x \approx -1.4142,\; x \approx 1.4142`, while the default
`--precision 15` prints
`x \approx -1.4142135623731,\; x \approx 1.4142135623731`.

---

## Underdetermined systems

This documents the current code as a matter of fact. When there are more
unknowns than independent equations, the engine raises an error instead of
returning a partial solution: any symbol left without a unique value produces
`ValueError("System is underdetermined: no unique solution for {symbol}.")`,
surfaced as a single LaTeX error block. The CLI prints it to stderr and exits
with code 2:

```bash
uv run python main.py 'x + y = 1'
```

```
Error: \text{Error:} \text{System is underdetermined: no unique solution for y.}
```

(The message above goes to stderr; exit code is 2.) With `--format json` the
same situation returns an error step plus the `error` field (still with
`"version": "v2"`):

```bash
uv run python main.py --format json '\begin{cases} x + y + z = 1 \\ x - y = 0 \end{cases}'
```

```json
{"input": "\\begin{cases} x + y + z = 1 \\\\ x - y = 0 \\end{cases}", "steps": [{"kind": "error", "title": "Error", "latex": "\\text{Error:} \\text{System is underdetermined: no unique solution for z.}"}], "error": "\\text{Error:} \\text{System is underdetermined: no unique solution for z.}", "version": "v2"}
```

This is pinned by
`tests/test_engine.py::test_underdetermined_single_equation_returns_error` and
`::test_underdetermined_system_returns_error`, which require a single error
block with no `None` leaking into the output.

---

## Extending the Engine

If you need additional capabilities (e.g. custom simplification rules,
different numeric precision, or extra output formats):

1. Add a new helper function in `engine.py` with clear docstrings.
2. Update `generate_solution_steps` to call the helper at the appropriate
   point in the workflow.
3. Write unit tests in a separate test suite to verify the new behaviour.

All contributions should adhere to **PEP 8** and the **Google Python Style Guide**.

---

## License

MIT License. See [`LICENSE`](LICENSE) for details.

---

## Structured Steps API

The `steps.py` module wraps `generate_solution_steps` with typed metadata
for API/UI/CLI consumers. Legacy `List[str]` behaviour is unchanged.

```python
from steps import generate_steps_structured, steps_to_json

steps = generate_steps_structured(r"x^2 - 5x + 6 = 0")
for s in steps:
    print(s.kind, "|", s.title, "|", s.latex)

print(steps_to_json(steps))
```

Success returns 4 `Step(kind, title, latex)` items in order
`input → simplified → symbolic → numeric`; failure returns one
`Step(kind="error", ...)`. `steps_to_json` converts steps to plain
dicts (`kind`/`title`/`latex`) for JSON serialization. Note:
`generate_steps_structured` accepts `precision` (default 15) for forward
compatibility, but numeric formatting still comes from the engine default —
see [Precision defaults](#precision-defaults).

