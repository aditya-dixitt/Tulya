"""Cross-CPSE harmonisation scenarios — the "what if we pooled this" question.

A steward picks an identity, the CPSEs that would participate, and a demand
multiplier, and asks what pooling would look like. The outputs are exactly the
columns on `impact_scenarios`, each one a `Figure` carrying its basis.

The danger this module is built against is named in the project's own risk
table: *simulated quantities get quoted as measured savings*. Two defences.

**Nothing here produces a money figure.** Quantities, coverage and a
consolidation count — no rupees. A quantity labelled SIMULATED that someone
misreads is an overstated stock position; a *saving* labelled SIMULATED that
someone misreads ends up in a board pack. Value is available on the holdings if
a caller genuinely needs it, and no output of this module multiplies it up into
a headline.

**An unresolved identity cannot be modelled.** `compute()` refuses rather than
returning zeros that read like a finding. "This case is not ready to model" is
the honest output, and it is an exception because a caller that ignores it
would otherwise publish a scenario about an item nobody has confirmed.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .provenance import SIMULATED, Figure, derive
from .stock import DEMAND_AGGREGATION_CANDIDATE, Holding


class ScenarioError(ValueError):
    """Inputs that cannot produce an honest scenario."""


@dataclass(frozen=True)
class ScenarioInputs:
    identity_id: int
    participating_cpses: tuple[str, ...]
    required_qty: float
    demand_multiplier: float = 1.0
    label: str | None = None

    def __post_init__(self):
        if not self.participating_cpses:
            raise ScenarioError("a scenario needs at least one participating CPSE")
        if len(set(self.participating_cpses)) != len(self.participating_cpses):
            raise ScenarioError("a CPSE cannot participate twice")
        if self.required_qty is None or float(self.required_qty) < 0:
            raise ScenarioError("required quantity must be zero or positive")
        if float(self.demand_multiplier) <= 0:
            raise ScenarioError(
                "demand multiplier must be positive; a zero or negative multiplier "
                "produces a scenario with no demand, which is not a scenario")

    def as_dict(self) -> dict:
        return {"identity_id": self.identity_id,
                "participating_cpse_ids": list(self.participating_cpses),
                "required_qty": self.required_qty,
                "demand_multiplier": self.demand_multiplier, "label": self.label}


@dataclass(frozen=True)
class ScenarioOutputs:
    demand: Figure
    combined_stock: Figure
    coverage: Figure
    surplus: Figure
    procurement_requirement: Figure
    legacy_codes_consolidated: Figure
    aggregation_opportunity: bool
    signal: str | None
    excluded_provisional: Figure
    participants: tuple[str, ...] = field(default=())
    basis: str = ""

    @property
    def provenance(self) -> str:
        """The scenario is only as strong as its weakest output."""
        from .provenance import combine
        return combine(self.demand.provenance, self.combined_stock.provenance,
                       self.coverage.provenance)

    def as_dict(self) -> dict:
        return {
            "demand": self.demand.as_dict(),
            "combined_stock": self.combined_stock.as_dict(),
            "coverage": self.coverage.as_dict(),
            "surplus": self.surplus.as_dict(),
            "procurement_requirement": self.procurement_requirement.as_dict(),
            "legacy_codes_consolidated": self.legacy_codes_consolidated.as_dict(),
            "excluded_provisional": self.excluded_provisional.as_dict(),
            "aggregation_opportunity": self.aggregation_opportunity,
            "signal": self.signal, "participants": list(self.participants),
            "provenance": self.provenance, "basis": self.basis,
        }

    def as_scenario_row(self, inputs: ScenarioInputs, *, created_by_id=None) -> dict:
        """Shaped for ImpactScenario(**row). provenance and basis are NOT NULL."""
        return {
            "identity_id": inputs.identity_id, "created_by_id": created_by_id,
            "label": inputs.label,
            "participating_cpse_ids": list(inputs.participating_cpses),
            "demand_multiplier": inputs.demand_multiplier,
            "required_qty": inputs.required_qty,
            "combined_stock": self.combined_stock.value,
            "coverage": self.coverage.value,
            "surplus": self.surplus.value,
            "procurement_requirement": self.procurement_requirement.value,
            "legacy_codes_consolidated": int(self.legacy_codes_consolidated.value),
            "aggregation_opportunity": self.aggregation_opportunity,
            "outputs": self.as_dict(),
            "provenance": self.provenance, "basis": self.basis,
        }


def compute(inputs: ScenarioInputs, holdings, *, identity_resolved: bool = True,
            source_provenance: str = SIMULATED) -> ScenarioOutputs:
    """Model pooling across the participating CPSEs."""
    if not identity_resolved:
        raise ScenarioError(
            f"identity {inputs.identity_id} is not confirmed; a pooling scenario "
            f"against an unconfirmed item would read as a finding about something "
            f"nobody has agreed exists")

    participating = set(inputs.participating_cpses)
    inside = [h for h in (holdings or []) if h.cpse in participating]
    confirmed = [h for h in inside if h.counts]
    provisional = [h for h in inside
                   if h.link_status == "PROVISIONAL" and (h.qty or 0) > 0]

    demand_value = float(inputs.required_qty) * float(inputs.demand_multiplier)
    stock_value = sum(h.qty for h in confirmed)

    demand = derive(
        demand_value,
        f"{inputs.required_qty:g} required x {inputs.demand_multiplier:g} demand "
        f"multiplier, both supplied by the person running the scenario",
        source_provenance)
    combined = derive(
        stock_value,
        f"sum of qty across {len(confirmed)} confirmed member record(s) in "
        f"{len(participating)} participating CPSE(s)",
        source_provenance)
    excluded = derive(
        sum(h.qty for h in provisional),
        f"{len(provisional)} provisional member record(s) excluded from the "
        f"combined stock — their descriptions could not confirm the signature",
        source_provenance)

    cov_value = 0.0 if demand_value <= 0 else min(1.0, stock_value / demand_value)
    coverage = derive(
        cov_value,
        ("no demand was modelled, so coverage is undefined and reported as 0"
         if demand_value <= 0 else
         f"{stock_value:g} pooled against {demand_value:g} demand, capped at 1.0"),
        demand, combined)
    surplus = derive(max(0.0, stock_value - demand_value),
                     "pooled stock above modelled demand, floored at zero",
                     demand, combined)
    requirement = derive(max(0.0, demand_value - stock_value),
                         "modelled demand not met from pooled stock, floored at zero",
                         demand, combined)

    legacy = {(h.cpse, h.record_id) for h in inside}
    consolidated = derive(
        float(len(legacy)),
        f"{len(legacy)} separate legacy record(s) across "
        f"{len(participating)} CPSE(s) would resolve to one national code",
        source_provenance)

    aggregation = len(participating) >= 2 and requirement.value > 0
    signal = DEMAND_AGGREGATION_CANDIDATE if aggregation else None

    basis = (
        f"Scenario over {len(participating)} CPSE(s) on identity "
        f"{inputs.identity_id}. Quantities come from the benchmark dataset, not "
        f"from any CPSE ERP, and are {source_provenance}. No monetary figure is "
        f"produced by this scenario."
    )

    return ScenarioOutputs(
        demand=demand, combined_stock=combined, coverage=coverage, surplus=surplus,
        procurement_requirement=requirement,
        legacy_codes_consolidated=consolidated, excluded_provisional=excluded,
        aggregation_opportunity=aggregation, signal=signal,
        participants=tuple(sorted(participating)), basis=basis,
    )
