"""Phase 6: the national code registry.

The Damm check digit is not tested against remembered outputs. The table's
defining property — total anti-symmetry — is re-derived from the table itself,
so a single mistyped cell fails the suite rather than being enshrined by a
fixture that was generated from the same typo.
"""
from __future__ import annotations

import itertools

import pytest

from app.registry import (
    INSUFFICIENT_EVIDENCE, NO_CLASS, MAX_SERIAL, RegistryError, damm_check,
    damm_valid, is_valid_code, mint_code, parse_code, plan, signature_of,
    supersede,
)
from app.registry.codegen import _DAMM
from app.workflow import Group


# --------------------------------------------------------------------------
# the check digit, from first principles
# --------------------------------------------------------------------------
def test_the_damm_table_is_a_quasigroup():
    """Every row and every column is a permutation of 0..9."""
    for i, row in enumerate(_DAMM):
        assert sorted(row) == list(range(10)), f"row {i} is not a permutation"
    for j in range(10):
        col = [_DAMM[i][j] for i in range(10)]
        assert sorted(col) == list(range(10)), f"column {j} is not a permutation"


def test_the_damm_table_is_totally_anti_symmetric():
    """The property that buys transposition detection.

    For all x, y, z:  (z*x)*y == (z*y)*x  implies  x == y.
    """
    for x, y, z in itertools.product(range(10), repeat=3):
        if x != y:
            assert _DAMM[_DAMM[z][x]][y] != _DAMM[_DAMM[z][y]][x]


def test_the_diagonal_is_zero_so_a_check_digit_validates_itself():
    for i in range(10):
        assert _DAMM[i][i] == 0


@pytest.mark.parametrize("digits", ["0", "12345", "9999999999", "10301000042"])
def test_appending_the_check_digit_makes_a_string_valid(digits):
    assert damm_valid(digits + str(damm_check(digits)))


def test_every_single_digit_error_is_caught():
    body = "10301000042"
    good = body + str(damm_check(body))
    for i in range(len(body)):
        for d in "0123456789":
            if d == body[i]:
                continue
            bad = body[:i] + d + body[i + 1:]
            assert not damm_valid(bad + good[-1])


def test_every_adjacent_transposition_is_caught():
    """This is the reason for Damm over Luhn — Luhn misses 09 <-> 90."""
    body = "10301000042"
    good = body + str(damm_check(body))
    caught = checked = 0
    for i in range(len(body) - 1):
        if body[i] == body[i + 1]:
            continue
        swapped = body[:i] + body[i + 1] + body[i] + body[i + 2:]
        checked += 1
        caught += not damm_valid(swapped + good[-1])
    assert checked and caught == checked


def test_luhn_would_have_missed_the_transposition_damm_catches():
    """09 <-> 90, the case named in the module docstring."""
    a, b = "09", "90"
    assert damm_check(a) != damm_check(b)


# --------------------------------------------------------------------------
# the code string
# --------------------------------------------------------------------------
def test_a_minted_code_round_trips():
    code = mint_code("10.30.10", 42)
    assert code.startswith("NMC-10-30-10-00042-")
    p = parse_code(code)
    assert p["class_code"] == "10.30.10" and p["serial"] == 42 and p["valid"]


def test_minting_is_pure_and_total():
    assert mint_code("10.30.10", 42) == mint_code("10.30.10", 42)


@pytest.mark.parametrize("bad", ["10.30", "1.30.10", "10.30.1", "ab.cd.ef"])
def test_a_malformed_class_code_is_refused(bad):
    with pytest.raises(ValueError):
        mint_code(bad, 1)


def test_a_serial_outside_the_range_is_refused():
    with pytest.raises(ValueError):
        mint_code("10.30.10", MAX_SERIAL + 1)


def test_a_typo_and_a_foreign_identifier_are_reported_differently():
    """One is a rejected row on an ERP import; the other is a row that isn't ours."""
    good = mint_code("10.30.10", 42)
    typo = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert parse_code(typo)["valid"] is False     # code-shaped, fails its check
    assert parse_code("SAP-000123") is None       # not ours at all
    assert not is_valid_code(typo)


# --------------------------------------------------------------------------
# minting decisions
# --------------------------------------------------------------------------
BOLT = {"thread": "M12", "length_mm": "50", "material_grade": "SS304"}


def _group(members, profile, canonical=None):
    return Group(members=tuple(members), profile=dict(profile),
                 canonical=canonical or members[0])


def test_a_group_with_a_readable_specification_earns_a_code():
    g = _group([1, 2], BOLT)
    p = plan(g, {1: BOLT, 2: dict(BOLT)}, class_code="10.30.10", serial=7)
    assert p.nmc.startswith("NMC-10-30-10-00007-")
    assert p.signature == "thread=M12; length_mm=50; material_grade=SS304"
    assert p.confirmed == 2 and p.provisional == 0


def test_a_group_with_nothing_readable_is_refused_not_coded():
    g = _group([1, 2], {})
    r = plan(g, {1: {}, 2: {}}, class_code="10.30.10", serial=7)
    assert r.reason == INSUFFICIENT_EVIDENCE
    assert "assert an identity nothing supports" in r.detail


def test_a_group_with_no_class_is_refused():
    r = plan(_group([1], BOLT), {1: BOLT}, class_code=None, serial=1)
    assert r.reason == NO_CLASS


def test_a_member_that_cannot_confirm_the_signature_is_provisional():
    """It agreed by staying silent, which is not the same as confirming."""
    g = _group([1, 2], BOLT)
    p = plan(g, {1: BOLT, 2: {"thread": "M12"}}, class_code="10.30.10", serial=7)
    by_id = {m.record_id: m for m in p.members}
    assert by_id[1].link_status == "CONFIRMED"
    assert by_id[2].link_status == "PROVISIONAL"
    assert set(by_id[2].unknown_keys) == {"length_mm", "material_grade"}


def test_the_signature_renders_in_a_stable_order():
    a = signature_of({"material_grade": "SS304", "thread": "M12"})
    b = signature_of({"thread": "M12", "material_grade": "SS304"})
    assert a == b == "thread=M12; material_grade=SS304"


def test_a_member_contradicting_the_profile_is_refused_defensively():
    """Grouping should make this impossible; the registry checks anyway."""
    g = _group([1, 2], BOLT)
    r = plan(g, {1: BOLT, 2: {"thread": "M16"}}, class_code="10.30.10", serial=7)
    assert r.reason == "PROFILE_CONFLICT"
    assert "grouping should have blocked" in r.detail


# --------------------------------------------------------------------------
# retirement
# --------------------------------------------------------------------------
def test_a_code_cannot_be_retired_without_saying_where_it_went():
    with pytest.raises(RegistryError) as exc:
        supersede("NMC-10-30-10-00042-7", None)
    assert "still carry this number" in str(exc.value)


def test_a_code_cannot_supersede_itself():
    with pytest.raises(RegistryError):
        supersede("NMC-10-30-10-00042-7", "NMC-10-30-10-00042-7")


def test_supersession_keeps_both_numbers_resolvable():
    s = supersede("NMC-10-30-10-00042-7", "NMC-10-30-10-00043-5")
    assert s.status == "SUPERSEDED"
    assert s.old_nmc and s.new_nmc          # neither is discarded
