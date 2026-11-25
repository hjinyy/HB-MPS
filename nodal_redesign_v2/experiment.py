"""Compare legacy, reclassified, and common-scale nodal dispatch cases.

Run with ``uv run --with numpy --with pandas --with matplotlib --with pandapower
python -m nodal_redesign_v2.run``. No legacy result path is written by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandapower as pp
import pandapower.networks as nw
import pandas as pd

from hb_inputs import INPUT, load_hours
from powerflow_validation import (
    INDUSTRIAL_BUS_NUMBERS as LEGACY_INDUSTRIAL_BUSES,
    INDUSTRIAL_COLUMN,
    INPUT_PATH,
    MIN_VOLTAGE_PU,
    PV_BUS_NUMBER,
    PV_COLUMN,
    PV_PENETRATION,
    RESIDENTIAL_BUS_NUMBERS as LEGACY_RESIDENTIAL_BUSES,
    RESIDENTIAL_COLUMN,
    build_network,
    load_profiles,
    profile_fraction,
    solve_network,
)
from powerflow_validation_severity import SeverityResult, simulate as legacy_simulate
from severity_fleet import (
    FLEET_SIZE,
    H2_CAPACITY_KG,
    FleetState,
    advance_idle,
    price_quantiles,
)

from .dispatch import dispatch_hour

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "results" / "nodal_redesign_v2"
NEW_INDUSTRIAL_BUSES = tuple(sorted(set(LEGACY_INDUSTRIAL_BUSES) | {
    19, 20, 21, 23, 24, 25, 26, 27, 28, 29
}))
ALL_LOAD_BUSES = tuple(range(2, 34))
GRID_CHARGE_BUS = 9
ALPHAS = (1.3, 1.5)


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    industrial_buses: tuple[int, ...]
    scale_rule: str
    legacy_load_scaling: bool = False

    @property
    def residential_buses(self) -> tuple[int, ...]:
        return tuple(bus for bus in ALL_LOAD_BUSES if bus not in self.industrial_buses)


CASES = (
    Case("C1", tuple(LEGACY_INDUSTRIAL_BUSES), "industrial_peak", True),
    Case("C2", NEW_INDUSTRIAL_BUSES, "industrial_peak"),
    Case("C3", NEW_INDUSTRIAL_BUSES, "common_peak_sum"),
)


@dataclass(frozen=True, slots=True)
class CaseRun:
    case: Case
    result: SeverityResult
    scale_mw_per_raw_kwh: float
    industrial_rating_mw: float
    residential_rating_mw: float
    total_rating_mw: float
    total_load_peak_mw: float


def _ratings(case: Case, net: pp.pandapowerNet) -> tuple[float, float, float]:
    industrial = float(net.load.loc[
        net.load.bus.isin({bus - 1 for bus in case.industrial_buses}), "p_mw"
    ].sum())
    residential = float(net.load.p_mw.sum()) - industrial
    return industrial, residential, industrial + residential


def _scale(case: Case, frame: pd.DataFrame, ratings: tuple[float, float, float]) -> float:
    industrial_peak = float(frame[INDUSTRIAL_COLUMN].max())
    residential_peak = float(frame[RESIDENTIAL_COLUMN].max())
    if case.scale_rule == "industrial_peak":
        return ratings[0] / industrial_peak
    if case.scale_rule == "common_peak_sum":
        return ratings[2] / (industrial_peak + residential_peak)
    raise ValueError(f"Unknown scale rule: {case.scale_rule}")


def _set_loads(
    net: pp.pandapowerNet,
    base_load_indices: tuple[int, ...],
    industrial_buses: tuple[int, ...],
    industrial_fraction: float,
    residential_fraction: float,
    pv_mw: float,
) -> None:
    """Scale only benchmark PQ loads; preserve their ratings and Q/P ratios."""
    net.load.loc[list(base_load_indices), "scaling"] = residential_fraction
    industrial_indices = net.load.index[
        net.load.index.isin(base_load_indices)
        & net.load.bus.isin({bus - 1 for bus in industrial_buses})
    ]
    net.load.loc[industrial_indices, "scaling"] = industrial_fraction
    net.sgen.loc[net.sgen.name.eq("PV"), "p_mw"] = pv_mw


def _enrich(
    case: Case,
    result: SeverityResult,
    frame: pd.DataFrame,
    ratings: tuple[float, float, float],
    scale: float,
) -> CaseRun:
    """Record the network PV balance without changing the dispatch policy."""
    benchmark = nw.case33bw()
    original_loads = benchmark.load.copy()
    industrial_fraction = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential_fraction = profile_fraction(frame[RESIDENTIAL_COLUMN])
    pv_fraction = profile_fraction(frame[PV_COLUMN])
    if case.legacy_load_scaling:
        # The preserved C1 solver classifies 23 buses as residential but
        # actually applies a weighted mixed profile to 14 of them.
        legacy_residential = {bus - 1 for bus in LEGACY_RESIDENTIAL_BUSES}
        legacy_industrial = {bus - 1 for bus in LEGACY_INDUSTRIAL_BUSES}
        legacy_residential_rating = float(
            original_loads.loc[
                original_loads.bus.isin(legacy_residential), "p_mw"
            ].sum()
        )
        mixed = (
            ratings[0] * industrial_fraction
            + legacy_residential_rating * residential_fraction
        ) / (ratings[0] + legacy_residential_rating)
        total_load = np.zeros(len(frame))
        for row in original_loads.itertuples():
            fraction = (
                industrial_fraction if row.bus in legacy_industrial
                else residential_fraction if row.bus in legacy_residential
                else mixed
            )
            total_load += float(row.p_mw) * fraction
    else:
        total_load = ratings[0] * industrial_fraction + ratings[1] * residential_fraction
    pv_generation = pv_fraction * ratings[2] * PV_PENETRATION
    raw_surplus = np.maximum(
        frame[PV_COLUMN].to_numpy(dtype=float)
        - frame[INDUSTRIAL_COLUMN].to_numpy(dtype=float)
        - frame[RESIDENTIAL_COLUMN].to_numpy(dtype=float),
        0.0,
    ) * scale
    network_surplus = np.maximum(pv_generation - total_load, 0.0)
    hourly = result.hourly.copy()
    hourly.insert(0, "case_id", case.name)
    hourly["total_grid_load_mw"] = total_load
    hourly["pv_generation_mw"] = pv_generation
    hourly["raw_pv_surplus_scaled_mw"] = raw_surplus
    hourly["network_pv_surplus_mw"] = network_surplus
    hourly["pv_use_mw"] = (
        hourly.pv_ess_charge_kwh + hourly.pv_p2g_kwh
    ) * scale
    hourly["pv_surplus_shortfall_mw"] = np.maximum(
        hourly.pv_use_mw - network_surplus, 0.0
    )
    buses = result.buses.copy()
    buses.insert(0, "case_id", case.name)
    trucks = result.trucks.copy()
    trucks.insert(0, "case_id", case.name)
    return CaseRun(
        case,
        replace(result, hourly=hourly, buses=buses, trucks=trucks),
        scale,
        *ratings,
        float(np.max(total_load)),
    )


def simulate(case: Case, alpha: float, frame: pd.DataFrame | None = None) -> CaseRun:
    """Run one 168-hour case and apply its chosen raw-to-grid conversion."""
    if alpha not in ALPHAS:
        raise ValueError(f"Unsupported alpha: {alpha}")
    frame = load_profiles(INPUT_PATH) if frame is None else frame
    hours = load_hours(INPUT)
    if len(frame) != 168 or len(hours) != 168:
        raise AssertionError("Nodal redesign requires 168 aligned hours")
    if set(case.industrial_buses) & set(case.residential_buses):
        raise AssertionError("Industrial and residential buses overlap")
    if set(case.industrial_buses) | set(case.residential_buses) != set(ALL_LOAD_BUSES):
        raise AssertionError("Every non-slack load bus needs one type")

    ratings = _ratings(case, nw.case33bw())
    scale = _scale(case, frame, ratings)
    if case.legacy_load_scaling:
        return _enrich(case, legacy_simulate(alpha), frame, ratings, scale)

    industrial_fraction = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential_fraction = profile_fraction(frame[RESIDENTIAL_COLUMN])
    pv_fraction = profile_fraction(frame[PV_COLUMN])
    baseline_net, support_net = build_network(), build_network()
    base_load_indices = tuple(baseline_net.load.index)
    bus_ratings = np.array([
        float(baseline_net.load.loc[baseline_net.load.bus.eq(bus - 1), "p_mw"].sum())
        for bus in case.industrial_buses
    ])
    bus_loads = industrial_fraction[:, None] * bus_ratings[None, :]
    thresholds = alpha * bus_loads.mean(axis=0)
    generators = np.array([
        pp.create_sgen(support_net, bus - 1, p_mw=0.0, q_mvar=0.0, name=f"Dynamic-{bus}")
        for bus in case.industrial_buses
    ])
    mode1_generators = {
        bus: pp.create_sgen(
            support_net, bus - 1, p_mw=0.0, q_mvar=0.0,
            name=f"Mode1 residential-{bus}",
        )
        for bus in case.residential_buses
    }
    pv_charge_load = pp.create_load(
        support_net, PV_BUS_NUMBER - 1, p_mw=0.0, q_mvar=0.0,
        name="HB PV charging and P2G",
    )
    grid_charge_load = pp.create_load(
        support_net, GRID_CHARGE_BUS - 1, p_mw=0.0, q_mvar=0.0,
        name="HB grid charging depot",
    )
    state = FleetState.initial()
    high_lcoe, low_smp = price_quantiles(hours)
    hourly_rows: list[dict] = []
    bus_rows: list[dict] = []
    truck_rows: list[dict] = []
    baseline_profiles: list[np.ndarray] = []
    supported_profiles: list[np.ndarray] = []
    industrial_by_bus = {bus: index for index, bus in enumerate(case.industrial_buses)}
    pv_rating = ratings[2] * PV_PENETRATION

    for t, hour in enumerate(hours):
        pv_mw = pv_fraction[t] * pv_rating
        for net in (baseline_net, support_net):
            _set_loads(
                net, base_load_indices, case.industrial_buses,
                industrial_fraction[t], residential_fraction[t], pv_mw,
            )
        support_net.sgen.loc[generators, "p_mw"] = 0.0
        support_net.sgen.loc[list(mode1_generators.values()), "p_mw"] = 0.0
        support_net.load.loc[[pv_charge_load, grid_charge_load], "p_mw"] = 0.0
        support_net.load.loc[[pv_charge_load, grid_charge_load], "scaling"] = 1.0
        baseline_voltage, baseline_loss = solve_network(baseline_net)
        demand = np.maximum(bus_loads[t] - thresholds, 0.0)
        mode2 = bool(np.any(demand > 1e-9))
        soc_start = state.soc
        h2_start = sum(state.h2_kg)
        h2_by_truck_start = tuple(state.h2_kg)
        idle = None
        mode1_bus: int | None = None
        mode1_mw = pv_charging_mw = grid_charging_mw = 0.0
        if mode2:
            dispatched = dispatch_hour(
                support_net, baseline_voltage, demand, generators, state,
                scale, case.industrial_buses,
            )
            supported_voltage = dispatched.supported_voltage
            supported_loss = dispatched.supported_loss_mw
            injections = dispatched.injections_mw
            residual = dispatched.remaining_excess_mw
            scores = dispatched.initial_severity
            hfc_kwh, ess_kwh = dispatched.hfc_kwh, dispatched.ess_kwh
            load_response_mw = dispatched.load_response_mw
            consumed_h2 = dispatched.h2_consumed_kg
            ess_withdrawal = dispatched.ess_withdrawal_kwh
            vehicles = dispatched.trucks
        else:
            idle = advance_idle(state, hour, high_lcoe, low_smp)
            if idle.phase1_ess_kwh > 0:
                mode1_bus = min(
                    case.residential_buses,
                    key=lambda bus: (baseline_voltage[bus - 1], bus),
                )
                mode1_mw = idle.phase1_ess_kwh * scale
                support_net.sgen.at[mode1_generators[mode1_bus], "p_mw"] = mode1_mw
            pv_charging_mw = (idle.pv_ess_charge_kwh + idle.pv_p2g_kwh) * scale
            grid_charging_mw = idle.grid_ess_charge_kwh * scale
            support_net.load.at[pv_charge_load, "p_mw"] = pv_charging_mw
            support_net.load.at[grid_charge_load, "p_mw"] = grid_charging_mw
            supported_voltage, supported_loss = solve_network(support_net)
            injections = np.zeros(len(case.industrial_buses))
            residual = demand.copy()
            scores = np.zeros(len(case.industrial_buses))
            hfc_kwh = ess_kwh = load_response_mw = ess_withdrawal = 0.0
            consumed_h2 = idle.travel_h2_kg
            vehicles = ()
        if not np.isclose(demand.sum(), injections.sum() + residual.sum(), atol=1e-8):
            raise AssertionError("Local excess does not balance injections and residual")
        if not np.isclose(injections.sum(), (hfc_kwh + ess_kwh) * scale, atol=1e-8):
            raise AssertionError("Raw-to-grid emergency energy conversion is inconsistent")
        supply_active = bool(hfc_kwh + ess_kwh > 1e-7)
        deficit_base = np.maximum(MIN_VOLTAGE_PU - baseline_voltage, 0.0)
        deficit_supported = np.maximum(MIN_VOLTAGE_PU - supported_voltage, 0.0)
        hourly_rows.append({
            "alpha": alpha, "t": t, "timestamp": str(frame.at[t, "timestamp"]),
            "mode2_trigger": mode2, "load_excess_trigger": mode2,
            "industrial_vmin_baseline": float(baseline_voltage[np.array(case.industrial_buses) - 1].min()),
            "supply_active": supply_active, "mode1_active": mode1_bus is not None,
            "mode1_bus": mode1_bus, "mode1_supply_mw": mode1_mw,
            "pv_charging_mw": pv_charging_mw, "grid_charging_mw": grid_charging_mw,
            "net_hbmps_mw": float(injections.sum()) + mode1_mw - pv_charging_mw - grid_charging_mw,
            "load_dispatch_active": supply_active and mode2,
            "industrial_load_mw": float(bus_loads[t].sum()),
            "bus_excess_mw": float(demand.sum()),
            "residual_excess_mw": float(residual.sum()),
            "hfc_kwh": hfc_kwh, "ess_emergency_kwh": ess_kwh,
            "emergency_supply_mw": float(injections.sum()),
            "load_response_mw": load_response_mw,
            "active_trucks": sum(vehicle.bus is not None for vehicle in vehicles),
            "vmin_baseline": float(baseline_voltage.min()),
            "vmin_supported": float(supported_voltage.min()),
            "voltage_violating_buses_baseline": int(np.count_nonzero(deficit_base)),
            "voltage_violating_buses_supported": int(np.count_nonzero(deficit_supported)),
            "voltage_deficit_baseline_pu": float(deficit_base.sum()),
            "voltage_deficit_supported_pu": float(deficit_supported.sum()),
            "line_loss_baseline_mw": baseline_loss,
            "line_loss_supported_mw": supported_loss,
            "soc_start_pct": soc_start * 100, "soc_end_pct": state.soc * 100,
            "main_loh_end_pct": state.h2_kg[0] / H2_CAPACITY_KG * 100,
            "fleet_h2_start_kg": h2_start, "fleet_h2_end_kg": sum(state.h2_kg),
            "h2_consumed_kg": consumed_h2,
            "h2_refilled_kg": idle.external_h2_kg if idle else 0.0,
            "phase1_ess_kwh": idle.phase1_ess_kwh if idle else 0.0,
            "pv_ess_charge_kwh": idle.pv_ess_charge_kwh if idle else 0.0,
            "grid_ess_charge_kwh": idle.grid_ess_charge_kwh if idle else 0.0,
            "pv_p2g_kwh": idle.pv_p2g_kwh if idle else 0.0,
            "ess_withdrawal_kwh": ess_withdrawal,
        })
        for bus in range(1, 34):
            index = industrial_by_bus.get(bus)
            mode1_injection = mode1_mw if bus == mode1_bus else 0.0
            charging = pv_charging_mw * (bus == PV_BUS_NUMBER) + grid_charging_mw * (
                bus == GRID_CHARGE_BUS
            )
            emergency_injection = float(injections[index]) if index is not None else 0.0
            bus_rows.append({
                "alpha": alpha, "t": t, "bus": bus,
                "bus_type": "Slack" if bus == 1 else (
                    "Industrial" if index is not None else "Residential"
                ),
                "industrial_candidate": index is not None,
                "industrial_load_mw": float(bus_loads[t, index]) if index is not None else 0.0,
                "threshold_mw": float(thresholds[index]) if index is not None else 0.0,
                "excess_mw": float(demand[index]) if index is not None else 0.0,
                "initial_severity": float(scores[index]) if index is not None else 0.0,
                "mode2_injection_mw": emergency_injection,
                "mode1_injection_mw": mode1_injection,
                "injection_mw": emergency_injection + mode1_injection,
                "charging_mw": charging,
                "net_hbmps_mw": emergency_injection + mode1_injection - charging,
                "residual_excess_mw": float(residual[index]) if index is not None else 0.0,
                "baseline_voltage_pu": float(baseline_voltage[bus - 1]),
                "supported_voltage_pu": float(supported_voltage[bus - 1]),
            })
        for truck in range(FLEET_SIZE):
            vehicle = vehicles[truck] if vehicles else None
            idle_bus = (
                mode1_bus if mode1_bus is not None else
                PV_BUS_NUMBER if pv_charging_mw > 0 else
                GRID_CHARGE_BUS if grid_charging_mw > 0 else None
            ) if truck == 0 else None
            truck_rows.append({
                "alpha": alpha, "t": t, "truck": truck,
                "bus": vehicle.bus if vehicle else idle_bus,
                "mode": (
                    "Mode 2" if vehicle and vehicle.bus is not None else
                    "Mode 1" if mode1_bus is not None and truck == 0 else
                    "PV charging" if pv_charging_mw > 0 and truck == 0 else
                    "Grid charging" if grid_charging_mw > 0 and truck == 0 else
                    "Standby"
                ),
                "hfc_kwh": vehicle.hfc_kwh if vehicle else 0.0,
                "ess_kwh": vehicle.ess_kwh if vehicle else 0.0,
                "mode1_ess_kwh": idle.phase1_ess_kwh if idle and truck == 0 else 0.0,
                "h2_start_kg": h2_by_truck_start[truck],
                "h2_end_kg": state.h2_kg[truck],
                "loh_end_pct": state.h2_kg[truck] / H2_CAPACITY_KG * 100,
            })
        baseline_profiles.append(baseline_voltage)
        supported_profiles.append(supported_voltage)

    baseline_array = np.stack(baseline_profiles)
    result = SeverityResult(
        alpha=alpha,
        hourly=pd.DataFrame.from_records(hourly_rows),
        buses=pd.DataFrame.from_records(bus_rows),
        trucks=pd.DataFrame.from_records(truck_rows),
        baseline_profiles=baseline_array,
        supported_profiles=np.stack(supported_profiles),
        worst_hour=int(np.argmin(baseline_array.min(axis=1))),
    )
    return _enrich(case, result, frame, ratings, scale)
