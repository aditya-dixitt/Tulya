"""Engine invariants, and a regression test for every bug measurement found.

The bugs in `TestHistoricalBugs` are the ones listed in the build log. Each one
silently corrupted results before it was found; each is now nailed down, so a
future refactor that reintroduces one fails here instead of in a holdout run
three weeks later.
"""
import unittest

import helpers
from engine.attributes import HARD_KEYS, compare, extract
from engine.block import build_multi, category_of, keys_for, size_bucket
from engine.normalize import normalize
from engine.score import MIN_COVERAGE, T_AUTO, T_DISCARD, fuse


def A(text):
    return extract(normalize(text))


class TestHistoricalBugs(unittest.TestCase):
    def test_fractions_survive_normalisation(self):
        """`/` used to be stripped before fractions were resolved, so 1/4", 3/4"
        and 4" all extracted as bore = 4. A large share of false merges."""
        self.assertEqual(A('Seamless Pipe 1/4" SCH40 Carbon Steel')["bore_in"], "0.25")
        self.assertEqual(A('Seamless Pipe 3/4" SCH40 Carbon Steel')["bore_in"], "0.75")
        self.assertEqual(A('Seamless Pipe 4" SCH40 Carbon Steel')["bore_in"], "4")
        self.assertNotEqual(A('pipe 1/4 inch')["bore_in"], A('pipe 4 inch')["bore_in"])

    def test_gr_is_graphite_but_not_in_a106_gr_b(self):
        """'A106 GR B' (a grade) was being expanded to 'graphite'."""
        self.assertIn("graphite", normalize("Spiral Wound Gasket GR"))
        self.assertNotIn("graphite", normalize("Seamless Pipe A106 GR B"))
        self.assertEqual(A("seamless pipe 2 inch A106 GR B")["material_grade"], "A106B")

    def test_m3_per_hour_is_not_an_m3_thread(self):
        """A pump's capacity unit parsed as an M3 bolt thread."""
        a = A("Centrifugal Pump 16 m3/hr head 40 m CI")
        self.assertNotIn("thread", a)
        self.assertEqual(a["cap_m3hr"], "16")
        self.assertEqual(a["head_m"], "40")

    def test_no_abbreviation_is_claimed_twice(self):
        """'flg' was claimed by both 'flange' and 'flanged', making expansion
        order-dependent. The dictionary must stay unambiguous."""
        import collections

        from engine.normalize import _REV
        counts = collections.Counter(abbr for abbr, _canon in _REV)
        dupes = {a: c for a, c in counts.items() if c > 1}
        self.assertEqual(dupes, {}, f"ambiguous abbreviations: {dupes}")

    def test_capacity_and_head_swapped_is_not_the_same_pump(self):
        """The demo's sharpest case: identical words, opposite meaning."""
        a = A("Centrifugal Pump 16 m3/hr head 40 m CI")
        b = A("Centrifugal Pump 40 m3/hr head 16 m CI")
        r = fuse(1.0, 1.0, a, b)
        self.assertTrue(r["vetoed"])
        self.assertEqual(r["score"], 0.0)
        # Fusion without the veto scores this 0.90 - comfortably a merge - because
        # every word matches and the only signal saying otherwise is the pair of
        # numbers that swapped places. That gap between 0.90 and 0.00 is the case.
        self.assertGreaterEqual(r["score_noveto"], 0.85,
                                "text similarity must be near-perfect, or the case proves nothing")
        self.assertGreater(r["score_noveto"], T_AUTO - 0.05)


class TestThreeStateComparison(unittest.TestCase):
    def test_unknown_is_never_a_mismatch(self):
        v, nm, nx, nk = compare(dict(thread="M12"), dict(length_mm="50"))
        self.assertEqual(nx, 0)
        self.assertEqual(nk, 0)
        self.assertEqual(set(v.values()), {"UNKNOWN"})

    def test_known_and_equal_is_a_match(self):
        _v, nm, nx, nk = compare(dict(thread="M12"), dict(thread="M12"))
        self.assertEqual((nm, nx, nk), (1, 0, 1))

    def test_known_and_different_is_a_mismatch(self):
        _v, nm, nx, nk = compare(dict(thread="M12"), dict(thread="M16"))
        self.assertEqual((nm, nx, nk), (0, 1, 1))


class TestVeto(unittest.TestCase):
    def test_one_disagreement_zeroes_the_score(self):
        r = fuse(1.0, 1.0, dict(thread="M12", length_mm="50"), dict(thread="M16", length_mm="50"))
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["decision"], "REJECTED_VETO")
        self.assertEqual(r["conflicts"], ["thread"])

    def test_the_veto_names_what_disagreed(self):
        r = fuse(0.9, 0.9, dict(bore_in="1", pressure_class="300"),
                 dict(bore_in="18", pressure_class="300"))
        self.assertIn("bore_in", r["reason"])

    def test_unknown_specs_do_not_veto(self):
        r = fuse(0.95, 0.95, dict(thread="M12"), dict(length_mm="50"))
        self.assertFalse(r["vetoed"])


class TestCoverageFloor(unittest.TestCase):
    def test_a_high_score_on_thin_evidence_is_capped_at_review(self):
        r = fuse(1.0, 1.0, dict(thread="M12"), dict(thread="M12"))
        self.assertGreaterEqual(r["score"], T_AUTO)
        self.assertEqual(r["decision"], "REVIEW")
        self.assertTrue(r["capped"])
        self.assertLess(r["coverage"], MIN_COVERAGE)

    def test_the_same_score_with_enough_evidence_is_auto_suggested(self):
        r = fuse(1.0, 1.0, dict(thread="M12", length_mm="50"),
                 dict(thread="M12", length_mm="50"))
        self.assertEqual(r["decision"], "AUTO_SUGGEST")
        self.assertFalse(r["capped"])

    def test_bands_are_ordered(self):
        self.assertLess(T_DISCARD, T_AUTO)


class TestBlocking(unittest.TestCase):
    def test_a_record_gets_several_keys_so_one_lost_spec_is_recoverable(self):
        attrs = A("Hexagonal Bolt M12 x 50 mm Stainless Steel 316")
        ks = keys_for("hex_bolt", "nos", attrs)
        self.assertGreater(len(ks), 1)
        self.assertTrue(all(k.startswith("hex_bolt|nos|") for k in ks))

    def test_partner_with_a_missing_spec_still_shares_a_key(self):
        full = A("Hexagonal Bolt M12 x 50 mm Stainless Steel 316")
        lost = A("Hexagonal Bolt x 50 mm Stainless Steel 316")   # thread gone
        self.assertTrue(set(keys_for("hex_bolt", "nos", full)) &
                        set(keys_for("hex_bolt", "nos", lost)))

    def test_unreadable_category_falls_into_the_global_block(self):
        self.assertEqual(category_of(normalize("misc item 4711")), "")
        blocks, stats = build_multi(["", "", "hex_bolt"], ["nos"] * 3,
                                    [{}, {}, dict(thread="M12")])
        self.assertIn("__global__", blocks)
        self.assertEqual(stats["global_records"], 2)


class TestNormalisation(unittest.TestCase):
    def test_is_idempotent(self):
        for text in ("Hexagonal Bolt M12 x 50 mm SS316", 'Seamless Pipe 3/4" SCH40',
                     "XLPE ARM CAB 2 CORE 185 SQMM 6.6 KV"):
            once = normalize(text)
            self.assertEqual(normalize(once), once, f"not idempotent: {text!r}")

    def test_case_and_punctuation_collapse_to_the_same_text(self):
        self.assertEqual(normalize("BOLT HEX M12X50 SS304"), normalize("bolt, hex m12x50 ss304"))

    def test_centimetres_become_millimetres(self):
        self.assertIn("50 mm", normalize("bolt 5 cm"))


class TestPipelineConsistency(unittest.TestCase):
    def test_hard_keys_have_no_duplicates(self):
        self.assertEqual(len(HARD_KEYS), len(set(HARD_KEYS)))

    def test_size_bucket_is_stable_for_the_same_attributes(self):
        a = A("Hexagonal Bolt M12 x 50 mm Stainless Steel 316")
        self.assertEqual(size_bucket(a), size_bucket(dict(reversed(list(a.items())))))

    def test_real_duplicates_score_above_a_real_non_duplicate(self):
        recs, prep = helpers.bolts()
        import json
        at = {i: json.loads(prep.at[i, "attrs"]) for i in prep.index}
        same = fuse(0.95, 0.90, at[1], at[3])       # same bolt, two CPSEs
        different = fuse(0.95, 0.90, at[1], at[4])  # M12 vs M16
        self.assertGreater(same["score"], different["score"])
        self.assertEqual(different["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
