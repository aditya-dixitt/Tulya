"""The SAP round trip: extract, mint, write back, load, verify.

The assertion that matters most to a CPSE is `test_matnr_is_never_modified`.
Everything else in the connector is replaceable; renumbering a live material
master is not recoverable.
"""
import json
import sqlite3
import tempfile
import unittest
import pathlib

import helpers
from engine import registry
from erp import extract as erp_extract, mock_erp, sap, writeback


class ErpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.recs, self.prep = helpers.bolts()
        flat = self.recs.reset_index()
        flat["category_true"] = "hex_bolt"
        self.export = mock_erp.export_extract(flat, self.tmp / "IOCL", truncate=False)
        self.conn = registry.init_registry(sqlite3.connect(":memory:"))


class TestExtract(ErpCase):
    def test_writes_the_four_sap_tables(self):
        for name in ("MARA", "MAKT", "MARC", "MARD"):
            self.assertTrue((self.tmp / "IOCL" / f"{name}.csv").exists(), name)

    def test_reads_back_every_material(self):
        df, report, rejects = erp_extract.load_extract(self.tmp / "IOCL", cpse="IOCL")
        self.assertEqual(len(df), len(self.recs))
        self.assertEqual(rejects, [])
        self.assertEqual(report["records"], len(self.recs))

    def test_a_material_without_a_description_is_rejected_loudly(self):
        rows = sap.read_table(self.tmp / "IOCL" / "MAKT.csv")
        sap.write_table(self.tmp / "IOCL" / "MAKT.csv", sap.MAKT_FIELDS, rows[:-1])
        df, report, rejects = erp_extract.load_extract(self.tmp / "IOCL", cpse="IOCL")
        self.assertEqual(len(rejects), 1)
        self.assertIn("MAKTX", rejects[0]["reason"])
        self.assertEqual(report["rejected"], 1)

    def test_plant_codes_never_collide(self):
        seen = {}
        codes = [sap.plant_code(p, seen) for p in
                 ["Panipat Refinery", "Paradip Refinery", "Mathura Refinery", "Mumbai Terminal"]]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(len(c) <= sap.WERKS_LIMIT for c in codes))

    def test_maktx_pressure_is_measured_not_asserted(self):
        long_desc = ["x" * 60, "y" * 10]
        p = sap.maktx_pressure(long_desc)
        self.assertEqual(p["over_limit"], 1)
        self.assertEqual(p["chars_lost"], 20)

    def test_truncation_really_truncates(self):
        flat = self.recs.reset_index()
        exp = mock_erp.export_extract(flat, self.tmp / "T", truncate=True)
        self.assertLessEqual(exp["maktx_after"]["max_len"], sap.MAKTX_LIMIT)


class TestWriteBack(ErpCase):
    def _mint_and_emit(self, mode="full"):
        df, _r, _x = erp_extract.load_extract(self.tmp / "IOCL", cpse="IOCL")
        idx = df.set_index("record_id")
        prep = self.prep.copy()
        prep.index = idx.index                     # extract reindexes from 0
        registry.mint_for_group(self.conn, list(idx.index[:3]), idx, prep, actor="steward")
        return df, writeback.emit_batch(self.conn, df, self.tmp / "out",
                                        approver="steward", mode=mode, threshold=0.92)

    def test_matnr_is_never_modified(self):
        """The whole write-back design in one assertion: the national code is an
        added column in a Z table, not a replacement material number."""
        df, manifest = self._mint_and_emit()
        self.assertFalse(manifest["matnr_modified"])
        self.assertEqual(manifest["target_table"], "Z_NMC_MAP")
        rows = sap.read_table(self.tmp / "out" / manifest["payload_file"])
        original = {str(c) for c in df.matnr}
        self.assertTrue({r["MATNR"] for r in rows}.issubset(original))

    def test_manifest_checksum_matches_the_payload(self):
        _df, manifest = self._mint_and_emit()
        self.assertTrue(writeback.verify_batch(self.tmp / "out", manifest["batch_id"])["ok"])

    def test_an_edited_payload_fails_verification(self):
        _df, manifest = self._mint_and_emit()
        path = self.tmp / "out" / manifest["payload_file"]
        path.write_text(path.read_text() + "\n")
        self.assertFalse(writeback.verify_batch(self.tmp / "out", manifest["batch_id"])["ok"])

    def test_payload_is_byte_identical_across_runs(self):
        """Idempotency: two loads of an unchanged registry must be the same file,
        so 'has anything changed' is answerable by comparing one hash."""
        df, first = self._mint_and_emit()
        second = writeback.emit_batch(self.conn, df, self.tmp / "out2",
                                      approver="steward", mode="full", threshold=0.92)
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])

    def test_delta_mode_suppresses_unchanged_rows(self):
        df, _first = self._mint_and_emit()
        delta = writeback.emit_batch(self.conn, df, self.tmp / "out",
                                     approver="steward", mode="delta", threshold=0.92)
        self.assertEqual(delta["rows"], 0)
        self.assertGreater(delta["rows_unchanged_suppressed"], 0)

    def test_revoking_keeps_the_payload_on_disk(self):
        _df, manifest = self._mint_and_emit()
        revoked = writeback.revoke_batch(self.tmp / "out", manifest["batch_id"], "wrong split")
        self.assertTrue(revoked["revoked"])
        self.assertTrue((self.tmp / "out" / manifest["payload_file"]).exists())

    def test_provisional_rows_are_flagged_in_the_payload(self):
        df, _r, _x = erp_extract.load_extract(self.tmp / "IOCL", cpse="IOCL")
        crecs, cprep = helpers.truncated_cables()
        registry.mint_for_group(self.conn, [10, 12], crecs, cprep, canonical_id=10)
        rows = writeback.build_payload(self.conn, crecs.reset_index(), approver="s")
        conf = {r["MATNR"]: r["ZZNMC_CONF"] for r in rows}
        self.assertEqual(conf["M-1"], "C")
        self.assertEqual(conf["M-3"], "P")


class TestErpAcceptance(ErpCase):
    def test_the_erp_accepts_a_well_formed_batch(self):
        df, _r, _x = erp_extract.load_extract(self.tmp / "IOCL", cpse="IOCL")
        idx = df.set_index("record_id")
        prep = self.prep.copy()
        prep.index = idx.index
        registry.mint_for_group(self.conn, list(idx.index[:3]), idx, prep, actor="steward")
        manifest = writeback.emit_batch(self.conn, df, self.tmp / "out", approver="steward")
        applied, rejects = mock_erp.apply_batch(
            self.tmp / "IOCL", self.tmp / "out" / manifest["payload_file"])
        self.assertEqual(rejects, [])
        self.assertEqual(len(applied), manifest["rows"])

    def test_a_code_failing_its_check_digit_is_rejected_at_the_erp(self):
        rows = [dict(MANDT=sap.CLIENT, MATNR="10001", WERKS="PR0",
                     ZZNMC="NMC-20-10-10-00001-9", ZZNMC_CLASS="20.10.10",
                     ZZNMC_STATUS="A", ZZNMC_CONF="C", ZZ_UNCONFIRMED="",
                     ZZ_VALID_FROM="20260915", ZZ_SOURCE="SAMANVAY", ZZ_APPROVER="x")]
        applied, rejects = mock_erp.apply_batch(self.tmp / "IOCL", rows)
        self.assertEqual(applied, [])
        self.assertIn("check digit", rejects[0]["_reason"])

    def test_a_row_for_an_unknown_material_is_rejected(self):
        from engine import codegen
        rows = [dict(MANDT=sap.CLIENT, MATNR="NOT-A-MATERIAL", WERKS="PR0",
                     ZZNMC=codegen.mint_code("20.10.10", 1), ZZNMC_CLASS="20.10.10",
                     ZZNMC_STATUS="A", ZZNMC_CONF="C", ZZ_UNCONFIRMED="",
                     ZZ_VALID_FROM="20260915", ZZ_SOURCE="SAMANVAY", ZZ_APPROVER="x")]
        applied, rejects = mock_erp.apply_batch(self.tmp / "IOCL", rows)
        self.assertEqual(applied, [])
        self.assertIn("material master", rejects[0]["_reason"])

    def test_a_row_for_the_wrong_client_is_rejected(self):
        from engine import codegen
        rows = [dict(MANDT="999", MATNR="10001", WERKS="PR0",
                     ZZNMC=codegen.mint_code("20.10.10", 1), ZZNMC_CLASS="20.10.10",
                     ZZNMC_STATUS="A", ZZNMC_CONF="C", ZZ_UNCONFIRMED="",
                     ZZ_VALID_FROM="20260915", ZZ_SOURCE="SAMANVAY", ZZ_APPROVER="x")]
        applied, rejects = mock_erp.apply_batch(self.tmp / "IOCL", rows)
        self.assertIn("MANDT", rejects[0]["_reason"])


if __name__ == "__main__":
    unittest.main()
