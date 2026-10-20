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
x \approx 2.00000000000000,\; x \approx 3.00000000000000
```

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
5. **Formatting** – symbolic and numeric results are turned back into LaTeX
   using `sympy.printing.latex.latex`.
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
- **SymPy** – symbolic mathematics library (`pip install sympy`)

See [`requirements.txt`](requirements.txt) for pinned versions.

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
dicts (`kind`/`title`/`latex`) for JSON serialization.

