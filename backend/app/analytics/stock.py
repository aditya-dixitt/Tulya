"""Cross-CPSE availability for one harmonised identity.

The question a materials manager actually has: *I need 400 of this. Does anyone
else already hold it?* Harmonised identity is what makes that question
answerable at all — before it, the same bolt sits under six codes and nobody
can add them up.

Three rules shape the answer:

**A PROVISIONAL mapping does not authorise a transfer.** A member whose own
description could not confirm the code's signature is in the group because the
group agreed, not because that row was verified. Its stock is *reported* — a
planner wants to know it might be there — but it does not count toward headline
availability or coverage. Same asymmetry as everywhere else in this system:
weak evidence may raise a question, never settle one.

**An unresolved identity produces no recommendation.** If nobody has confirmed
what this item is, a transfer proposal against it is a guess wearing a number.
The signal is `UNRESOLVED_CASE` and the quantities are still reported, because
"we cannot advise on this one" is itself an operational fact.

**The requester's own stock is not cross-CPSE stock.** Excluded by
construction, so a CPSE is never told to source from itself.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .provenance import SIMULATED, Figure, derive

# signal vocabulary — mirrors the CHECK constraint on procurement_opportunities
CROSS_CPSE_STOCK_FOUND = "CROSS_CPSE_STOCK_FOUND"
DEMAND_AGGREGATION_CANDIDATE = "DEMAND_AGGREGATION_CANDIDATE"
OPPORTUNITY_DETECTED = "OPPORTUNITY_DETECTED"
NO_CROSS_CPSE_STOCK = "NO_CROSS_CPSE_STOCK"
UNRESOLVED_CASE = "UNRESOLVED_CASE"

INTRA = "INTRA"
INTER = "INTER"


@dataclass(frozen=True)
class Holding:
    """One member record's stock, as the source extract states it."""

    record_id: int
    cpse: str
    qty: float = 0.0
    unit_value: float = 0.0
    plant: str | None = None
    link_status: str = "CONFIRMED"      # CONFIRMED | PROVISIONAL | WITHDRAWN

    @property
    def counts(self) -> bool:
        """Only a confirmed mapping may back a transfer recommendation."""
        return self.link_status == "CONFIRMED" and (self.qty or 0) > 0

    @property
    def value(self) -> float:
        return float(self.qty or 0) * float(self.unit_value or 0)


@dataclass(frozen=True)
class Availability:
    signal: str
    scope: str | None
    required: Figure
    available: Figure                  # confirmed only
    reported_provisional: Figure       # excluded from `available`, shown anyway
    coverage: Figure
    shortfall: Figure
    best_source_record_id: int | None
    contributing_cpses: tuple[str, ...] = field(default=())
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "signal": self.signal, "scope": self.scope,
            "required": self.required.as_dict(),
            "available": self.available.as_dict(),
            "reported_provisional": self.reported_provisional.as_dict(),
            "coverage": self.coverage.as_dict(),
            "shortfall": self.shortfall.as_dict(),
            "best_source_record_id": self.best_source_record_id,
            "contributing_cpses": list(self.contributing_cpses),
            "note": self.note,
        }

    def as_opportunity_row(self, *, identity_id=None, code_id=None,
                           requesting_cpse_id=None) -> dict:
        """Shaped for ProcurementOpportunity(**row) — provenance and basis carried."""
        return {
            "identity_id": identity_id, "code_id": code_id,
            "requesting_cpse_id": requesting_cpse_id,
            "required_qty": self.required.value,
            "available_qty": self.available.value,
            "best_source_record_id": self.best_source_record_id,
            "coverage": self.coverage.value,
            "signal": self.signal, "scope": self.scope,
            "provenance": self.coverage.provenance,
            "basis": self.coverage.basis,
        }


def availability(required_qty: float, holdings, *, requesting_cpse: str,
                 identity_resolved: bool = True,
                 source_provenance: str = SIMULATED) -> Availability:
    """What the harmonised identity says is available to `requesting_cpse`."""
    if required_qty is None or float(required_qty) < 0:
        raise ValueError("required quantity must be zero or positive")
    required_qty = float(required_qty)
    holdings = [h for h in (holdings or []) if h.cpse != requesting_cpse]

    confirmed = [h for h in holdings if h.counts]
    provisional = [h for h in holdings
                   if h.link_status == "PROVISIONAL" and (h.qty or 0) > 0]

    available_qty = sum(h.qty for h in confirmed)
    provisional_qty = sum(h.qty for h in provisional)
    cpses = tuple(sorted({h.cpse for h in confirmed}))

    req = Figure(required_qty, source_provenance,
                 f"requested quantity for {requesting_cpse}, from the source extract")
    avail = derive(
        available_qty,
        f"sum of qty across {len(confirmed)} confirmed member record(s) in "
        f"{len(cpses)} other CPSE(s); provisional mappings excluded",
        source_provenance)
    prov_only = derive(
        provisional_qty,
        f"sum of qty across {len(provisional)} member record(s) whose own "
        f"description could not confirm the code signature — reported, not counted",
        source_provenance)

    cov_value = 0.0 if required_qty <= 0 else min(1.0, available_qty / required_qty)
    coverage = derive(
        cov_value,
        ("no quantity was requested, so coverage is undefined and reported as 0"
         if required_qty <= 0 else
         f"{available_qty:g} confirmed available against {required_qty:g} required, "
         f"capped at 1.0"),
        req, avail)
    shortfall = derive(max(0.0, required_qty - available_qty),
                       "required minus confirmed available, floored at zero",
                       req, avail)

    # the single record best able to meet the need: largest confirmed qty,
    # ties broken by lowest record id so the answer is stable
    best = min(confirmed, key=lambda h: (-h.qty, h.record_id)).record_id if confirmed else None

    if not identity_resolved:
        signal, note = UNRESOLVED_CASE, (
            "the identity behind this demand is not confirmed, so no sourcing "
            "recommendation is made; the quantities are reported for context only")
    elif not confirmed:
        signal = NO_CROSS_CPSE_STOCK
        note = ("no other CPSE holds a confirmed mapping with stock"
                + (f"; {provisional_qty:g} sits behind provisional mappings and "
                   f"would need confirming first" if provisional_qty else ""))
    elif cov_value >= 1.0:
        signal, note = CROSS_CPSE_STOCK_FOUND, (
            f"{', '.join(cpses)} can meet the requirement in full")
    else:
        signal, note = OPPORTUNITY_DETECTED, (
            f"{', '.join(cpses)} can cover {cov_value:.0%} of the requirement")

    return Availability(
        signal=signal, scope=INTER if cpses else INTRA,
        required=req, available=avail, reported_provisional=prov_only,
        coverage=coverage, shortfall=shortfall,
        best_source_record_id=best, contributing_cpses=cpses, note=note,
    )
