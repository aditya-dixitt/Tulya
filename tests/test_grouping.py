"""Golden records, and the group-level veto.

`test_truncated_record_cannot_bridge_contradictory_items` is the regression
test for the defect the ERP round trip found: a pairwise veto does not
constrain a transitive closure. Before the fix, 21 of 516 golden records built
from the IOCL material master contained members that directly contradicted
each other. The ablation below reproduces that on three records.
"""
import unittest

import helpers
from api import grouping


class TestUnionFind(unittest.TestCase):
    def test_transitive_merge(self):
        recs, prep = helpers.bolts()
        res = grouping.resolve([(1, 2), (2, 3)], recs, prep)
        self.assertEqual(len(res["groups"]), 1)
        self.assertEqual(res["groups"][0]["size"], 3)

    def test_canonical_is_the_most_completely_described_member(self):
        recs, prep = helpers.bolts()
        g = grouping.resolve([(1, 2), (2, 3)], recs, prep)["groups"][0]
        # record 2 is the abbreviated one; it must not win
        self.assertNotEqual(g["canonical"]["record_id"], 2)

    def test_edges_to_unknown_records_are_dropped_not_raised(self):
        recs, prep = helpers.bolts()
        res = grouping.resolve([(1, 2), (2, 999_999)], recs, prep)
        self.assertEqual(len(res["groups"]), 1)
        self.assertEqual(res["groups"][0]["size"], 2)

    def test_plants_and_cpses_are_reported(self):
        recs, prep = helpers.bolts()
        g = grouping.resolve([(1, 2), (2, 3)], recs, prep)["groups"][0]
        self.assertEqual(g["cpses"], ["BPCL", "IOCL"])
        self.assertIn("Panipat Refinery", g["plants"])


class TestGroupLevelVeto(unittest.TestCase):
    def test_direct_contradiction_is_blocked(self):
        recs, prep = helpers.bolts()
        res = grouping.resolve([(1, 4)], recs, prep)   # M12 vs M16
        self.assertEqual(res["groups"], [])
        self.assertEqual(len(res["blocked"]), 1)
        self.assertIn("thread", res["blocked"][0]["conflicts"])

    def test_truncated_record_cannot_bridge_contradictory_items(self):
        """The bug, and the fix, in one test.

        Cable 12 lost its voltage to truncation, so it conflicts with neither
        the 6.6 kV cable nor the 33 kV one. Approving both pairs is individually
        reasonable. Applying both puts 6.6 kV and 33 kV under one code.
        """
        recs, prep = helpers.truncated_cables()
        edges = [(10, 12), (11, 12)]

        naive = grouping.resolve(edges, recs, prep, enforce=False)
        self.assertEqual(len(naive["groups"]), 1)
        self.assertEqual(naive["groups"][0]["size"], 3)
        self.assertTrue(grouping.audit_consistency(naive["groups"], prep),
                        "the ablation must reproduce the defect, or it proves nothing")

        fixed = grouping.resolve(edges, recs, prep, enforce=True)
        self.assertEqual(grouping.audit_consistency(fixed["groups"], prep), [])
        self.assertEqual(len(fixed["blocked"]), 1)
        self.assertIn("voltage_kv", fixed["blocked"][0]["conflicts"])

    def test_stronger_evidence_wins_when_two_approvals_conflict(self):
        """Which edge survives must be decided by score, not by dict order."""
        recs, prep = helpers.truncated_cables()
        edges = [(10, 12), (11, 12)]
        keep_11 = grouping.resolve(edges, recs, prep, scores={(11, 12): 0.99, (10, 12): 0.80})
        self.assertEqual(keep_11["blocked"][0]["a"], 10)
        keep_10 = grouping.resolve(edges, recs, prep, scores={(11, 12): 0.80, (10, 12): 0.99})
        self.assertEqual(keep_10["blocked"][0]["a"], 11)

    def test_blocked_edge_carries_the_conflicting_values(self):
        recs, prep = helpers.bolts()
        blocked = grouping.resolve([(1, 4)], recs, prep)["blocked"][0]
        self.assertEqual(sorted(blocked["detail"]["thread"]), ["M12", "M16"])
        self.assertIn("thread", blocked["reason"])


class TestSpecConsolidation(unittest.TestCase):
    def test_group_profile_unions_what_members_knew(self):
        recs, prep = helpers.truncated_cables()
        g = grouping.resolve([(10, 12)], recs, prep)["groups"][0]
        self.assertEqual(g["specs"]["voltage_kv"], "6.6")
        self.assertEqual(g["specs"]["csa_sqmm"], "185")

    def test_audit_is_independent_of_the_builder(self):
        """A guarantee checked by the code that produced it is not a guarantee,
        so audit_consistency re-derives conflicts from prep, not from profiles."""
        recs, prep = helpers.bolts()
        groups = grouping.resolve([(1, 2), (2, 3)], recs, prep)["groups"]
        self.assertEqual(grouping.audit_consistency(groups, prep), [])


if __name__ == "__main__":
    unittest.main()
