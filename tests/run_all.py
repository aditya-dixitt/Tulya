"""Run the whole suite from the repository root.

`python3 -m unittest` from inside tests/ leaves the working directory there,
and api/app.py resolves its artefacts relative to the root (as it must, since
it is normally started by `make api`). So the runner fixes the working
directory once, here, rather than every module guessing.

    make test             everything
    make test T=erp       just tests/test_erp.py
"""
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).parent.parent
os.chdir(ROOT)
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "api")]


def main():
    pattern = f"test_{sys.argv[1]}.py" if len(sys.argv) > 1 else "test_*.py"
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
