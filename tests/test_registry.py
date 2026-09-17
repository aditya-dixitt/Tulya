"""Issuance, idempotency, supersede chains, and graded linkage."""
import sqlite3
import unittest

import helpers
from engine import registry, taxonomy


class RegistryCase(unittest.TestCase):
    def setUp(self):
        self.conn = registry.init_registry(sqlite3.connect(":memory:"))
        self.recs, self.prep = helpers.bolts()

    def mint(self, ids, actor="steward", canonical=None):
        return registry.mint_for_group(self.conn, ids, self.recs, self.prep,
                                       actor=actor, canonical_id=canonical)


class TestIssuance(RegistryCase):
    def test_issues_a_valid_code(self):
        from engine import codegen
        r = self.mint([1, 2, 3])
        self.assertEqual(r["status"], "issued")
        self.assertTrue(codegen.is_valid_code(r["nmc"]))
        self.assertEqual(r["class_code"], "20.10.10")

    def test_issuance_is_idempotent(self):
        first = self.mint([1, 2, 3])
        again = self.mint([1, 2, 3])
        self.assertEqual(again["status"], "reused")
        self.assertEqual(again["nmc"], first["nmc"])
        self.assertEqual(registry.stats(self.conn)["active_codes"], 1)

    def test_serials_advance_within_a_class(self):
        a = self.mint([1, 2])
        # a genuinely different item in the same class
        r2 = self.mint([4])
        self.assertNotEqual(a["nmc"], r2["nmc"])
        self.assertEqual(registry.stats(self.conn)["active_codes"], 2)

    def test_legacy_lookup_resolves(self):
        r = self.mint([1, 2, 3])
        self.assertEqual(registry.code_for_legacy(self.conn, "BPCL", "B-900"), r["nmc"])
        self.assertIsNone(registry.code_for_legacy(self.conn, "BPCL", "nope"))


class TestSupersede(RegistryCase):
    def test_two_coded_items_consolidate_onto_the_older_code(self):
        a = self.mint([1])
        b = self.mint([2])
        self.assertNotEqual(a["nmc"], b["nmc"])
        merged = self.mint([1, 2, 3])
        self.assertEqual(merged["status"], "consolidated")
        self.assertEqual(merged["nmc"], a["nmc"], "the earlier code must survive")
        self.assertIn(b["nmc"], merged["superseded"])

    def test_a_retired_code_still_resolves_forever(self):
        a, b = self.mint([1]), self.mint([2])
        self.mint([1, 2])
        live, hops = registry.resolve(self.conn, b["nmc"])
        self.assertEqual(live, a["nmc"])
        self.assertEqual(hops, 1)
        self.assertIsNotNone(registry.get(self.conn, b["nmc"]),
                             "a superseded code is never deleted")

    def test_resolve_terminates_on_an_unknown_code(self):
        self.assertEqual(registry.resolve(self.conn, "NMC-99-99-99-00001-0")[0], None)

    def test_unlink_leaves_the_code_intact(self):
        r = self.mint([1, 2, 3])
        registry.unlink_record(self.conn, 2, actor="approver")
        self.assertIsNone(registry.code_for_record(self.conn, 2))
        self.assertEqual(len(registry.members_of(self.conn, r["nmc"])), 2)
        self.assertEqual(registry.get(self.conn, r["nmc"])["status"], "ACTIVE")


class TestRefusalAndGrading(RegistryCase):
    def test_refuses_when_a_defining_spec_is_unreadable(self):
        recs, prep = helpers.frames([
            (20, "IOCL", "Panipat Refinery", "X1", "O-Ring 10 mm id 1.78 mm section", "nos", 1, 5.0),
        ])
        r = registry.mint_for_group(self.conn, [20], recs, prep, actor="steward")
        self.assertEqual(r["status"], "refused")
        self.assertIn("material_grade", r["detail"])
        self.assertEqual(registry.stats(self.conn)["refused_groups"], 1)

    def test_refuses_an_unclassifiable_item(self):
        recs, prep = helpers.frames([
            (21, "IOCL", "Panipat Refinery", "X2", "misc item 4711", "nos", 1, 5.0),
        ])
        r = registry.mint_for_group(self.conn, [21], recs, prep, actor="steward")
        self.assertEqual(r["status"], "refused")
        self.assertEqual(r["reason"], "unclassified")

    def test_a_row_that_cannot_confirm_the_code_is_provisional_not_confirmed(self):
        recs, prep = helpers.truncated_cables()
        r = registry.mint_for_group(self.conn, [10, 12], recs, prep,
                                    actor="steward", canonical_id=10)
        self.assertEqual(r["status"], "issued")
        by_id = {m["record_id"]: m for m in registry.members_of(self.conn, r["nmc"])}
        self.assertEqual(by_id[10]["link_status"], "CONFIRMED")
        self.assertEqual(by_id[12]["link_status"], "PROVISIONAL")
        self.assertIn("voltage_kv", by_id[12]["unknown_keys"])

    def test_provisional_rows_form_a_work_queue(self):
        recs, prep = helpers.truncated_cables()
        registry.mint_for_group(self.conn, [10, 12], recs, prep, canonical_id=10)
        queue = registry.provisional_queue(self.conn)
        self.assertEqual([q["record_id"] for q in queue], [12])
        self.assertEqual(queue[0]["class_name"], "Cable, XLPE Armoured")

    def test_a_human_can_confirm_a_provisional_row(self):
        recs, prep = helpers.truncated_cables()
        r = registry.mint_for_group(self.conn, [10, 12], recs, prep, canonical_id=10)
        registry.confirm_member(self.conn, 12, actor="approver", note="checked the drawing")
        self.assertEqual(registry.provisional_queue(self.conn), [])
        self.assertEqual(registry.stats(self.conn)["confirmed_links"], 2)
        self.assertIn("confirmed", [e["event"] for e in registry.events(self.conn)])


class TestSignatureGrading(unittest.TestCase):
    CLS = "40.20.10"
    SIG = "cores=2|csa_sqmm=185|voltage_kv=6.6"

    def grade(self, attrs):
        return taxonomy.signature_match(self.CLS, attrs, self.SIG)["status"]

    def test_all_keys_present_and_equal_is_confirmed(self):
        self.assertEqual(self.grade(dict(cores="2", csa_sqmm="185", voltage_kv="6.6")),
                         "confirmed")

    def test_a_disagreement_is_a_conflict_however_much_else_matches(self):
        self.assertEqual(self.grade(dict(cores="2", csa_sqmm="185", voltage_kv="33")),
                         "conflict")

    def test_two_corroborating_keys_and_one_unknown_is_provisional(self):
        self.assertEqual(self.grade(dict(cores="2", csa_sqmm="185")), "provisional")

    def test_one_corroborating_key_is_not_enough(self):
        self.assertEqual(self.grade(dict(cores="2")), "unsupported")

    def test_nothing_readable_is_unsupported(self):
        self.assertEqual(self.grade({}), "unsupported")


class TestTaxonomy(unittest.TestCase):
    def test_every_class_has_defining_keys(self):
        for info in taxonomy.all_classes():
            self.assertTrue(info["defining_keys"],
                            f"{info['class_code']} has no defining specifications")

    def test_defining_keys_are_real_hard_keys(self):
        from engine.attributes import HARD_KEYS
        for info in taxonomy.all_classes():
            for k in info["defining_keys"]:
                self.assertIn(k, HARD_KEYS, f"{info['class_code']} defines on unknown key {k}")

    def test_every_engine_category_maps_to_a_class(self):
        from engine.block import CATEGORY_KEYS
        for _phrase, cat in CATEGORY_KEYS:
            self.assertNotEqual(taxonomy.class_of_category(cat), taxonomy.UNCLASSIFIED,
                                f"category {cat} has no class")

    def test_signature_is_order_stable_and_marks_holes(self):
        a = taxonomy.spec_signature("20.10.10", dict(material_grade="SS316", thread="M12",
                                                     length_mm="50"))
        b = taxonomy.spec_signature("20.10.10", dict(thread="M12", length_mm="50",
                                                     material_grade="SS316"))
        self.assertEqual(a, b)
        holed = taxonomy.spec_signature("20.10.10", dict(thread="M12", length_mm="50"))
        self.assertIn("=?", holed)
        self.assertNotEqual(a, holed, "an incomplete signature must not collide with a full one")

    def test_defining_keys_are_actually_readable_from_real_descriptions(self):
        """A class whose defining keys never appear in the data refuses a code to
        every item in it - silently, and forever.

        That is not hypothetical: the first version of this taxonomy demanded a
        voltage on induction motors (appears on 0 of 523), a seal type on roller
        bearings (0 of 10) and a pressure class on compressed-fibre gaskets
        (0 of 73). All three refused 100% of their class. This audit re-derives
        completeness from the real prepared split, so the next wrong key fails
        here instead of in a demo.
        """
        import json
        import pandas as pd
        from engine.block import category_of
        path = helpers.ROOT / "data/out/prepared_test.csv"
        if not path.exists():
            self.skipTest("prepared_test.csv not built; run `make demo` first")
        prep = pd.read_csv(path)
        seen, complete = {}, {}
        for norm, raw in zip(prep["norm"], prep["attrs"]):
            cc = taxonomy.class_of_category(category_of(str(norm)))
            if cc == taxonomy.UNCLASSIFIED:
                continue
            attrs = json.loads(raw) if isinstance(raw, str) else {}
            seen[cc] = seen.get(cc, 0) + 1
            complete[cc] = complete.get(cc, 0) + taxonomy.signature_is_complete(cc, attrs)
        self.assertTrue(seen, "no classified records found")
        for cc, n in seen.items():
            if n < 20:                      # too few to judge a rate on
                continue
            rate = complete.get(cc, 0) / n
            self.assertGreater(
                rate, 0.35,
                f"{taxonomy.describe(cc)['class_name']} ({cc}) can complete its signature on "
                f"only {rate:.0%} of {n} real records - a defining key is probably wrong: "
                f"{taxonomy.DEFINING_KEYS[cc]}")

    def test_unspsc_crosswalk_is_empty_rather_than_guessed(self):
        """Deliberate: the UNSPSC code list is licensed and was not available to
        this build. Plausible-looking invented codes in a government-facing
        artefact are worse than an honest gap."""
        self.assertTrue(all(c["unspsc"] is None for c in taxonomy.all_classes()))


if __name__ == "__main__":
    unittest.main()
