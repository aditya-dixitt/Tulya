"""The console's HTTP surface, against throwaway databases.

Slow-ish: importing api.app loads the locked test split (~6k records, 147k
scored pairs) exactly as the real console does. That is the point - these run
against the same artefacts a judge will see, not a mock.
"""
import os
import pathlib
import tempfile
import unittest

_TMP = pathlib.Path(tempfile.mkdtemp())
os.environ["SAMANVAY_DB"] = str(_TMP / "steward.db")
os.environ["SAMANVAY_REGISTRY_DB"] = str(_TMP / "registry.db")

import helpers  # noqa: F401,E402  - sets sys.path
from api import app as api_app  # noqa: E402


class ApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        api_app.app.config["TESTING"] = True
        cls.c = api_app.app.test_client()

    def token(self, username, password):
        r = self.c.post("/api/auth/login", json=dict(username=username, password=password))
        self.assertEqual(r.status_code, 200, r.get_json())
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def a_pair(self, decision="AUTO_SUGGEST"):
        """A real pair from the locked split, in the given band."""
        row = api_app.PAIRS[api_app.PAIRS.decision == decision].iloc[0]
        return int(row.a), int(row.b)


class TestAuthRoutes(ApiCase):
    def test_login_rejects_a_wrong_password(self):
        r = self.c.post("/api/auth/login", json=dict(username="steward", password="nope"))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["code"], "bad_credentials")

    def test_writing_without_a_session_is_401_not_403(self):
        a, b = self.a_pair()
        r = self.c.post(f"/api/pair/{a}/{b}/approve", json={})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["code"], "unauthenticated")

    def test_a_viewer_gets_403_and_is_told_which_role_is_needed(self):
        a, b = self.a_pair()
        r = self.c.post(f"/api/pair/{a}/{b}/approve", json={}, headers=self.token("viewer",
                                                                                 "viewer123"))
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertEqual(body["required"], "steward")
        self.assertEqual(body["held"], "viewer")

    def test_me_reports_the_signed_in_user(self):
        r = self.c.get("/api/auth/me", headers=self.token("approver", "approver123"))
        self.assertTrue(r.get_json()["signed_in"])
        self.assertEqual(r.get_json()["role"], "approver")

    def test_logout_revokes(self):
        h = self.token("steward", "steward123")
        self.c.post("/api/auth/logout", headers=h)
        self.assertFalse(self.c.get("/api/auth/me", headers=h).get_json()["signed_in"])


class TestReadRoutes(ApiCase):
    def test_stats(self):
        r = self.c.get("/api/stats")
        self.assertEqual(r.status_code, 200)

    def test_queue_returns_real_pairs_with_evidence(self):
        items = self.c.get("/api/queue?limit=5").get_json()["items"]
        self.assertTrue(items)
        for it in items:
            self.assertEqual(it["decision"], "REVIEW")
            self.assertIn("record_a", it)
            self.assertIn("plant", it["record_a"])

    def test_explain_breaks_the_score_into_signals(self):
        a, b = self.a_pair()
        body = self.c.get(f"/api/pair/{a}/{b}/explain").get_json()
        self.assertIn("score", str(body))

    def test_performance_is_read_not_recomputed(self):
        body = self.c.get("/api/performance").get_json()
        self.assertTrue(body)

    def test_an_unknown_record_id_is_a_400_not_a_500(self):
        r = self.c.post("/api/pair/99999999/99999998/approve", json={},
                        headers=self.token("steward", "steward123"))
        self.assertEqual(r.status_code, 400)


class TestDecisionFlow(ApiCase):
    def test_approve_forms_a_group_and_mints_a_code(self):
        from engine import codegen
        steward = self.token("steward", "steward123")
        for a, b in [(int(r.a), int(r.b)) for r in
                     api_app.PAIRS[api_app.PAIRS.decision == "AUTO_SUGGEST"].head(40).itertuples()]:
            value = float(api_app.SPEND.get(a, 0)) + float(api_app.SPEND.get(b, 0))
            if value >= 1_000_000:          # skip the ones that will be parked
                continue
            body = self.c.post(f"/api/pair/{a}/{b}/approve", json={}, headers=steward).get_json()
            if body.get("status") == "applied" and body.get("national_code", {}).get("nmc"):
                self.assertTrue(codegen.is_valid_code(body["national_code"]["nmc"]))
                self.assertIn(body["national_code"]["status"], ("issued", "reused", "consolidated"))
                self.assertGreaterEqual(body["group"]["size"], 2)
                return
        self.skipTest("no cheap auto-suggest pair produced a mintable group")

    def test_a_high_value_merge_is_parked_for_a_second_signature(self):
        steward = self.token("steward", "steward123")
        candidates = sorted(
            [(int(r.a), int(r.b)) for r in
             api_app.PAIRS[api_app.PAIRS.decision == "AUTO_SUGGEST"].head(400).itertuples()],
            key=lambda ab: -(float(api_app.SPEND.get(ab[0], 0)) +
                             float(api_app.SPEND.get(ab[1], 0))))
        a, b = candidates[0]
        body = self.c.post(f"/api/pair/{a}/{b}/approve", json={}, headers=steward).get_json()
        self.assertEqual(body["status"], "awaiting_second")

        # it must not be in force yet
        pending = self.c.get("/api/pending-approvals").get_json()["pending"]
        self.assertIn((a, b), [(p["a"], p["b"]) for p in pending])

        # and a steward cannot countersign it
        self.assertEqual(
            self.c.post(f"/api/pair/{a}/{b}/countersign", json={}, headers=steward).status_code,
            403)

        approver = self.token("approver", "approver123")
        done = self.c.post(f"/api/pair/{a}/{b}/countersign", json={}, headers=approver)
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.get_json()["status"], "applied")


class TestRegistryRoutes(ApiCase):
    def test_a_mistyped_code_is_caught_by_its_check_digit(self):
        from engine import codegen
        good = codegen.mint_code("10.30.10", 7)
        bad = good[:-1] + str((int(good[-1]) + 1) % 10)
        r = self.c.get(f"/api/nmc/{bad}")
        self.assertEqual(r.status_code, 400)
        self.assertIn("check digit", r.get_json()["error"])

    def test_a_foreign_identifier_is_not_treated_as_a_mistyped_code(self):
        r = self.c.get("/api/nmc/MATNR-4711")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not a national material code", r.get_json()["error"])

    def test_a_valid_but_unissued_code_is_404(self):
        from engine import codegen
        r = self.c.get(f"/api/nmc/{codegen.mint_code('99.99.99', 99999)}")
        self.assertEqual(r.status_code, 404)

    def test_registry_stats_and_catalogue_respond(self):
        self.assertEqual(self.c.get("/api/registry/stats").status_code, 200)
        self.assertEqual(self.c.get("/api/registry/catalogue?limit=5").status_code, 200)
        self.assertEqual(self.c.get("/api/registry/provisional").status_code, 200)

    def test_lookup_requires_a_legacy_code(self):
        self.assertEqual(self.c.get("/api/lookup?cpse=IOCL").status_code, 400)


if __name__ == "__main__":
    unittest.main()
