"""Analytics, procurement and impact — all server-side.

Phase 7. Three pure modules:

    provenance  a number does not leave this package without saying where it
                came from; provenance is inherited from inputs, never asserted
    stock       cross-CPSE availability for one harmonised identity
    scenario    "what if these CPSEs pooled this" — the impact_scenarios inputs
                and outputs, each one carrying its basis

The risk this phase is built against is named in the project's own risk table:
*simulated quantities get quoted as measured savings*. The defences are that
`Figure` refuses to exist without a basis, that `derive()` takes the weakest
provenance among its inputs so MEASURED cannot be manufactured one aggregation
step away from SIMULATED, and that nothing in here produces a money figure at
all. A misread quantity is an overstated stock position; a misread *saving*
ends up in a board pack.
"""
from .provenance import (  # noqa: F401
    DERIVED, KNOWN, MEASURED, SIMULATED, Figure, ProvenanceError, combine,
    derive, measured, simulated,
)
from .scenario import ScenarioError, ScenarioInputs, ScenarioOutputs  # noqa: F401
from .scenario import compute as compute_scenario  # noqa: F401
from .stock import (  # noqa: F401
    CROSS_CPSE_STOCK_FOUND, DEMAND_AGGREGATION_CANDIDATE, INTER, INTRA,
    NO_CROSS_CPSE_STOCK, OPPORTUNITY_DETECTED, UNRESOLVED_CASE, Availability,
    Holding, availability,
)
