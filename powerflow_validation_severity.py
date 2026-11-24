#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["numpy", "pandas", "matplotlib", "pandapower"]
# ///

# ─── How to run ───
# 1. Install uv (if needed): curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: uv run powerflow_validation_severity.py
# 3. Or: chmod +x powerflow_validation_severity.py && ./powerflow_validation_severity.py
# ──────────────────

"""Independent bus-level dynamic HB-MPS dispatch and IEEE 33-bus validation.

This replaces only the additional Fig. 15(1)/(2) experiment. The original
Figure 15 and operational P1 simulation are read but never modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandapower as pp
import pandas as pd

from hb_inputs import INPUT, load_hours
from powerflow_plot_severity import save_severity_figure
from powerflow_validation import (
    INDUSTRIAL_BUS_NUMBERS,
    INDUSTRIAL_COLUMN,
    INPUT_PATH,
    MIN_VOLTAGE_PU,
    OUTPUT_DIR,
    PV_BUS_NUMBER,
    PV_COLUMN,
    PV_PENETRATION,
    RESIDENTIAL_COLUMN,
    build_network,
    load_profiles,
    profile_fraction,
    set_operating_point,
    solve_network,
)
from severity_ac_dispatch import (
    BUS_INDICES,
    dispatch_hour,
)
from severity_fleet import (
    FLEET_SIZE,
    H2_CAPACITY_KG,
    FleetState,
    advance_idle,
    price_quantiles,
)

ALPHAS: Final = (1.3, 1.5)
SUMMARY_PATH: Final = OUTPUT_DIR / "FIG15_SEVERITY_DISPATCH_SUMMARY.md"
HOURLY_PATH: Final = OUTPUT_DIR / "fig15_severity_dynamic_hourly.csv"
BUS_PATH: Final = OUTPUT_DIR / "fig15_severity_dynamic_bus_hourly.csv"
TRUCK_PATH: Final = OUTPUT_DIR / "fig15_severity_dynamic_trucks.csv"
COMPARISON_PATH: Final = OUTPUT_DIR / "fig15_strategy_comparison.csv"


@dataclass(frozen=True, slots=True)
class SeverityResult:
    alpha: float
    hourly: pd.DataFrame
    buses: pd.DataFrame
    trucks: pd.DataFrame
    baseline_profiles: np.ndarray
    supported_profiles: np.ndarray
    worst_hour: int

    @property
    def baseline_minimum(self) -> np.ndarray:
        return self.baseline_profiles.min(axis=1)

    @property
    def supported_minimum(self) -> np.ndarray:
        return self.supported_profiles.min(axis=1)

    @property
    def active_hours(self) -> np.ndarray:
        return self.hourly["supply_active"].to_numpy(dtype=bool)

    @property
    def load_dispatch_hours(self) -> np.ndarray:
        return self.hourly["load_dispatch_active"].to_numpy(dtype=bool)

    @property
    def injection_buses(self) -> tuple[tuple[int, ...], ...]:
        rows = self.trucks.loc[
            self.trucks.bus.notna()
            & (
                self.trucks.hfc_kwh + self.trucks.ess_kwh + self.trucks.mode1_ess_kwh
            ).gt(0)
        ]
        return tuple(
            tuple(rows.loc[rows.t.eq(t), "bus"].astype(int))
            for t in range(len(self.hourly))
        )


def _bus_ratings(net: pp.pandapowerNet) -> np.ndarray:
    return np.array(
        [
            float(net.load.loc[net.load.bus.eq(bus - 1), "p_mw"].sum())
            for bus in INDUSTRIAL_BUS_NUMBERS
        ]
    )


def simulate(alpha: float) -> SeverityResult:
    """Recompute dispatch, SOC, LOH and sequential AC support for 168 hours."""
    frame = load_profiles(INPUT_PATH)
    hours = load_hours(INPUT)
    if len(frame) != 168 or len(hours) != len(frame):
        raise AssertionError("Dynamic experiment requires aligned 168-hour inputs")
    industrial_fraction = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential_fraction = profile_fraction(frame[RESIDENTIAL_COLUMN])
    pv_fraction = profile_fraction(frame[PV_COLUMN])
    baseline_net = build_network()
    support_net = build_network()
    bus_ratings = _bus_ratings(baseline_net)
    industrial_rating = float(bus_ratings.sum())
    industrial_indices = set(BUS_INDICES)
    residential_bus_numbers = tuple(
        sorted(
            int(bus) + 1
            for bus in baseline_net.load.bus.unique()
            if bus not in industrial_indices
        )
    )
    if len(residential_bus_numbers) != 23:
        raise AssertionError("Expected 9 industrial and 23 residential load buses")
    pv_rating = float(baseline_net.load.p_mw.sum()) * PV_PENETRATION
    raw_peak = float(frame[INDUSTRIAL_COLUMN].max())
    mw_per_raw_kwh = industrial_rating / raw_peak
    bus_loads = industrial_fraction[:, None] * bus_ratings[None, :]
    bus_thresholds = alpha * bus_loads.mean(axis=0)
    generators = np.array(
        [
            pp.create_sgen(
                support_net,
                bus - 1,
                p_mw=0.0,
                q_mvar=0.0,
                name=f"Dynamic-{bus}",
            )
            for bus in INDUSTRIAL_BUS_NUMBERS
        ]
    )
    mode1_generators = {
        bus: pp.create_sgen(
            support_net,
            bus - 1,
            p_mw=0.0,
            q_mvar=0.0,
            name=f"Mode1 residential-{bus}",
        )
        for bus in residential_bus_numbers
    }
    pv_charge_load = pp.create_load(
        support_net,
        PV_BUS_NUMBER - 1,
        p_mw=0.0,
        q_mvar=0.0,
        name="HB PV charging and P2G",
    )
    grid_charge_bus = 9
    grid_charge_load = pp.create_load(
        support_net,
        grid_charge_bus - 1,
        p_mw=0.0,
        q_mvar=0.0,
        name="HB grid charging depot",
    )
    state = FleetState.initial()
    high_lcoe, low_smp = price_quantiles(hours)
    hourly_rows: list[dict[str, float | int | str | bool]] = []
    bus_rows: list[dict[str, float | int | str | bool]] = []
    truck_rows: list[dict[str, float | int | str | bool | None]] = []
    baseline_profiles: list[np.ndarray] = []
    supported_profiles: list[np.ndarray] = []
    industrial_by_bus = {bus: index for index, bus in enumerate(INDUSTRIAL_BUS_NUMBERS)}

    for t, hour in enumerate(hours):
        operating_point = (
            industrial_fraction[t],
            residential_fraction[t],
            residential_fraction[t],
            pv_fraction[t] * pv_rating,
            0.0,
        )
        set_operating_point(baseline_net, *operating_point)
        set_operating_point(support_net, *operating_point)
        support_net.sgen.loc[generators, "p_mw"] = 0.0
        support_net.sgen.loc[list(mode1_generators.values()), "p_mw"] = 0.0
        support_net.load.loc[[pv_charge_load, grid_charge_load], "p_mw"] = 0.0
        support_net.load.loc[[pv_charge_load, grid_charge_load], "scaling"] = 1.0
        baseline_voltage, baseline_loss = solve_network(baseline_net)
        demand = np.maximum(bus_loads[t] - bus_thresholds, 0.0)
        load_trigger = bool(np.any(demand > 1e-9))
        mode2 = load_trigger
        soc_start = state.soc
        h2_start = sum(state.h2_kg)
        h2_by_truck_start = tuple(state.h2_kg)
        idle = None
        mode1_bus: int | None = None
        mode1_mw = pv_charging_mw = grid_charging_mw = 0.0
        if mode2:
            dispatch = dispatch_hour(
                support_net,
                baseline_voltage,
                demand,
                generators,
                state,
                mw_per_raw_kwh,
            )
            supported_voltage = dispatch.supported_voltage
            supported_loss = dispatch.supported_loss_mw
            injections = dispatch.injections_mw
            residual = dispatch.remaining_excess_mw
            scores = dispatch.initial_severity
            hfc_kwh = dispatch.hfc_kwh
            ess_kwh = dispatch.ess_kwh
            load_response_mw = dispatch.load_response_mw
            consumed_h2 = dispatch.h2_consumed_kg
            ess_withdrawal = dispatch.ess_withdrawal_kwh
            vehicles = dispatch.trucks
        else:
            idle = advance_idle(state, hour, high_lcoe, low_smp)
            if idle.phase1_ess_kwh > 0:
                # Prices are common to all residential buses; lowest voltage
                # resolves the otherwise equal spatial economic choice.
                mode1_bus = min(
                    residential_bus_numbers,
                    key=lambda bus: (baseline_voltage[bus - 1], bus),
                )
                mode1_mw = idle.phase1_ess_kwh * mw_per_raw_kwh
                support_net.sgen.at[mode1_generators[mode1_bus], "p_mw"] = mode1_mw
            pv_charging_mw = (idle.pv_ess_charge_kwh + idle.pv_p2g_kwh) * mw_per_raw_kwh
            grid_charging_mw = idle.grid_ess_charge_kwh * mw_per_raw_kwh
            support_net.load.at[pv_charge_load, "p_mw"] = pv_charging_mw
            support_net.load.at[grid_charge_load, "p_mw"] = grid_charging_mw
            supported_voltage, supported_loss = solve_network(support_net)
            injections = np.zeros(len(INDUSTRIAL_BUS_NUMBERS))
            residual = demand.copy()
            scores = np.zeros(len(INDUSTRIAL_BUS_NUMBERS))
            hfc_kwh = ess_kwh = load_response_mw = 0.0
            consumed_h2 = idle.travel_h2_kg
            ess_withdrawal = 0.0
            vehicles = ()
        supply_active = bool(hfc_kwh + ess_kwh > 1e-7)
        baseline_deficit = np.maximum(MIN_VOLTAGE_PU - baseline_voltage, 0.0)
        supported_deficit = np.maximum(MIN_VOLTAGE_PU - supported_voltage, 0.0)
        hourly_rows.append(
            {
                "alpha": alpha,
                "t": t,
                "timestamp": str(frame.at[t, "timestamp"]),
                "mode2_trigger": mode2,
                "load_excess_trigger": load_trigger,
                "industrial_vmin_baseline": float(baseline_voltage[BUS_INDICES].min()),
                "supply_active": supply_active,
                "mode1_active": mode1_bus is not None,
                "mode1_bus": mode1_bus,
                "mode1_supply_mw": mode1_mw,
                "pv_charging_mw": pv_charging_mw,
                "grid_charging_mw": grid_charging_mw,
                "net_hbmps_mw": float(injections.sum())
                + mode1_mw
                - pv_charging_mw
                - grid_charging_mw,
                "load_dispatch_active": supply_active and load_trigger,
                "industrial_load_mw": float(bus_loads[t].sum()),
                "bus_excess_mw": float(demand.sum()),
                "residual_excess_mw": float(residual.sum()),
                "hfc_kwh": hfc_kwh,
                "ess_emergency_kwh": ess_kwh,
                "emergency_supply_mw": float(injections.sum()),
                "load_response_mw": load_response_mw,
                "active_trucks": sum(vehicle.bus is not None for vehicle in vehicles),
                "vmin_baseline": float(baseline_voltage.min()),
                "vmin_supported": float(supported_voltage.min()),
                "voltage_violating_buses_baseline": int(
                    np.count_nonzero(baseline_deficit)
                ),
                "voltage_violating_buses_supported": int(
                    np.count_nonzero(supported_deficit)
                ),
                "voltage_deficit_baseline_pu": float(baseline_deficit.sum()),
                "voltage_deficit_supported_pu": float(supported_deficit.sum()),
                "line_loss_baseline_mw": baseline_loss,
                "line_loss_supported_mw": supported_loss,
                "soc_start_pct": soc_start * 100,
                "soc_end_pct": state.soc * 100,
                "main_loh_end_pct": state.h2_kg[0] / H2_CAPACITY_KG * 100,
                "fleet_h2_start_kg": h2_start,
                "fleet_h2_end_kg": sum(state.h2_kg),
                "h2_consumed_kg": consumed_h2,
                "h2_refilled_kg": idle.external_h2_kg if idle else 0.0,
                "phase1_ess_kwh": idle.phase1_ess_kwh if idle else 0.0,
                "pv_ess_charge_kwh": idle.pv_ess_charge_kwh if idle else 0.0,
                "grid_ess_charge_kwh": idle.grid_ess_charge_kwh if idle else 0.0,
                "pv_p2g_kwh": idle.pv_p2g_kwh if idle else 0.0,
                "ess_withdrawal_kwh": ess_withdrawal,
            }
        )
        for bus in range(1, 34):
            index = industrial_by_bus.get(bus)
            mode1_injection = mode1_mw if bus == mode1_bus else 0.0
            charging = pv_charging_mw * (bus == PV_BUS_NUMBER) + grid_charging_mw * (
                bus == grid_charge_bus
            )
            bus_rows.append(
                {
                    "alpha": alpha,
                    "t": t,
                    "bus": bus,
                    "bus_type": "Slack"
                    if bus == 1
                    else ("Industrial" if index is not None else "Residential"),
                    "industrial_candidate": index is not None,
                    "industrial_load_mw": float(bus_loads[t, index])
                    if index is not None
                    else 0.0,
                    "threshold_mw": float(bus_thresholds[index])
                    if index is not None
                    else 0.0,
                    "excess_mw": float(demand[index]) if index is not None else 0.0,
                    "initial_severity": float(scores[index])
                    if index is not None
                    else 0.0,
                    "mode2_injection_mw": float(injections[index])
                    if index is not None
                    else 0.0,
                    "mode1_injection_mw": mode1_injection,
                    "injection_mw": (
                        float(injections[index]) if index is not None else 0.0
                    )
                    + mode1_injection,
                    "charging_mw": charging,
                    "net_hbmps_mw": (
                        float(injections[index]) if index is not None else 0.0
                    )
                    + mode1_injection
                    - charging,
                    "residual_excess_mw": float(residual[index])
                    if index is not None
                    else 0.0,
                    "baseline_voltage_pu": float(baseline_voltage[bus - 1]),
                    "supported_voltage_pu": float(supported_voltage[bus - 1]),
                }
            )
        for truck in range(FLEET_SIZE):
            vehicle = vehicles[truck] if vehicles else None
            idle_bus = (
                (
                    mode1_bus
                    if mode1_bus is not None
                    else PV_BUS_NUMBER
                    if pv_charging_mw > 0
                    else grid_charge_bus
                    if grid_charging_mw > 0
                    else None
                )
                if truck == 0
                else None
            )
            truck_rows.append(
                {
                    "alpha": alpha,
                    "t": t,
                    "truck": truck,
                    "bus": vehicle.bus if vehicle else idle_bus,
                    "mode": (
                        "Mode 2"
                        if vehicle and vehicle.bus is not None
                        else "Mode 1"
                        if mode1_bus is not None and truck == 0
                        else "PV charging"
                        if pv_charging_mw > 0 and truck == 0
                        else "Grid charging"
                        if grid_charging_mw > 0 and truck == 0
                        else "Standby"
                    ),
                    "hfc_kwh": vehicle.hfc_kwh if vehicle else 0.0,
                    "ess_kwh": vehicle.ess_kwh if vehicle else 0.0,
                    "mode1_ess_kwh": idle.phase1_ess_kwh
                    if idle and truck == 0
                    else 0.0,
                    "h2_start_kg": h2_by_truck_start[truck],
                    "h2_end_kg": state.h2_kg[truck],
                    "loh_end_pct": state.h2_kg[truck] / H2_CAPACITY_KG * 100,
                }
            )
        baseline_profiles.append(baseline_voltage)
        supported_profiles.append(supported_voltage)

    baseline_array = np.stack(baseline_profiles)
    return SeverityResult(
        alpha=alpha,
        hourly=pd.DataFrame.from_records(hourly_rows),
        buses=pd.DataFrame.from_records(bus_rows),
        trucks=pd.DataFrame.from_records(truck_rows),
        baseline_profiles=baseline_array,
        supported_profiles=np.stack(supported_profiles),
        worst_hour=int(np.argmin(baseline_array.min(axis=1))),
    )


def main() -> None:
    """Generate both dynamic experiments, comparisons, figures, CSV and report."""
    from severity_report import compare_strategies, write_report

    results = tuple(simulate(alpha) for alpha in ALPHAS)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.concat([result.hourly for result in results], ignore_index=True).to_csv(
        HOURLY_PATH, index=False
    )
    pd.concat([result.buses for result in results], ignore_index=True).to_csv(
        BUS_PATH, index=False
    )
    pd.concat([result.trucks for result in results], ignore_index=True).to_csv(
        TRUCK_PATH, index=False
    )
    for index, result in enumerate(results, start=1):
        alpha_label = str(result.alpha).replace(".", "_")
        stem = f"fig15_{index}_severity_dispatch_alpha_{alpha_label}"
        for suffix in ("png", "pdf"):
            save_severity_figure(result, OUTPUT_DIR / f"{stem}.{suffix}")
    comparison = compare_strategies(results)
    comparison.to_csv(COMPARISON_PATH, index=False)
    write_report(results, comparison, SUMMARY_PATH)
    print(SUMMARY_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
