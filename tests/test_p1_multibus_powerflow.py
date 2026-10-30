"""Unchanged P1 energy path and auditable two-bus AC injection checks."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

from emergency_dispatch import H2_CAPACITY_KG, HFC_OUTPUT_KWH, run_scenario
from emergency_dispatch_model import Scenario, Strategy
from hb_inputs import INPUT, load_hours
from p1_multibus_dispatch import allocate_p1_supply
from powerflow_validation import (
    build_network,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def read_csv(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(newline="") as source:
        return list(csv.DictReader(source))


def test_truck_replay_preserves_original_p1_energy_and_inventories() -> None:
    hours = load_hours(INPUT)
    net = build_network()
    p18 = float(net.load.loc[net.load.bus.eq(17), "p_mw"].sum())
    p33 = float(net.load.loc[net.load.bus.eq(32), "p_mw"].sum())
    assert math.isclose(p18 / (p18 + p33), 0.6)
    for alpha in (1.3, 1.5, 1.8):
        original = run_scenario(hours, Scenario(alpha, 5, Strategy.P1))
        injection, trucks = allocate_p1_supply(hours, original, p18 / (p18 + p33))
        assert len(injection) == 168
        assert len(trucks) == 168 * 5
        for t, step in enumerate(original.steps):
            allocation = injection[t]
            vehicles = trucks[t * 5 : (t + 1) * 5]
            assert all(vehicle.bus in (18, 33) for vehicle in vehicles)
            assert vehicles[0].bus == 18
            assert all(
                0 <= vehicle.hfc_kwh <= HFC_OUTPUT_KWH + 1e-8 for vehicle in vehicles
            )
            assert all(
                0 <= vehicle.h2_end_kg <= H2_CAPACITY_KG + 1e-8 for vehicle in vehicles
            )
            assert math.isclose(
                sum(vehicle.hfc_kwh for vehicle in vehicles if vehicle.bus == 18),
                allocation.hfc18_kwh,
                abs_tol=1e-7,
            )
            assert math.isclose(
                sum(vehicle.hfc_kwh for vehicle in vehicles if vehicle.bus == 33),
                allocation.hfc33_kwh,
                abs_tol=1e-7,
            )
            assert math.isclose(allocation.ess18_kwh, step.ess_emergency_kwh)
            assert math.isclose(
                allocation.total_kwh, step.hfc_kwh + step.ess_emergency_kwh
            )
            assert math.isclose(
                sum(vehicle.h2_end_kg for vehicle in vehicles), step.h2_end_kg
            )


def test_saved_ac_injection_and_figure_csvs_close_to_p1() -> None:
    pf = read_csv("pf_results.csv")
    injection = read_csv("p1_multibus_hourly_injection.csv")
    trucks = read_csv("p1_multibus_vehicle_dispatch.csv")
    heatmap = read_csv("powerflow_voltage_by_bus_hour.csv")
    assert len(pf) == 3 * 168
    assert len(injection) == 3 * 168
    assert len(trucks) == 3 * 168 * 5
    assert len(heatmap) == 33 * 168
    per_hour = {(row["alpha"], int(row["t"])): row for row in injection}
    by_hour: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for vehicle in trucks:
        by_hour[vehicle["alpha"], int(vehicle["t"])].append(vehicle)
    for row in pf:
        key = row["alpha"], int(row["t"])
        item = per_hour[key]
        vehicles = by_hour[key]
        assert len(vehicles) == 5
        assert math.isclose(
            float(row["hfc_supplied_kwh"]),
            float(item["hfc18_kwh"]) + float(item["hfc33_kwh"]),
            abs_tol=1e-7,
        )
        assert math.isclose(float(row["ess_emergency_kwh"]), float(item["ess18_kwh"]))
        assert math.isclose(
            float(row["hbmps_mw"]),
            float(row["hbmps18_mw"]) + float(row["hbmps33_mw"]),
            abs_tol=1e-10,
        )
        assert math.isfinite(float(row["vmin_hbmps"]))
        assert math.isfinite(float(row["ploss_hbmps_mw"]))
    assert any(row["bus"] == "33" and float(row["hfc_kwh"]) > 0 for row in trucks)
