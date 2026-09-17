"""Accounts, roles, sessions, and the two-person rule."""
import sqlite3
import time
import unittest

import helpers  # noqa: F401
from api import auth, store


class AuthCase(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        auth.init_auth(self.conn)


class TestPasswords(AuthCase):
    def test_correct_password_authenticates(self):
        self.assertIsNotNone(auth.verify(self.conn, "steward", "steward123"))

    def test_wrong_password_does_not(self):
        self.assertIsNone(auth.verify(self.conn, "steward", "steward124"))

    def test_unknown_user_does_not(self):
        self.assertIsNone(auth.verify(self.conn, "nobody", "steward123"))

    def test_the_password_is_not_stored(self):
        row = self.conn.execute("SELECT salt, pwd_hash FROM users WHERE username='steward'"
                                ).fetchone()
        self.assertNotIn(b"steward123", row[1])
        self.assertEqual(len(row[0]), 16)

    def test_two_users_with_the_same_password_hash_differently(self):
        auth.create_user(self.conn, "a", "A", "IOCL", "steward", "same-password")
        auth.create_user(self.conn, "b", "B", "IOCL", "steward", "same-password")
        ha = self.conn.execute("SELECT pwd_hash FROM users WHERE username='a'").fetchone()[0]
        hb = self.conn.execute("SELECT pwd_hash FROM users WHERE username='b'").fetchone()[0]
        self.assertNotEqual(ha, hb, "per-user salts must make identical passwords differ")

    def test_an_unknown_role_is_refused(self):
        with self.assertRaises(ValueError):
            auth.create_user(self.conn, "x", "X", "IOCL", "superuser", "pw")


class TestSessions(AuthCase):
    def test_login_issues_a_usable_token(self):
        s = auth.login(self.conn, "steward", "steward123")
        self.assertEqual(auth.user_for_token(self.conn, s["token"])["role"], "steward")

    def test_tokens_are_unpredictable_and_unique(self):
        tokens = {auth.login(self.conn, "steward", "steward123")["token"] for _ in range(20)}
        self.assertEqual(len(tokens), 20)
        self.assertGreaterEqual(len(tokens.pop()), 32)

    def test_logout_actually_revokes(self):
        s = auth.login(self.conn, "steward", "steward123")
        auth.logout(self.conn, s["token"])
        self.assertIsNone(auth.user_for_token(self.conn, s["token"]))

    def test_an_expired_session_is_refused_and_cleaned_up(self):
        s = auth.login(self.conn, "steward", "steward123")
        self.conn.execute("UPDATE sessions SET expires_ts=? WHERE token=?",
                          (time.time() - 1, s["token"]))
        self.conn.commit()
        self.assertIsNone(auth.user_for_token(self.conn, s["token"]))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)

    def test_a_deactivated_account_cannot_use_an_existing_session(self):
        s = auth.login(self.conn, "steward", "steward123")
        self.conn.execute("UPDATE users SET active=0 WHERE username='steward'")
        self.conn.commit()
        self.assertIsNone(auth.user_for_token(self.conn, s["token"]))

    def test_a_garbage_token_is_just_refused(self):
        self.assertIsNone(auth.user_for_token(self.conn, "not-a-token"))
        self.assertIsNone(auth.user_for_token(self.conn, None))


class TestRoles(AuthCase):
    def test_roles_are_cumulative(self):
        admin = dict(role="admin")
        viewer = dict(role="viewer")
        self.assertTrue(auth.can(admin, "steward"))
        self.assertTrue(auth.can(admin, "admin"))
        self.assertFalse(auth.can(viewer, "steward"))
        self.assertTrue(auth.can(viewer, "viewer"))

    def test_nobody_is_not_allowed_anything(self):
        self.assertFalse(auth.can(None, "viewer"))


class TestMakerChecker(unittest.TestCase):
    def setUp(self):
        self.conn = store.init_db(_tmp_db())

    def test_a_small_merge_applies_immediately(self):
        status = store.record_review(self.conn, 1, 2, "approve", "steward",
                                     value_at_stake=100.0, needs_second=False)
        self.assertEqual(status, "applied")
        self.assertIn((1, 2), store.approved_edges(self.conn))

    def test_a_large_merge_is_parked_and_does_not_form_a_group(self):
        value = auth.SECOND_APPROVAL_VALUE * 2
        status = store.record_review(self.conn, 1, 2, "approve", "steward",
                                     value_at_stake=value,
                                     needs_second=auth.needs_second_approval(value))
        self.assertEqual(status, "awaiting_second")
        self.assertEqual(store.approved_edges(self.conn), [],
                         "a parked merge must not take effect in the meantime")
        self.assertEqual(len(store.pending_second_approval(self.conn)), 1)

    def test_the_same_person_cannot_countersign_their_own_merge(self):
        value = auth.SECOND_APPROVAL_VALUE * 2
        store.record_review(self.conn, 1, 2, "approve", "steward", value_at_stake=value,
                            needs_second=True)
        ok, msg = store.countersign(self.conn, 1, 2, "steward")
        self.assertFalse(ok)
        self.assertIn("same person", msg)
        self.assertEqual(store.approved_edges(self.conn), [])

    def test_a_different_approver_applies_it(self):
        store.record_review(self.conn, 1, 2, "approve", "steward",
                            value_at_stake=auth.SECOND_APPROVAL_VALUE * 2, needs_second=True)
        ok, _msg = store.countersign(self.conn, 1, 2, "approver")
        self.assertTrue(ok)
        self.assertIn((1, 2), store.approved_edges(self.conn))

    def test_countersigning_twice_is_refused(self):
        store.record_review(self.conn, 1, 2, "approve", "steward",
                            value_at_stake=auth.SECOND_APPROVAL_VALUE * 2, needs_second=True)
        store.countersign(self.conn, 1, 2, "approver")
        ok, _ = store.countersign(self.conn, 1, 2, "admin")
        self.assertFalse(ok)

    def test_rejecting_is_never_parked(self):
        """Making the cautious action harder than the risky one is how
        two-person rules get routed around."""
        status = store.record_review(self.conn, 1, 2, "reject", "steward",
                                     value_at_stake=auth.SECOND_APPROVAL_VALUE * 99,
                                     needs_second=True)
        self.assertEqual(status, "applied")

    def test_the_audit_log_records_the_parking_and_the_countersignature(self):
        store.record_review(self.conn, 1, 2, "approve", "steward",
                            value_at_stake=auth.SECOND_APPROVAL_VALUE * 2, needs_second=True)
        store.countersign(self.conn, 1, 2, "approver")
        actions = [r["action"] for r in store.audit_log(self.conn)]
        self.assertIn("countersign", actions)
        parked = [r for r in store.audit_log(self.conn) if "parked" in (r["detail"] or "")]
        self.assertTrue(parked)

    def test_pairs_are_stored_unordered(self):
        store.record_review(self.conn, 9, 4, "approve", "steward")
        self.assertIsNotNone(store.get_review(self.conn, 4, 9))


def _tmp_db():
    import pathlib
    import tempfile
    return pathlib.Path(tempfile.mkdtemp()) / "steward.db"


if __name__ == "__main__":
    unittest.main()
