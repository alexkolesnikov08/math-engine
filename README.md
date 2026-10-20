# math-engine

A compact Python utility that parses mathematical equations written in LaTeX, solves them both symbolically and numerically, and returns a step‑by‑step solution as LaTeX fragments.

## Features

- Supports single equations and systems of equations.
- Symbolic simplification, solving, and numeric approximation.
- Full LaTeX output (original input, simplified form, symbolic solution, numeric approximation).
- Command‑line interface (`main.py`) and importable engine (`engine.py`).
- FastAPI service (`api.py`) with a KaTeX preview page (`static/index.html`).
- Powered by **SymPy** – no external mathematics engines required.

## Installation

Requires Python 3.10+. The primary workflow uses [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/alexkolesnikov08/math-engine
cd math-engine
uv sync
```

Run everything through `uv run`, e.g. `uv run python main.py "x^2 - 5x + 6 = 0"`.

Fallback without `uv` (plain `pip`; `requirements.txt` re-exports the project itself, whose dependencies live in `pyproject.toml`):

```bash
pip install -r requirements.txt
```

> If using a Homebrew‑installed Python, replace `pip` with the full path (e.g. `/opt/homebrew/bin/python3.11 -m pip install -r requirements.txt`).

## Usage

### CLI

```bash
# Pass the equation as an argument
uv run python main.py "x^2 - 5x + 6 = 0"

# Or pipe via stdin
echo "x^2 - 5x + 6 = 0" | uv run python main.py

# Or read it from a file
uv run python main.py --file equation.tex
```

Output (each line is a LaTeX fragment):

```
x^2 - 5x + 6 = 0
x^{2} - 5 x + 6 = 0
x = 2,\; x = 3
x \approx 2.0,\; x \approx 3.0
```

Note: `main.py` has no executable bit (`ls -l main.py` shows `-rw-r--r--`), so invoke it explicitly as `python main.py` (or `python -m main`) rather than `./main.py`.

`uv run python main.py --help` reports (verbatim):

```
usage: main.py [-h] [--format {text,json,latex}] [--precision PRECISION]
               [--full-steps] [--only-solution] [--file PATH]
               [equation]

Solve LaTeX equations and output step-by-step LaTeX solution.

positional arguments:
  equation              LaTeX string of the equation or system to solve. If
                        omitted, the script reads from standard input or
                        --file.

options:
  -h, --help            show this help message and exit
  --format {text,json,latex}
                        Output format: text (one LaTeX step per line), json,
                        or latex (each step in \[...\]). Default: text.
  --precision PRECISION
                        Number of significant digits for numerical
                        approximations. Must be >= 1. Default: 15.
  --full-steps          Show full derivation steps. Without it,
                        json/latex/text outputs are filtered to the legacy 4
                        steps (input/simplified/symbolic/numeric).
  --only-solution       Output only symbolic and numeric solution steps.
  --file PATH           Read the equation from a file instead of the argument
                        or stdin.
```

| Flag | Effect |
|------|--------|
| `--format {text,json,latex}` | Output format: `text` (one LaTeX step per line), `json` (structured steps with `kind`/`title`/`latex`, plus `version`), or `latex` (each step wrapped in `\[...\]`). Default: `text`. |
| `--precision N` | Significant digits for numeric approximations. Must be `>= 1`. Default: `15`. |
| `--full-steps` | Show full derivation steps. Without it, all formats are filtered to the legacy 4 steps (`input`/`simplified`/`symbolic`/`numeric`). |
| `--only-solution` | Output only the symbolic and numeric solution steps. |
| `--file PATH` | Read the equation from a file instead of the argument or stdin. |

#### Output modes: legacy-4 default vs full honest steps

By default every format keeps the legacy 4-step view (`input → simplified → symbolic → numeric`), so existing scripts keep working. The `json` format additionally carries `"version": "v2"`:

```bash
uv run python main.py --format json "x^2 - 5x + 6 = 0"
```

```json
{"input": "x^2 - 5x + 6 = 0", "steps": [{"kind": "input", "title": "Input", "latex": "x^2 - 5x + 6 = 0"}, {"kind": "simplified", "title": "Simplified form", "latex": "x^{2} - 5 x + 6 = 0"}, {"kind": "symbolic", "title": "Symbolic solution", "latex": "x = 2,\\; x = 3"}, {"kind": "numeric", "title": "Numerical approximation", "latex": "x \\approx 2.0,\\; x \\approx 3.0"}], "error": null, "version": "v2"}
```

`--full-steps` reveals the honest derivation (extra `derivation` and `verification` steps where the solvers provide them):

```bash
uv run python main.py --full-steps "x^2 - 5x + 6 = 0"
```

```
x^2 - 5x + 6 = 0
x^{2} - 5 x + 6 = 0
a = 1,\; b = -5,\; c = 6
D = - 4 a c + b^{2}
D = \left(-4\right) 1 \cdot 6 + \left(-5\right)^{2} = 1
x = \frac{\sqrt{D} - b}{2 a},\; x = \frac{- \sqrt{D} - b}{2 a}
x = 2,\; x = 3
x \approx 2.0,\; x \approx 3.0
0 = 0
0 = 0
```

`--format json --full-steps` returns the same 10 steps as structured `kind`/`title`/`latex` objects (still with `"version": "v2"`); `--format latex --full-steps` wraps each in `\[...\]`.

`--only-solution` composes with every format/mode and keeps just the symbolic and numeric lines:

```bash
uv run python main.py --only-solution "x^2 - 5x + 6 = 0"
uv run python main.py --format json --only-solution "x^2 - 5x + 6 = 0"
```

```
x = 2,\; x = 3
x \approx 2.0,\; x \approx 3.0
```

```json
{"input": "x^2 - 5x + 6 = 0", "steps": [{"kind": "symbolic", "title": "Symbolic solution", "latex": "x = 2,\\; x = 3"}, {"kind": "numeric", "title": "Numerical approximation", "latex": "x \\approx 2.0,\\; x \\approx 3.0"}], "error": null, "version": "v2"}
```

#### Precision

`--precision` controls significant digits of the numeric approximation:

```bash
uv run python main.py --precision 5 "x^2 - 2 = 0"
```

```
x^2 - 2 = 0
x^{2} - 2 = 0
x = - \sqrt{2},\; x = \sqrt{2}
x \approx -1.4142,\; x \approx 1.4142
```

With the default `--precision 15` the last line is `x \approx -1.4142135623731,\; x \approx 1.4142135623731`. Values below 1 are rejected by argparse (`--precision 0` exits with code 2 and `error: argument --precision: --precision must be >= 1`).

Precision is currently owned by three layers (as a matter of fact, not design intent):

- `engine._numeric_approx` defaults to 3 significant digits (`evalf(3)`); this is what plain `generate_solution_steps` produces (e.g. `2.0`).
- `steps.generate_steps_structured(..., precision=15)` accepts a `precision` argument but ignores it — numeric formatting still comes from the engine default.
- The CLI (`main.py`, default `--precision 15`) applies precision afterwards via `precision.apply_precision`, which recomputes the numeric line with `evalf(precision)` — so `--precision` visibly affects CLI/API output only.

### Library

```python
from engine import generate_solution_steps

latex_eq = r"\begin{cases} x + y = 3 \\ 2x - y = 0 \end{cases}"
steps = generate_solution_steps(latex_eq)

for step in steps:
    print(step)
```

Output (each line is a LaTeX fragment):

```
\begin{cases} x + y = 3 \\ 2x - y = 0 \end{cases}
x + y = 3\\ 2 x - y = 0
x = 1,\; y = 2
x \approx 1.0,\; y \approx 2.0
```

Each returned string is a LaTeX math fragment. Wrap it in `$$...$$` (display) or `\\(...\\)` (inline) before rendering. See [`documentation.md`](documentation.md) for the full API reference.

### API server

```bash
uv run uvicorn api:app --reload
```

- `GET /` serves the KaTeX preview page (`static/index.html`).
- `POST /solve` with JSON body `{"latex": "...", "precision": 15}` returns the structured steps (`input`/`simplified`/`derivation`…/`symbolic`/`numeric`/`verification`) plus an `error` field (see [`documentation.md`](documentation.md)).

### Shebang

`main.py` uses the portable shebang `#!/usr/bin/env python3`. If your system has multiple Python versions, use `uv run python main.py` or override the interpreter explicitly.

## LaTeX input notes

Bare function names (without a backslash) are normalized to their LaTeX form
before solving, so `sin(x)` works exactly like `\sin(x)`:

```bash
uv run python main.py 'sin(x) = 0'
```

```
sin(x) = 0
\sin{\left(x \right)} = 0
x = 0,\; x = \pi
x \approx 0,\; x \approx 3.14159265358979
```

This is pinned by `tests/test_engine.py::test_trigonometric` (`sin(x) = 1` must
produce 4 steps whose symbolic line mentions pi).

## Dependencies

| Group | Packages | Declared in |
|-------|----------|-------------|
| base | `sympy`, `antlr4-python3-runtime==4.11.*` | `pyproject.toml` `[project] dependencies` |
| dev | `pytest`, `ruff` | `pyproject.toml` `[project.optional-dependencies] dev` |
| server | `fastapi`, `uvicorn`, `httpx` | `pyproject.toml` `[project.optional-dependencies] server` |

Install a group with `uv sync --extra dev --extra server` (CI installs both, locked, via `uv sync --locked --extra dev --extra server`).

## Project Structure

```
math-engine/
├── engine.py         # Core solving logic (importable)
├── steps.py           # Structured steps API (Step dataclass)
├── parsing.py         # Robust LaTeX parsing
├── step_builders.py   # Honest derivation steps
├── extensions.py      # Expressions, inequalities, calculus
├── linalg.py          # Matrices and linear systems
├── api.py             # FastAPI service (serves static/ preview at GET /)
├── main.py            # CLI entry point
├── precision.py       # CLI/API numeric precision handling
├── static/            # KaTeX preview page (index.html)
├── tests/             # pytest suite (unit + integration markers)
├── pyproject.toml     # Project metadata and dependencies
├── uv.lock            # Locked dependency versions
├── .github/workflows/ # CI (lint + unit + integration tests)
├── README.md          # This file
├── documentation.md   # Full API reference
├── requirements.txt  # pip fallback (re-exports the project)
└── LICENSE           # MIT License
```

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-feature`).
3. Ensure code follows **Google Python Style Guide** and passes linting.
4. Submit a pull request with a clear description of the changes.

## License

MIT License. See [LICENSE](LICENSE) for details.
