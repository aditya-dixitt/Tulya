"""Phase 7: analytics, procurement and impact.

No database, no network, no model.

The tests that matter most are the provenance ones. The project's risk table
names "simulated quantities get quoted as measured savings" as a live danger,
and the defence is that MEASURED cannot be reached from SIMULATED by any route
this package offers.
"""
from __future__ import annotations

import pytest

from app.analytics import (
    CROSS_CPSE_STOCK_FOUND, DERIVED, MEASURED, NO_CROSS_CPSE_STOCK,
    OPPORTUNITY_DETECTED, SIMULATED, UNRESOLVED_CASE, Figure, Holding,
    ProvenanceError, ScenarioError, ScenarioInputs, availability, combine,
    compute_scenario, derive, measured, simulated,
)


# --------------------------------------------------------------------------
# provenance: the guard
# --------------------------------------------------------------------------
def test_a_figure_cannot_exist_without_a_basis():
    with pytest.raises(ProvenanceError) as exc:
        Figure(42.0, SIMULATED, "")
    assert "say where it came from" in str(exc.value)


def test_a_figure_cannot_carry_an_unknown_provenance():
    with pytest.raises(ProvenanceError):
        Figure(42.0, "PROBABLY_FINE", "a basis")


def test_one_simulated_input_simulates_the_whole_aggregate():
    assert combine(MEASURED, MEASURED, SIMULATED) == SIMULATED
    assert combine(MEASURED, DERIVED) == DERIVED
    assert combine(MEASURED, MEASURED) == MEASURED


def test_measured_cannot_be_manufactured_from_simulated_inputs():
    """The tempting mistake is one aggregation step away from the honest label."""
    sim = simulated(100.0, "from the benchmark generator")
    out = derive(100.0, "passed through", sim)
    assert out.provenance == SIMULATED
    assert out.is_measured is False
    assert out.quotable_as_saving is False


def test_deriving_from_measured_inputs_is_derived_not_measured():
    a = measured(10.0, "qty column of the source extract")
    b = measured(5.0, "qty column of the source extract")
    assert derive(15.0, "a + b", a, b).provenance == DERIVED


def test_only_an_observed_figure_may_be_quoted_as_a_saving():
    assert measured(1.0, "observed").quotable_as_saving is True
    assert derive(1.0, "computed", measured(1.0, "observed")).quotable_as_saving is False
    assert simulated(1.0, "generated").quotable_as_saving is False


def test_a_derived_figure_must_name_its_inputs():
    with pytest.raises(ProvenanceError) as exc:
        derive(1.0, "out of thin air")
    assert "assertion rather than a consequence" in str(exc.value)


def test_a_figure_renders_its_basis_when_printed():
    assert "benchmark" in str(simulated(5.0, "from the benchmark generator"))


# --------------------------------------------------------------------------
# availability
# --------------------------------------------------------------------------
def _h(rid, cpse, qty, status="CONFIRMED", uv=100.0):
    return Holding(record_id=rid, cpse=cpse, qty=qty, unit_value=uv,
                   link_status=status)


def test_a_cpse_is_never_told_to_source_from_itself():
    a = availability(100, [_h(1, "IOCL", 500), _h(2, "BPCL", 80)],
                     requesting_cpse="IOCL")
    assert a.available.value == 80
    assert a.contributing_cpses == ("BPCL",)


def test_full_coverage_is_reported_as_stock_found():
    a = availability(100, [_h(1, "BPCL", 400)], requesting_cpse="IOCL")
    assert a.signal == CROSS_CPSE_STOCK_FOUND
    assert a.coverage.value == 1.0
    assert a.shortfall.value == 0.0


def test_coverage_is_capped_at_one_to_match_the_check_constraint():
    a = availability(10, [_h(1, "BPCL", 1000)], requesting_cpse="IOCL")
    assert 0.0 <= a.coverage.value <= 1.0


def test_partial_coverage_is_an_opportunity_not_a_solution():
    a = availability(100, [_h(1, "BPCL", 40)], requesting_cpse="IOCL")
    assert a.signal == OPPORTUNITY_DETECTED
    assert a.coverage.value == pytest.approx(0.4)
    assert a.shortfall.value == 60


def test_no_confirmed_stock_anywhere_says_so_plainly():
    a = availability(100, [_h(1, "IOCL", 900)], requesting_cpse="IOCL")
    assert a.signal == NO_CROSS_CPSE_STOCK
    assert a.available.value == 0


def test_a_provisional_mapping_is_reported_but_does_not_authorise_a_transfer():
    """It is in the group because the group agreed, not because it was verified."""
    a = availability(100, [_h(1, "BPCL", 500, status="PROVISIONAL")],
                     requesting_cpse="IOCL")
    assert a.available.value == 0
    assert a.reported_provisional.value == 500
    assert a.signal == NO_CROSS_CPSE_STOCK
    assert "would need confirming first" in a.note


def test_a_withdrawn_mapping_contributes_nothing_at_all():
    a = availability(100, [_h(1, "BPCL", 500, status="WITHDRAWN")],
                     requesting_cpse="IOCL")
    assert a.available.value == 0 and a.reported_provisional.value == 0


def test_an_unresolved_identity_produces_no_recommendation():
    a = availability(100, [_h(1, "BPCL", 500)], requesting_cpse="IOCL",
                     identity_resolved=False)
    assert a.signal == UNRESOLVED_CASE
    assert "no sourcing recommendation" in a.note
    assert a.available.value == 500          # still reported, for context


def test_the_best_source_is_the_largest_confirmed_holding_deterministically():
    a = availability(100, [_h(3, "BPCL", 50), _h(1, "HPCL", 200), _h(2, "GAIL", 200)],
                     requesting_cpse="IOCL")
    assert a.best_source_record_id == 1      # tie on qty, lowest record id wins


def test_zero_demand_is_handled_rather_than_dividing_by_it():
    a = availability(0, [_h(1, "BPCL", 50)], requesting_cpse="IOCL")
    assert a.coverage.value == 0.0
    assert "undefined" in a.coverage.basis


def test_a_negative_requirement_is_refused():
    with pytest.raises(ValueError):
        availability(-5, [], requesting_cpse="IOCL")


def test_every_availability_number_carries_its_basis():
    a = availability(100, [_h(1, "BPCL", 40)], requesting_cpse="IOCL")
    for f in (a.required, a.available, a.coverage, a.shortfall,
              a.reported_provisional):
        assert f.basis.strip()
        assert f.provenance in (MEASURED, DERIVED, SIMULATED)


def test_the_opportunity_row_carries_provenance_and_basis():
    """ProcurementOpportunity has both as NOT NULL columns."""
    row = availability(100, [_h(1, "BPCL", 40)], requesting_cpse="IOCL") \
        .as_opportunity_row(identity_id=3, requesting_cpse_id=9)
    assert row["provenance"] and row["basis"]
    assert 0.0 <= row["coverage"] <= 1.0


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------
def _inputs(**kw):
    base = dict(identity_id=1, participating_cpses=("IOCL", "BPCL"),
                required_qty=100.0, demand_multiplier=1.0)
    base.update(kw)
    return ScenarioInputs(**base)


def test_pooling_adds_up_confirmed_stock_across_participants():
    out = compute_scenario(_inputs(), [_h(1, "IOCL", 60), _h(2, "BPCL", 30)])
    assert out.combined_stock.value == 90
    assert out.coverage.value == pytest.approx(0.9)
    assert out.procurement_requirement.value == 10
    assert out.surplus.value == 0


def test_a_non_participating_cpse_is_excluded():
    out = compute_scenario(_inputs(), [_h(1, "IOCL", 60), _h(9, "HPCL", 500)])
    assert out.combined_stock.value == 60


def test_the_demand_multiplier_scales_demand_not_stock():
    out = compute_scenario(_inputs(demand_multiplier=2.0), [_h(1, "IOCL", 100)])
    assert out.demand.value == 200
    assert out.combined_stock.value == 100
    assert out.coverage.value == pytest.approx(0.5)


def test_surplus_and_requirement_are_never_both_positive():
    for stock in (10, 100, 250):
        out = compute_scenario(_inputs(), [_h(1, "IOCL", stock)])
        assert out.surplus.value == 0 or out.procurement_requirement.value == 0


def test_aggregation_is_only_a_candidate_when_pooling_could_actually_help():
    short = compute_scenario(_inputs(), [_h(1, "IOCL", 10)])
    assert short.aggregation_opportunity is True
    covered = compute_scenario(_inputs(), [_h(1, "IOCL", 500)])
    assert covered.aggregation_opportunity is False
    alone = compute_scenario(_inputs(participating_cpses=("IOCL",)), [_h(1, "IOCL", 1)])
    assert alone.aggregation_opportunity is False


def test_provisional_stock_is_excluded_from_pooling_and_reported():
    out = compute_scenario(_inputs(),
                           [_h(1, "IOCL", 60), _h(2, "BPCL", 40, status="PROVISIONAL")])
    assert out.combined_stock.value == 60
    assert out.excluded_provisional.value == 40


def test_an_unresolved_identity_cannot_be_modelled_at_all():
    with pytest.raises(ScenarioError) as exc:
        compute_scenario(_inputs(), [_h(1, "IOCL", 60)], identity_resolved=False)
    assert "nobody has agreed exists" in str(exc.value)


@pytest.mark.parametrize("bad", [
    dict(participating_cpses=()),
    dict(participating_cpses=("IOCL", "IOCL")),
    dict(demand_multiplier=0),
    dict(demand_multiplier=-1),
    dict(required_qty=-5),
])
def test_inputs_that_cannot_produce_an_honest_scenario_are_refused(bad):
    with pytest.raises(ScenarioError):
        _inputs(**bad)


def test_the_scenario_produces_no_money_figure():
    """A misread quantity overstates stock; a misread saving reaches a board pack."""
    out = compute_scenario(_inputs(), [_h(1, "IOCL", 60, uv=9999.0)])
    blob = out.as_dict()
    for key in ("saving", "savings", "value", "inr", "rupees", "cost"):
        assert key not in {k.lower() for k in blob}


def test_the_scenario_is_labelled_simulated_end_to_end():
    out = compute_scenario(_inputs(), [_h(1, "IOCL", 60)])
    assert out.provenance == SIMULATED
    assert "not from any CPSE ERP" in out.basis


def test_the_scenario_row_carries_provenance_and_basis():
    """ImpactScenario has both as NOT NULL columns."""
    inputs = _inputs()
    row = compute_scenario(inputs, [_h(1, "IOCL", 60)]).as_scenario_row(inputs)
    assert row["provenance"] == SIMULATED and row["basis"]
    assert row["outputs"]["coverage"]["basis"]


def test_consolidation_counts_the_legacy_records_that_become_one_code():
    out = compute_scenario(_inputs(), [_h(1, "IOCL", 10), _h(2, "IOCL", 5),
                                       _h(3, "BPCL", 20)])
    assert out.legacy_codes_consolidated.value == 3
