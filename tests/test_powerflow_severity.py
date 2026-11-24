"""Behavior and saved-output checks for the separate dynamic AC experiment."""

from __future__ import annotations

import numpy as np
import pandapower as pp
import pandas as pd

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
from severity_ac_dispatch import dispatch_hour, severity_scores
from severity_fleet import ESS_MIN_SOC, FLEET_SIZE, FleetState


def test_severity_uses_industrial_demand_and_voltage_scale() -> None:
    # Given equal industrial excess at two candidates and a deficit elsewhere.
    demand = np.zeros(len(INDUSTRIAL_BUS_NUMBERS))
    demand[:2] = 0.1
    voltage = np.ones(33)
    voltage[17] = 0.94  # Industrial Bus 18.
    voltage[16] = 0.92  # Industrial Bus 17.
    voltage[1] = 0.90  # Residential undervoltage cannot set Mode 2 priority.

    # When demand and voltage violation each receive a half weight.
    scores = severity_scores(demand, voltage)

    # Then only the industrial candidates set the dispatch priority.
    assert scores[1] > scores[0] > scores[2]
    assert np.isclose(scores[1], 1.0)


def test_voltage_only_event_does_not_dispatch() -> None:
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

    # When voltage is low but no industrial bus exceeds its load threshold.
    result = dispatch_hour(net, baseline, np.zeros(9), generators, state, 0.00006)

    # Then Mode 2 uses no assets and the voltage is only evaluated.
    assert result.hfc_kwh == 0
    assert result.ess_kwh == 0
    assert result.load_response_mw == 0
    assert np.allclose(result.injections_mw, 0)
    assert np.allclose(result.supported_voltage, baseline)
    assert np.isclose(initial_h2, sum(state.h2_kg))
    assert state.soc >= ESS_MIN_SOC - 1e-9
    assert all(
        vehicle.bus in INDUSTRIAL_BUS_NUMBERS or vehicle.bus is None
        for vehicle in result.trucks
    )


def test_emergency_supply_never_exceeds_local_excess() -> None:
    # Given a low-voltage feeder with one industrial load excess.
    net = build_network()
    set_operating_point(net, 1.0, 1.0, 1.0, 0.0, 0.0)
    baseline, _ = solve_network(net)
    generators = np.array(
        [
            pp.create_sgen(net, bus - 1, p_mw=0.0, q_mvar=0.0)
            for bus in INDUSTRIAL_BUS_NUMBERS
        ]
    )
    demand = np.zeros(9)
    demand[0] = 0.02

    # When the fleet supplies the sole load-excess bus.
    result = dispatch_hour(
        net, baseline, demand, generators, FleetState.initial(), 0.00006
    )

    # Then the output is limited by the shortage, regardless of low voltage.
    assert 0 < result.injections_mw[0] <= demand[0] + 1e-9
    assert np.allclose(result.injections_mw[1:], 0)
    assert np.isclose(result.injections_mw.sum(), result.load_response_mw)


def test_saved_hourly_bus_and_vehicle_energy_balances() -> None:
    # Given the generated 168-hour CSV outputs for both requested α cases.
    hourly = pd.read_csv(OUTPUT_DIR / "fig13_severity_dynamic_hourly.csv")
    buses = pd.read_csv(OUTPUT_DIR / "fig13_severity_dynamic_bus_hourly.csv")
    trucks = pd.read_csv(OUTPUT_DIR / "fig13_severity_dynamic_trucks.csv")
    comparison = pd.read_csv(OUTPUT_DIR / "fig13_strategy_comparison.csv")

    # When the rows are grouped at each real experiment hour.
    groups = hourly.groupby(["alpha", "t"], sort=False)

    # Then supply, injection, trigger and resource paths agree without P1 reuse.
    assert len(hourly) == 2 * 168
    assert len(buses) == 2 * 168 * 33
    assert len(trucks) == 2 * 168 * FLEET_SIZE
    assert len(comparison) == 2 * 5
    for (alpha, t), group in groups:
        row = group.iloc[0]
        bus_hour = buses.loc[buses.alpha.eq(alpha) & buses.t.eq(t)]
        truck_hour = trucks.loc[trucks.alpha.eq(alpha) & trucks.t.eq(t)]
        assert np.isclose(bus_hour.mode2_injection_mw.sum(), row.emergency_supply_mw)
        assert np.isclose(bus_hour.mode1_injection_mw.sum(), row.mode1_supply_mw)
        assert np.isclose(
            bus_hour.charging_mw.sum(), row.pv_charging_mw + row.grid_charging_mw
        )
        assert np.isclose(bus_hour.net_hbmps_mw.sum(), row.net_hbmps_mw)
        assert np.isclose(truck_hour.hfc_kwh.sum(), row.hfc_kwh)
        assert np.isclose(truck_hour.ess_kwh.sum(), row.ess_emergency_kwh)
        assert np.isclose(truck_hour.mode1_ess_kwh.sum(), row.phase1_ess_kwh)
        assert np.isclose(bus_hour.residual_excess_mw.sum(), row.residual_excess_mw)
        assert row.supply_active <= row.mode2_trigger
        assert not (row.mode1_active and row.mode2_trigger)
        industrial = bus_hour.loc[bus_hour.bus_type.eq("Industrial")]
        assert row.mode2_trigger == bool(industrial.excess_mw.gt(1e-9).any())
        assert (industrial.mode2_injection_mw <= industrial.excess_mw + 1e-8).all()
        if row.mode1_active:
            receiving = bus_hour.loc[bus_hour.bus.eq(row.mode1_bus)].iloc[0]
            assert receiving.bus_type == "Residential"
            assert receiving.mode1_injection_mw > 0
            assert receiving.supported_voltage_pu > receiving.baseline_voltage_pu
        assert np.isclose(
            bus_hour.loc[bus_hour.bus.eq(7), "charging_mw"].iloc[0],
            row.pv_charging_mw,
        )
        assert np.isclose(
            bus_hour.loc[bus_hour.bus.eq(9), "charging_mw"].iloc[0],
            row.grid_charging_mw,
        )
        if row.pv_charging_mw > 0:
            pv_bus = bus_hour.loc[bus_hour.bus.eq(7)].iloc[0]
            assert pv_bus.supported_voltage_pu < pv_bus.baseline_voltage_pu
        if row.grid_charging_mw > 0:
            grid_bus = bus_hour.loc[bus_hour.bus.eq(9)].iloc[0]
            assert grid_bus.supported_voltage_pu < grid_bus.baseline_voltage_pu
        assert row.soc_end_pct >= ESS_MIN_SOC * 100 - 1e-8
        assert (truck_hour.h2_end_kg >= -1e-8).all()
        assert np.isclose(row.emergency_supply_mw, row.load_response_mw)
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
    assert set(buses.bus_type) == {"Slack", "Industrial", "Residential"}
    assert buses.loc[
        buses.t.eq(0) & buses.alpha.eq(1.3), "bus_type"
    ].value_counts().to_dict() == {
        "Residential": 23,
        "Industrial": 9,
        "Slack": 1,
    }
    assert not hourly.mode1_active.eq(False).all()
    residential_undervoltage = hourly.vmin_baseline.lt(0.95) & ~hourly.mode2_trigger
    assert residential_undervoltage.any()
    assert (residential_undervoltage & hourly.mode1_active).any()
    for (alpha, bus), rows in candidates.groupby(["alpha", "bus"]):
        assert len(rows) == 168
        assert np.isclose(
            rows.threshold_mw.iloc[0], alpha * rows.industrial_load_mw.mean()
        )
        assert np.allclose(
            rows.excess_mw, np.maximum(rows.industrial_load_mw - rows.threshold_mw, 0)
        )
    dynamic = comparison.loc[comparison.strategy.eq("Dynamic bus-level")]
    binary_fixed = comparison.loc[comparison.strategy.eq("Fixed P1 dual-mode (binary)")]
    assert (dynamic.actual_supply_hours > 0).all()
    assert (dynamic.load_response_hours == dynamic.actual_supply_hours).all()
    assert (dynamic.mode1_hours > 0).all()
    assert (binary_fixed.mode1_hours > 0).all()
    assert np.allclose(
        dynamic.worst_baseline_voltage_pu,
        binary_fixed.worst_baseline_voltage_pu,
    )
    assert (dynamic.mode2_trigger_hours == dynamic.load_excess_trigger_hours).all()
    assert np.allclose(dynamic.load_response_mwh_ac, dynamic.ac_injection_mwh)
