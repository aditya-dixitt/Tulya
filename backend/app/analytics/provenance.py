"""Every number that leaves this package says where it came from.

The quantities in this project come from a synthetic benchmark dataset, not
from a CPSE's ERP. They are useful for showing what harmonised identity *would*
let a procurement team see. They are worse than worthless if anyone quotes them
as a measured saving — a slide that says "₹4.2 crore saved" sourced from a
generator is the single most damaging thing this repo could produce.

So a bare float does not leave this package. `Figure` carries a value, a
provenance and a `basis` string that says in plain words where the number came
from, and it refuses to exist without all three. `procurement_opportunities`
and `impact_scenarios` both have `provenance` and `basis` as NOT NULL columns
for the same reason; this is that rule expressed where the arithmetic happens.

**Provenance is inherited, not asserted.** `derive()` takes the worst
provenance among its inputs. You cannot compute a MEASURED figure from a
SIMULATED one by calling it derived — the lattice makes that unrepresentable
rather than discouraged, which matters because the tempting mistake is exactly
one aggregation step away from the honest label.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass

MEASURED = "MEASURED"
DERIVED = "DERIVED"
SIMULATED = "SIMULATED"

KNOWN = (MEASURED, DERIVED, SIMULATED)

#: how far each label is from "we observed this". Aggregation can only move
#: away from observation, never toward it.
_DISTANCE = {MEASURED: 0, DERIVED: 1, SIMULATED: 2}


class ProvenanceError(ValueError):
    """A number that cannot be honestly labelled is refused rather than shipped."""


def combine(*provenances: str) -> str:
    """The weakest claim among the inputs. One simulated input simulates the lot."""
    if not provenances:
        raise ProvenanceError("a derived figure must name at least one input")
    for p in provenances:
        if p not in KNOWN:
            raise ProvenanceError(f"unknown provenance {p!r}; expected one of {KNOWN}")
    return max(provenances, key=lambda p: _DISTANCE[p])


@dataclass(frozen=True)
class Figure:
    """A number with its provenance and a human-checkable basis."""

    value: float
    provenance: str
    basis: str

    def __post_init__(self):
        if self.provenance not in KNOWN:
            raise ProvenanceError(
                f"unknown provenance {self.provenance!r}; expected one of {KNOWN}")
        if not (self.basis or "").strip():
            raise ProvenanceError(
                f"a figure of {self.value} was created with no basis — say where it "
                f"came from in words a non-technical reader can check, or do not "
                f"produce the number")
        try:
            float(self.value)
        except (TypeError, ValueError):
            raise ProvenanceError(f"{self.value!r} is not a number")

    @property
    def is_measured(self) -> bool:
        return self.provenance == MEASURED

    @property
    def quotable_as_saving(self) -> bool:
        """Only an observed figure may be presented as a realised outcome."""
        return self.provenance == MEASURED

    def as_dict(self) -> dict:
        return {"value": self.value, "provenance": self.provenance,
                "basis": self.basis, "quotable_as_saving": self.quotable_as_saving}

    def __str__(self) -> str:
        return f"{self.value:g} [{self.provenance}: {self.basis}]"


def measured(value: float, basis: str) -> Figure:
    """Something read directly from the source extract."""
    return Figure(value=value, provenance=MEASURED, basis=basis)


def simulated(value: float, basis: str) -> Figure:
    """Something the benchmark generator produced."""
    return Figure(value=value, provenance=SIMULATED, basis=basis)


def derive(value: float, basis: str, *inputs) -> Figure:
    """A figure computed from others. Inherits the weakest input's provenance.

    `inputs` may be Figures or provenance strings.
    """
    if not inputs:
        raise ProvenanceError(
            "a derived figure must name its inputs, otherwise its provenance is "
            "an assertion rather than a consequence")
    labels = [i.provenance if isinstance(i, Figure) else i for i in inputs]
    worst = combine(*labels)
    # DERIVED is a step away from MEASURED; it can never be a step back toward it
    provenance = DERIVED if worst == MEASURED else worst
    return Figure(value=value, provenance=provenance, basis=basis)
