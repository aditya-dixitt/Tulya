"""Deciding whether a group earns a national code, and on what terms.

`codegen.py` builds the code string. This decides whether one should exist at
all, which members it may claim, and what happens when it is retired.

Three rules, each of which the registry would be worse without:

**A code asserts a specification.** It is minted against the group's
consolidated profile, and the profile becomes the code's `signature`. A group
with nothing readable on both sides gets no code — `INSUFFICIENT_EVIDENCE` —
because a national code whose defining specification is "unknown" is a number
pretending to be an identity.

**A member whose own description cannot confirm the signature is PROVISIONAL,
not CONFIRMED.** The group agreed; that is why it is a group. But a truncated
row that agreed by staying silent has not actually confirmed anything, and the
difference matters when someone later asks "which of these did we verify". The
keys it could not confirm are listed on the membership rather than shrugged off.

**Refusals are kept.** `CodeRefusal` exists because "we could not code this" is
an operational fact a materials team needs. A registry that silently drops the
groups it cannot handle looks better than it is.

Retirement is a status change plus a forwarding pointer, never a deletion —
old purchase orders carry printed codes nobody is going to reissue, so a
superseded code must still resolve. `superseded_needs_target` is the database
saying the same thing.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..matching.attributes import HARD_KEYS
from .codegen import mint_code

#: refusal reasons, kept short because they are stored and grouped on
NO_CLASS = "NO_CLASS"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
PROFILE_CONFLICT = "PROFILE_CONFLICT"

#: a code needs at least this many readable hard keys to assert an identity
MIN_SIGNATURE_KEYS = 1


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class MemberPlan:
    record_id: int
    link_status: str                      # CONFIRMED | PROVISIONAL
    unknown_keys: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"record_id": self.record_id, "link_status": self.link_status,
                "unknown_keys": list(self.unknown_keys)}


@dataclass(frozen=True)
class CodePlan:
    nmc: str
    class_code: str
    serial: int
    signature: str
    specs: dict
    canonical_record_id: int | None
    members: tuple[MemberPlan, ...] = ()

    @property
    def confirmed(self) -> int:
        return sum(1 for m in self.members if m.link_status == "CONFIRMED")

    @property
    def provisional(self) -> int:
        return len(self.members) - self.confirmed

    def as_dict(self) -> dict:
        return {"nmc": self.nmc, "class_code": self.class_code, "serial": self.serial,
                "signature": self.signature, "specs": dict(self.specs),
                "canonical_record_id": self.canonical_record_id,
                "members": [m.as_dict() for m in self.members],
                "confirmed": self.confirmed, "provisional": self.provisional}


@dataclass(frozen=True)
class Refusal:
    group_key: str
    reason: str
    detail: str
    members: tuple[int, ...] = field(default=())

    def as_dict(self) -> dict:
        return {"group_key": self.group_key, "reason": self.reason,
                "detail": self.detail, "members": list(self.members)}


def signature_of(profile: dict) -> str:
    """A stable, readable statement of what the code asserts.

    Sorted by the canonical HARD_KEYS order rather than alphabetically, so two
    codes for the same specification always render identically and a human can
    compare them by eye.
    """
    parts = [f"{k}={profile[k]}" for k in HARD_KEYS
             if profile.get(k) is not None]
    return "; ".join(parts)


def _member_plan(record_id: int, member_attrs: dict, signature_keys) -> MemberPlan:
    attrs = member_attrs or {}
    unknown = tuple(k for k in signature_keys if attrs.get(k) is None)
    return MemberPlan(
        record_id=record_id,
        link_status="PROVISIONAL" if unknown else "CONFIRMED",
        unknown_keys=unknown,
    )


def plan(group, attrs_by_record, *, class_code: str | None, serial: int,
         min_signature_keys: int = MIN_SIGNATURE_KEYS):
    """-> CodePlan, or Refusal explaining why this group gets no code.

    `group` is a `workflow.grouping.Group`.
    """
    members = tuple(group.members)
    group_key = ",".join(str(m) for m in members)

    if not class_code:
        return Refusal(group_key, NO_CLASS,
                       "the group has no class code, so no serial range applies",
                       members)

    profile = {k: v for k, v in (group.profile or {}).items() if v is not None}
    signature_keys = tuple(k for k in HARD_KEYS if k in profile)

    if len(signature_keys) < min_signature_keys:
        return Refusal(
            group_key, INSUFFICIENT_EVIDENCE,
            f"no hard specification could be read across the group, so a code "
            f"would assert an identity nothing supports ({len(members)} member(s))",
            members)

    # defensive: grouping should already have made this impossible
    for rid in members:
        a = attrs_by_record.get(rid) or {}
        clash = [k for k in signature_keys
                 if a.get(k) is not None and a[k] != profile[k]]
        if clash:
            return Refusal(
                group_key, PROFILE_CONFLICT,
                f"record {rid} contradicts the group profile on "
                f"{', '.join(clash)} — grouping should have blocked this edge",
                members)

    return CodePlan(
        nmc=mint_code(class_code, serial),
        class_code=class_code,
        serial=int(serial),
        signature=signature_of(profile),
        specs=dict(profile),
        canonical_record_id=group.canonical,
        members=tuple(_member_plan(rid, attrs_by_record.get(rid), signature_keys)
                      for rid in members),
    )


@dataclass(frozen=True)
class Supersession:
    old_nmc: str
    new_nmc: str
    status: str = "SUPERSEDED"

    def as_dict(self) -> dict:
        return {"old_nmc": self.old_nmc, "new_nmc": self.new_nmc,
                "status": self.status}


def supersede(old_nmc: str, new_nmc: str | None) -> Supersession:
    """Retire a code in favour of another. A retirement with no target is refused.

    This mirrors the `superseded_needs_target` CHECK constraint: a code that is
    retired without saying where it went breaks every printed document that
    quotes it, and the database will not accept the row either.
    """
    if not new_nmc:
        raise RegistryError(
            f"{old_nmc} cannot be superseded without naming the code that replaces "
            f"it — old purchase orders still carry this number and must resolve")
    if new_nmc == old_nmc:
        raise RegistryError(f"{old_nmc} cannot supersede itself")
    return Supersession(old_nmc=old_nmc, new_nmc=new_nmc)


def revoke(nmc: str, reason: str) -> dict:
    """Revocation is for a code issued in error. It still resolves, to nothing."""
    if not reason:
        raise RegistryError("a revocation must state why")
    return {"nmc": nmc, "status": "REVOKED", "reason": reason}
