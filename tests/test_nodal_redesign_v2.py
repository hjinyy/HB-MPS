"""Regression, physical-balance and Figure 13 checks for the isolated redesign."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np
import pandapower as pp
import pandapower.networks as nw
import pandas as pd
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from nodal_redesign_v2.experiment import (
    CASES,
    OUTPUT_DIR,
    _ratings,
    _scale,
    _set_loads,
)
from nodal_redesign_v2.dispatch import dispatch_hour, severity_scores
from nodal_redesign_v2.plots import _draw_deployment, _draw_operation_timeline
from powerflow_validation import INPUT_PATH, build_network, load_profiles, solve_network
from severity_fleet import FleetState


def _directory(case: str, alpha: float) -> Path:
    return OUTPUT_DIR / f"{case}_alpha_{str(alpha).replace('.', '_')}"


def test_benchmark_ratings_and_common_scale_are_unchanged() -> None:
    network = nw.case33bw()
    frame = load_profiles(INPUT_PATH)
    assert len(CASES[0].industrial_buses) == 9
    assert len(CASES[0].residential_buses) == 23
    assert len(CASES[1].industrial_buses) == len(CASES[2].industrial_buses) == 19
    assert len(CASES[1].residential_buses) == len(CASES[2].residential_buses) == 13
    assert set(CASES[2].industrial_buses).isdisjoint(CASES[2].residential_buses)
    assert set(CASES[2].industrial_buses) | set(CASES[2].residential_buses) == set(range(2, 34))
    assert (7, 9, 22) == tuple(bus for bus in (7, 9, 22) if bus in CASES[2].residential_buses)
    assert np.allclose(_ratings(CASES[0], network), (1.010, 2.705, 3.715))
    assert np.allclose(_ratings(CASES[2], network), (2.510, 1.205, 3.715))
    assert np.isclose(_scale(CASES[0], frame, _ratings(CASES[0], network)) * 100_000, 6.1855807743)
    assert np.isclose(_scale(CASES[1], frame, _ratings(CASES[1], network)) * 100_000, 15.3720868747)
    assert np.isclose(_scale(CASES[2], frame, _ratings(CASES[2], network)) * 100_000, 15.4289012351)


def test_new_load_types_preserve_benchmark_pq_and_topology() -> None:
    network = build_network()
    reference = nw.case33bw()
    original_pq = network.load[["p_mw", "q_mvar"]].copy()
    _set_loads(network, tuple(network.load.index), CASES[2].industrial_buses,
               industrial_fraction=0.7, residential_fraction=0.4, pv_mw=0.2)
    assert np.array_equal(network.load[["p_mw", "q_mvar"]], original_pq)
    assert np.array_equal(network.line[["from_bus", "to_bus", "r_ohm_per_km", "x_ohm_per_km"]],
                          reference.line[["from_bus", "to_bus", "r_ohm_per_km", "x_ohm_per_km"]])
    assert np.allclose(network.load.loc[network.load.bus.eq(6), "scaling"], 0.4)
    assert np.allclose(network.load.loc[network.load.bus.eq(13), "scaling"], 0.7)


def test_nineteen_bus_dispatch_uses_excess_and_rechecks_ac() -> None:
    buses = CASES[2].industrial_buses
    demand = np.zeros(len(buses))
    demand[buses.index(14)] = demand[buses.index(18)] = 0.1
    voltage = np.ones(33)
    voltage[1] = 0.8  # Residential Bus 2 cannot set the emergency priority.
    voltage[17] = 0.92
    scores = severity_scores(demand, voltage, buses)
    assert scores[buses.index(18)] > scores[buses.index(14)]
    network = build_network()
    _set_loads(network, tuple(network.load.index), buses, 1.0, 1.0, 0.0)
    baseline, _ = solve_network(network)
    generators = np.array([
        pp.create_sgen(network, bus - 1, p_mw=0.0, q_mvar=0.0)
        for bus in buses
    ])
    state = FleetState.initial()
    result = dispatch_hour(network, baseline, demand, generators, state,
                           0.0001542890123505551, buses)
    assert set(vehicle.bus for vehicle in result.trucks if vehicle.bus is not None) <= set(buses)
    assert np.isclose(result.injections_mw.sum() + result.remaining_excess_mw.sum(), demand.sum())
    assert np.all(result.injections_mw <= demand + 1e-8)
    assert np.isfinite(result.supported_voltage).all()


@pytest.mark.parametrize("case", ("C1", "C2", "C3"))
@pytest.mark.parametrize("alpha", (1.3, 1.5))
def test_saved_hourly_bus_truck_and_energy_balances(case: str, alpha: float) -> None:
    directory = _directory(case, alpha)
    hourly = pd.read_csv(directory / "hourly.csv")
    buses = pd.read_csv(directory / "bus_hourly.csv")
    trucks = pd.read_csv(directory / "trucks.csv")
    metrics = pd.read_csv(OUTPUT_DIR / "case_metrics.csv")
    scale = float(metrics.loc[metrics.case_id.eq(case) & metrics.alpha.eq(alpha), "hb_mps_scale_pct"].iloc[0]) / 100_000
    assert len(hourly) == 168
    assert len(buses) == 168 * 33
    assert len(trucks) == 168 * 5
    assert all((directory / f"fig{number}_{stem}.png").exists() for number, stem in (
        (12, "ieee_33_bus_configuration"),
        (13, "operation_and_nodal_deployment"),
        (14, "nodal_voltage_analysis"),
    ))
    bus_groups = buses.groupby("t", sort=True)
    truck_groups = trucks.groupby("t", sort=True)
    for t, row in enumerate(hourly.itertuples(index=False)):
        bus_hour, truck_hour = bus_groups.get_group(t), truck_groups.get_group(t)
        assert np.isclose(row.bus_excess_mw, row.emergency_supply_mw + row.residual_excess_mw)
        assert np.isclose(bus_hour.mode2_injection_mw.sum(), row.emergency_supply_mw)
        assert np.isclose(bus_hour.mode1_injection_mw.sum(), row.mode1_supply_mw)
        assert np.isclose(bus_hour.net_hbmps_mw.sum(), row.net_hbmps_mw)
        assert np.isclose(truck_hour.hfc_kwh.sum(), row.hfc_kwh)
        assert np.isclose(truck_hour.ess_kwh.sum(), row.ess_emergency_kwh)
        assert np.isclose(row.emergency_supply_mw, (row.hfc_kwh + row.ess_emergency_kwh) * scale)
        assert row.mode2_trigger == bool(bus_hour.excess_mw.gt(1e-9).any())
        assert not (row.mode1_active and row.mode2_trigger)
        assert (truck_hour.h2_end_kg >= -1e-8).all()
        assert row.soc_end_pct >= 10 - 1e-8
    assert np.isfinite(buses[["baseline_voltage_pu", "supported_voltage_pu"]]).all().all()
    first = buses.loc[buses.t.eq(0)]
    assert first.bus_type.value_counts()["Industrial"] == (9 if case == "C1" else 19)
    assert first.bus_type.value_counts()["Residential"] == (23 if case == "C1" else 13)


def test_c1_reproduces_saved_legacy_nodal_experiment() -> None:
    legacy = pd.read_csv(Path("results/fig13_severity_dynamic_hourly.csv"))
    for alpha in (1.3, 1.5):
        old = legacy.loc[legacy.alpha.eq(alpha)].sort_values("t")
        new = pd.read_csv(_directory("C1", alpha) / "hourly.csv").sort_values("t")
        for field in (
            "mode2_trigger", "mode1_active", "hfc_kwh", "ess_emergency_kwh",
            "vmin_baseline", "vmin_supported", "line_loss_supported_mw",
        ):
            assert np.allclose(new[field], old[field]), field


def test_c2_c3_share_identical_load_baseline_and_detect_pv_mismatch() -> None:
    metrics = pd.read_csv(OUTPUT_DIR / "case_metrics.csv")
    for alpha in (1.3, 1.5):
        a = pd.read_csv(_directory("C2", alpha) / "bus_hourly.csv")
        b = pd.read_csv(_directory("C3", alpha) / "bus_hourly.csv")
        assert np.allclose(a.baseline_voltage_pu, b.baseline_voltage_pu)
        for case in ("C2", "C3"):
            row = metrics.loc[metrics.case_id.eq(case) & metrics.alpha.eq(alpha)].iloc[0]
            assert row.pv_surplus_shortfall_hours > 0
            assert row.pv_surplus_shortfall_mwh > 0
            assert row.network_pv_surplus_mwh == 0


def test_figure13_hides_unavailable_row_only_when_empty_and_uses_two_legend_rows() -> None:
    for case, expected_rows in (("C1", 3), ("C3", 2)):
        hourly = pd.read_csv(_directory(case, 1.3) / "hourly.csv")
        trucks = pd.read_csv(_directory(case, 1.3) / "trucks.csv")
        run = SimpleNamespace(result=SimpleNamespace(hourly=hourly, trucks=trucks))
        fig, (timeline, deployment) = plt.subplots(2, 1)
        _draw_operation_timeline(timeline, run)
        _draw_deployment(deployment, run)
        assert len(timeline.get_yticklabels()) == expected_rows
        legend = deployment.get_legend()
        assert legend is not None
        count = len(legend.get_texts())
        assert (count + legend._ncols - 1) // legend._ncols == 2
        plt.close(fig)
