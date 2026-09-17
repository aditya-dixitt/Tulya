"""The national code's algebra.

The important test here is `test_damm_table_is_a_valid_quasigroup`, which
derives the check digit's guarantee from the table rather than asserting known
outputs. Writing the table from memory got it wrong on the first attempt - two
rows were transposed, and a suite of "damm_check('572') == 4" assertions would
have happily encoded the broken table as correct. Testing the *property*
caught it in one run.
"""
import random
import unittest

import helpers  # noqa: F401  - sets sys.path
from engine import codegen


class TestDammTable(unittest.TestCase):
    D = codegen._DAMM
    N = 10

    def test_is_a_latin_square(self):
        for i, row in enumerate(self.D):
            self.assertEqual(sorted(row), list(range(self.N)), f"row {i} is not a permutation")
        for j in range(self.N):
            col = [self.D[i][j] for i in range(self.N)]
            self.assertEqual(sorted(col), list(range(self.N)), f"column {j} is not a permutation")

    def test_diagonal_is_zero(self):
        """d(x,x) = 0 is what makes the check digit of a valid string come out 0."""
        for i in range(self.N):
            self.assertEqual(self.D[i][i], 0)

    def test_totally_anti_symmetric(self):
        """The property that buys detection of every adjacent transposition."""
        for x in range(self.N):
            for y in range(self.N):
                if x == y:
                    continue
                for z in range(self.N):
                    self.assertNotEqual(self.D[self.D[z][x]][y], self.D[self.D[z][y]][x],
                                        f"anti-symmetry fails at x={x} y={y} z={z}")


class TestErrorDetection(unittest.TestCase):
    def setUp(self):
        self.rnd = random.Random(20260915)
        self.samples = []
        for _ in range(400):
            body = "".join(self.rnd.choice("0123456789") for _ in range(9))
            self.samples.append(body + str(codegen.damm_check(body)))

    def test_every_single_digit_error_is_detected(self):
        checked = 0
        for full in self.samples:
            for i in range(len(full)):
                for d in "0123456789":
                    if d == full[i]:
                        continue
                    wrong = full[:i] + d + full[i + 1:]
                    self.assertFalse(codegen.damm_valid(wrong))
                    checked += 1
        self.assertGreater(checked, 30_000)

    def test_every_adjacent_transposition_is_detected(self):
        checked = 0
        for full in self.samples:
            for i in range(len(full) - 1):
                if full[i] == full[i + 1]:
                    continue
                wrong = full[:i] + full[i + 1] + full[i] + full[i + 2:]
                self.assertFalse(codegen.damm_valid(wrong))
                checked += 1
        self.assertGreater(checked, 2_000)


class TestCodeFormat(unittest.TestCase):
    def test_mint_is_pure_and_deterministic(self):
        self.assertEqual(codegen.mint_code("10.30.10", 42), codegen.mint_code("10.30.10", 42))

    def test_round_trip(self):
        for cls in ("10.30.10", "20.10.10", "40.20.10"):
            for serial in (1, 7, 999, 99999):
                code = codegen.mint_code(cls, serial)
                p = codegen.parse_code(code)
                self.assertTrue(p["valid"], code)
                self.assertEqual(p["class_code"], cls)
                self.assertEqual(p["serial"], serial)

    def test_distinct_serials_give_distinct_codes(self):
        seen = {codegen.mint_code("10.30.10", s) for s in range(1, 3000)}
        self.assertEqual(len(seen), 2999)

    def test_rejects_malformed_class_code(self):
        for bad in ("10.30", "1.30.10", "ab.cd.ef", "10-30-10"):
            with self.assertRaises(ValueError):
                codegen.mint_code(bad, 1)

    def test_rejects_out_of_range_serial(self):
        with self.assertRaises(ValueError):
            codegen.mint_code("10.30.10", codegen.MAX_SERIAL + 1)

    def test_non_code_returns_none_not_invalid(self):
        """A foreign identifier and a mistyped SAMANVAY code need different
        handling on an ERP import, so they must be distinguishable."""
        self.assertIsNone(codegen.parse_code("MATNR-4711"))
        mistyped = codegen.mint_code("10.30.10", 42)[:-1] + "9"
        parsed = codegen.parse_code(mistyped)
        self.assertIsNotNone(parsed)
        self.assertFalse(parsed["valid"])

    def test_case_and_whitespace_tolerant(self):
        code = codegen.mint_code("10.30.10", 42)
        self.assertTrue(codegen.is_valid_code(f"  {code.lower()}  "))


if __name__ == "__main__":
    unittest.main()
