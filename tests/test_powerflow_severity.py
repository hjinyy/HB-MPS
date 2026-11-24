"""Behavior and saved-output checks for the separate dynamic AC experiment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandapower as pp

from emergency_dispatch import (
    ESS_CAPACITY,
    ESS_EFFICIENCY,
    H2_CAPACITY_KG,
    HFC_OUTPUT_KWH,
    P2G_KWH_PER_KG,
)
from powerflow_validation import (
    INDUSTRIAL_BUS_NUMBERS,
    OUTPUT_DIR,
    build_network,
    set_operating_point,
    solve_network,
)
from severity_ac_dispatch import dispatch_hour, required_supply_mw, severity_scores
from severity_fleet import ESS_MIN_SOC, FLEET_SIZE, FleetState


def test_severity_uses_local_demand_and_all_bus_voltage_scale() -> None:
    # Given equal local excess at two candidates and a larger deficit elsewhere.
    demand = np.zeros(len(INDUSTRIAL_BUS_NUMBERS))
    demand[:2] = 0.1
    voltage = np.ones(33)
    voltage[17] = 0.94  # Industrial Bus 18.
    voltage[16] = 0.92  # Industrial Bus 17.
    voltage[1] = 0.90  # A noncandidate bus sets the global scale.

    # When demand and voltage violation each receive a half weight.
    scores = severity_scores(demand, voltage)

    # Then the weaker candidate is ranked first, without ignoring Bus 2.
    assert scores[1] > scores[0] > scores[2]
    assert np.isclose(scores[1], 0.5 + 0.5 * (0.03 / 0.05))


def test_voltage_only_event_recomputes_supply_and_preserves_resources() -> None:
    # Given an AC feeder with undervoltage but no industrial-load excess.
    net = build_network()
    set_operating_point(net, 1.0, 1.0, 1.0, 0.0, 0.0)
    baseline, _ = solve_network(net)
    assert baseline.min() < 0.95
    generators = np.array(
        [
            pp.create_sgen(net, bus - 1, p_mw=0.0, q_mvar=0.0)
            for bus in INDUSTRIAL_BUS_NUMBERS
        ]
    )
    state = FleetState.initial()
    initial_h2 = sum(state.h2_kg)

    # When the independent five-truck rule assesses AC voltage support.
    result = dispatch_hour(net, baseline, np.zeros(9), generators, state, 0.00006)

    # Then it dispatches despite zero local excess and pays for fuel/ESS use.
    assert result.hfc_kwh > 0
    assert result.load_response_mw == 0
    assert result.voltage_only_mw > 0
    assert np.isclose(
        result.injections_mw.sum(), (result.hfc_kwh + result.ess_kwh) * 0.00006
    )
    assert (
        np.maximum(0.95 - result.supported_voltage, 0).sum()
        < np.maximum(0.95 - baseline, 0).sum()
    )
    assert np.isclose(initial_h2 - sum(state.h2_kg), result.h2_consumed_kg)
    assert state.soc >= ESS_MIN_SOC - 1e-9
    assert all(
        vehicle.bus in INDUSTRIAL_BUS_NUMBERS or vehicle.bus is None
        for vehicle in result.trucks
    )


def test_ac_voltage_need_and_local_excess_are_not_added() -> None:
    # Given a feeder just below 0.95 p.u. with a candidate Bus 18 connection.
    net = build_network()
    low, high = 0.2, 1.0
    for _ in range(22):
        midpoint = (low + high) / 2
        set_operating_point(net, midpoint, midpoint, midpoint, 0.0, 0.0)
        voltage, _ = solve_network(net)
        if voltage.min() < 0.9499:
            high = midpoint
        else:
            low = midpoint
    set_operating_point(net, high, high, high, 0.0, 0.0)
    baseline, _ = solve_network(net)
    generator = pp.create_sgen(net, 17, p_mw=0.0, q_mvar=0.0)

    # When AC voltage-only need and a larger local excess are each evaluated.
    voltage_need = required_supply_mw(net, generator, 0.0, 0.5, baseline)
    combined_need = required_supply_mw(net, generator, 0.1, 0.5, baseline)

    # Then the dispatch takes their maximum, not their sum, and probes revert.
    assert 0 < voltage_need < 0.1
    assert np.isclose(combined_need, 0.1)
    assert net.sgen.at[generator, "p_mw"] == 0.0


def test_saved_hourly_bus_and_vehicle_energy_balances() -> None:
    # Given the generated 168-hour CSV outputs for both requested α cases.
    hourly = pd.read_csv(OUTPUT_DIR / "fig15_severity_dynamic_hourly.csv")
    buses = pd.read_csv(OUTPUT_DIR / "fig15_severity_dynamic_bus_hourly.csv")
    trucks = pd.read_csv(OUTPUT_DIR / "fig15_severity_dynamic_trucks.csv")
    comparison = pd.read_csv(OUTPUT_DIR / "fig15_strategy_comparison.csv")

    # When the rows are grouped at each real experiment hour.
    groups = hourly.groupby(["alpha", "t"], sort=False)

    # Then supply, injection, trigger and resource paths agree without P1 reuse.
    assert len(hourly) == 2 * 168
    assert len(buses) == 2 * 168 * 33
    assert len(trucks) == 2 * 168 * FLEET_SIZE
    assert len(comparison) == 2 * 3
    for (alpha, t), group in groups:
        row = group.iloc[0]
        bus_hour = buses.loc[buses.alpha.eq(alpha) & buses.t.eq(t)]
        truck_hour = trucks.loc[trucks.alpha.eq(alpha) & trucks.t.eq(t)]
        assert np.isclose(bus_hour.injection_mw.sum(), row.emergency_supply_mw)
        assert np.isclose(truck_hour.hfc_kwh.sum(), row.hfc_kwh)
        assert np.isclose(truck_hour.ess_kwh.sum(), row.ess_emergency_kwh)
        assert np.isclose(bus_hour.residual_excess_mw.sum(), row.residual_excess_mw)
        assert row.supply_active <= row.mode2_trigger
        assert row.soc_end_pct >= ESS_MIN_SOC * 100 - 1e-8
        assert (truck_hour.h2_end_kg >= -1e-8).all()
        assert np.isclose(
            row.emergency_supply_mw, row.load_response_mw + row.voltage_only_mw
        )
        assert np.isclose(
            row.fleet_h2_end_kg,
            row.fleet_h2_start_kg
            + row.h2_refilled_kg
            + row.pv_p2g_kwh / P2G_KWH_PER_KG
            - row.h2_consumed_kg,
            atol=1e-7,
        )
        soc_end_kwh = (
            row.soc_start_pct / 100 * ESS_CAPACITY
            - row.ess_withdrawal_kwh
            - row.phase1_ess_kwh / ESS_EFFICIENCY
            + (row.pv_ess_charge_kwh + row.grid_ess_charge_kwh) * ESS_EFFICIENCY
        )
        assert np.isclose(row.soc_end_pct / 100 * ESS_CAPACITY, soc_end_kwh)
        assert (truck_hour.hfc_kwh <= HFC_OUTPUT_KWH + 1e-7).all()
        assert (truck_hour.h2_end_kg <= H2_CAPACITY_KG + 1e-7).all()
    candidates = buses.loc[buses.industrial_candidate]
    for (alpha, bus), rows in candidates.groupby(["alpha", "bus"]):
        assert len(rows) == 168
        assert np.isclose(
            rows.threshold_mw.iloc[0], alpha * rows.industrial_load_mw.mean()
        )
        assert np.allclose(
            rows.excess_mw, np.maximum(rows.industrial_load_mw - rows.threshold_mw, 0)
        )
    dynamic = comparison.loc[comparison.strategy.eq("Dynamic bus-level")]
    assert (dynamic.actual_supply_hours > 0).all()
    assert (dynamic.voltage_only_response_hours > 0).all()
    assert (
        dynamic.total_mwh_raw
        > comparison.loc[
            comparison.strategy.eq("Existing Figure 15")
        ].total_mwh_raw.to_numpy()
    ).all()
