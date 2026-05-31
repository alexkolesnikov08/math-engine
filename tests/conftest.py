import pathlib
import sys

# Ensure the project root (parent of the tests directory) is on sys.path for imports.
project_root = pathlib.Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))
