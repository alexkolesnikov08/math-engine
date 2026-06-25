# Math Equation Solver

A compact Python utility that parses mathematical equations written in LaTeX, solves them both symbolically and numerically, and returns a step‑by‑step solution as LaTeX fragments.

## Features

- Supports single equations and systems of equations.
- Symbolic simplification, solving, and numeric approximation.
- Full LaTeX output (original input, simplified form, symbolic solution, numeric approximation).
- Command‑line interface (`main.py`) and importable engine (`engine.py`).
- Powered by **SymPy** – no external mathematics engines required.

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/alexkolesnikov08/Math
   cd Math
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

   > Requires Python 3.10+. If using a Homebrew‑installed Python, replace `pip` with the full path (e.g. `/opt/homebrew/bin/python3.11 -m pip install -r requirements.txt`).

3. **Make the CLI executable (optional)**:

   ```bash
   chmod +x main.py
   ./main.py "x^2 - 5x + 6 = 0"
   ```

## Usage

### CLI

```bash
# Pass the equation as an argument
python -m main "x^2 - 5x + 6 = 0"

# Or pipe via stdin
echo "x^2 - 5x + 6 = 0" | python -m main
```

Output (each line is a LaTeX fragment):

```
x^2 - 5x + 6 = 0
x^{2} - 5 x + 6 = 0
x = 2,\; x = 3
x \approx 2.00000000000000,\; x \approx 3.00000000000000
```

### Library

```python
from engine import generate_solution_steps

latex_eq = r"\begin{cases} x + y = 3 \\ 2x - y = 0 \end{cases}"
steps = generate_solution_steps(latex_eq)

for step in steps:
    print(step)
```

Each returned string is a LaTeX math fragment. Wrap it in `$$...$$` (display) or `\\(...\\)` (inline) before rendering. See [`documentation.md`](documentation.md) for the full API reference.

### Shebang

`main.py` uses the portable shebang `#!/usr/bin/env python3`. If your system has multiple Python versions, use `python main.py` or override the interpreter explicitly.

## Project Structure

```
Math/
├── engine.py         # Core solving logic (importable)
├── main.py           # CLI entry point
├── README.md         # This file
├── documentation.md  # Full API reference
├── requirements.txt  # Python dependencies
└── LICENSE           # MIT License
```

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-feature`).
3. Ensure code follows **Google Python Style Guide** and passes linting.
4. Submit a pull request with a clear description of the changes.

## License

MIT License. See [LICENSE](LICENSE) for details.
