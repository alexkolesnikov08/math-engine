# Engine Documentation

## Overview

The **engine** module (`engine.py`) provides a high‑level API for solving mathematical
equations expressed in LaTeX. It parses the LaTeX, performs symbolic simplification,
produces a symbolic solution, and optionally a numerical approximation.  
All steps are returned as LaTeX strings so they can be displayed directly in
documents, notebooks, or any LaTeX‑aware viewer.

## Public API

### `generate_solution_steps(latex_input: str) -> List[str]`

#### Description
Creates a chain of LaTeX‑formatted solution steps for a single equation or a system
of equations.

#### Parameters
- **latex_input** (`str`): LaTeX source containing one equation or several
  equations (system). Equations can be separated by `\\`, `;`, or newlines.

#### Returns
- `List[str]`: Ordered list of LaTeX strings:
  1. Original input.
  2. Simplified form of each equation.
  3. Symbolic solution(s) in `variable = expression` format.
  4. Numerical approximations (`≈`).

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
Output (each line is a LaTeX fragment):
```
x^2 - 5x + 6 = 0
x^{2} - 5 x + 6 = 0
x = 2,\; x = 3
x \approx 2.00000000000000,\; x \approx 3.00000000000000
```

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

## Importing the Engine

You can import the engine in any Python module:

```python
from engine import generate_solution_steps
```

The function is pure; it does not perform I/O, making it safe to use in
web‑services, notebooks, or other applications.

## Extending the Engine

If you need additional capabilities (e.g., custom simplification rules,
different numeric precision, or extra output formats), follow these steps:

1. Add a new helper function in `engine.py` with clear docstrings.
2. Update `generate_solution_steps` to call the helper at the appropriate
   point in the workflow.
3. Write unit tests in a separate test suite to verify the new behavior.

All contributions should adhere to **PEP 8** and the **Google Python Style Guide**.

## Dependencies

- **Python 3.10** (or newer)
- **SymPy** – symbolic mathematics library.
  Installation: `pip install sympy`

## License

The code in this repository is released under the MIT License.

---
