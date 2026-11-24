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

"""Validate severity-ranked placement of unchanged P1 emergency supply."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandapower as pp

from emergency_dispatch import run_scenario
from emergency_dispatch_model import Scenario, Strategy
from hb_inputs import INPUT, load_hours
from p1_multibus_dispatch import allocate_p1_supply, validate_main_reference
from powerflow_validation import (
    INDUSTRIAL_BUS_NUMBERS,
    INDUSTRIAL_COLUMN,
    INPUT_PATH,
    MAIN_REFERENCE_PATH,
    MIN_VOLTAGE_PU,
    OUTPUT_DIR,
    PV_COLUMN,
    PV_PENETRATION,
    RESIDENTIAL_BUS_NUMBERS,
    RESIDENTIAL_COLUMN,
    build_network,
    load_profiles,
    profile_fraction,
    set_operating_point,
    solve_network,
)
from powerflow_plot_severity import save_severity_figure

ALPHAS: Final = (1.3, 1.5)
WEIGHT_DEMAND: Final = 0.5
WEIGHT_VOLTAGE: Final = 0.5
SUMMARY_PATH: Final = OUTPUT_DIR / "FIG15_SEVERITY_DISPATCH_SUMMARY.md"


@dataclass(frozen=True, slots=True)
class SeverityResult:
    alpha: float
    baseline_profiles: np.ndarray
    supported_profiles: np.ndarray
    baseline_losses_mw: np.ndarray
    supported_losses_mw: np.ndarray
    active_hours: np.ndarray
    main_buses: tuple[int | None, ...]
    injection_buses: tuple[tuple[int, ...], ...]
    supplied_raw_kwh: float
    supplied_ac_mwh: float
    worst_hour: int

    @property
    def baseline_minimum(self) -> np.ndarray:
        return self.baseline_profiles.min(axis=1)

    @property
    def supported_minimum(self) -> np.ndarray:
        return self.supported_profiles.min(axis=1)


def severity_scores(demand_mw: np.ndarray, baseline_voltage: np.ndarray) -> np.ndarray:
    """Score each industrial bus using local excess demand and voltage deficit."""
    demand_scale = max(float(demand_mw.max()), 1e-12)
    voltage_deficit = np.maximum(MIN_VOLTAGE_PU - baseline_voltage, 0.0)
    return (
        WEIGHT_DEMAND * demand_mw / demand_scale
        + WEIGHT_VOLTAGE * voltage_deficit / MIN_VOLTAGE_PU
    )


def place_trucks(
    demand_mw: np.ndarray,
    scores: np.ndarray,
    truck_hfc_mw: np.ndarray,
    ess_mw: float,
) -> tuple[np.ndarray, int | None, tuple[int, ...]]:
    """Place each active truck at one ranked bus; keep ESS with the main truck.

    Existing P1 output is injected in full. Remaining local excess demand only
    guides the next location; it does not alter the operational energy balance.
    """
    injections = np.zeros(len(INDUSTRIAL_BUS_NUMBERS), dtype=float)
    remaining = demand_mw.copy()
    ranked = sorted(
        range(len(remaining)),
        key=lambda index: (-scores[index], INDUSTRIAL_BUS_NUMBERS[index]),
    )
    selected: list[int] = []
    main_bus: int | None = None
    for truck, hfc_mw in enumerate(truck_hfc_mw):
        supply = float(hfc_mw) + (ess_mw if truck == 0 else 0.0)
        if supply <= 0:
            continue
        candidates = [index for index in ranked if remaining[index] > 1e-12]
        chosen = candidates[0] if candidates else ranked[0]
        injections[chosen] += supply
        remaining[chosen] = max(0.0, remaining[chosen] - supply)
        bus_number = INDUSTRIAL_BUS_NUMBERS[chosen]
        selected.append(bus_number)
        if truck == 0:
            main_bus = bus_number
    if not np.isclose(injections.sum(), truck_hfc_mw.sum() + ess_mw):
        raise AssertionError("Severity placement changed P1 emergency supply")
    return injections, main_bus, tuple(selected)


def simulate(alpha: float) -> SeverityResult:
    """Run 168 hourly baseline and severity-supported AC power flows."""
    frame = load_profiles(INPUT_PATH)
    industrial_fraction = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential_fraction = profile_fraction(frame[RESIDENTIAL_COLUMN])
    pv_fraction = profile_fraction(frame[PV_COLUMN])
    hours = load_hours(INPUT)
    run = run_scenario(hours, Scenario(alpha, 5, Strategy.P1))
    validate_main_reference(run, MAIN_REFERENCE_PATH)
    if len(frame) != 168 or len(run.steps) != len(frame):
        raise AssertionError("Severity experiment requires aligned 168-hour profiles")

    base_net = build_network()
    support_net = build_network()
    industrial_indices = {number - 1 for number in INDUSTRIAL_BUS_NUMBERS}
    residential_indices = {number - 1 for number in RESIDENTIAL_BUS_NUMBERS}
    industrial_rating = float(
        base_net.load.loc[base_net.load.bus.isin(industrial_indices), "p_mw"].sum()
    )
    residential_rating = float(
        base_net.load.loc[base_net.load.bus.isin(residential_indices), "p_mw"].sum()
    )
    bus_ratings = np.array(
        [
            float(base_net.load.loc[base_net.load.bus.eq(bus - 1), "p_mw"].sum())
            for bus in INDUSTRIAL_BUS_NUMBERS
        ]
    )
    bus_loads = industrial_fraction[:, None] * bus_ratings[None, :]
    bus_thresholds = alpha * bus_loads.mean(axis=0)
    pv_rating = float(base_net.load.p_mw.sum()) * PV_PENETRATION
    raw_peak = float(frame[INDUSTRIAL_COLUMN].max())
    mw_per_raw_kwh = industrial_rating / raw_peak
    bus18_rating = bus_ratings[INDUSTRIAL_BUS_NUMBERS.index(18)]
    bus33_rating = bus_ratings[INDUSTRIAL_BUS_NUMBERS.index(33)]
    _, truck_rows = allocate_p1_supply(
        hours, run, bus18_rating / (bus18_rating + bus33_rating)
    )
    generator_indices = np.array(
        [
            pp.create_sgen(
                support_net, bus - 1, p_mw=0.0, q_mvar=0.0,
                name=f"Severity-{bus}",
            )
            for bus in INDUSTRIAL_BUS_NUMBERS
        ]
    )

    baseline_profiles: list[np.ndarray] = []
    supported_profiles: list[np.ndarray] = []
    baseline_losses: list[float] = []
    supported_losses: list[float] = []
    active_hours: list[bool] = []
    main_buses: list[int | None] = []
    injection_buses: list[tuple[int, ...]] = []
    for t, step in enumerate(run.steps):
        mixed_scale = (
            industrial_rating * industrial_fraction[t]
            + residential_rating * residential_fraction[t]
        ) / (industrial_rating + residential_rating)
        operating_point = (
            industrial_fraction[t], residential_fraction[t], mixed_scale,
            pv_fraction[t] * pv_rating, 0.0,
        )
        set_operating_point(base_net, *operating_point)
        set_operating_point(support_net, *operating_point)
        baseline, baseline_loss = solve_network(base_net)
        demand = np.maximum(bus_loads[t] - bus_thresholds, 0.0)
        bus_voltage = baseline[np.array(INDUSTRIAL_BUS_NUMBERS) - 1]
        scores = severity_scores(demand, bus_voltage)
        truck_hfc = np.array(
            [row.hfc_kwh for row in truck_rows[t * 5 : (t + 1) * 5]]
        ) * mw_per_raw_kwh
        ess_mw = step.ess_emergency_kwh * mw_per_raw_kwh
        if truck_hfc.sum() + ess_mw > 0 and not np.any(demand > 0):
            raise AssertionError("P1 emergency output occurred without local demand")
        injections, main_bus, selected = place_trucks(
            demand, scores, truck_hfc, ess_mw
        )
        support_net.sgen.loc[generator_indices, "p_mw"] = injections
        supported, supported_loss = solve_network(support_net)
        baseline_profiles.append(baseline)
        supported_profiles.append(supported)
        baseline_losses.append(baseline_loss)
        supported_losses.append(supported_loss)
        active_hours.append(bool(injections.sum() > 0))
        main_buses.append(main_bus)
        injection_buses.append(selected)

    baseline_array = np.stack(baseline_profiles)
    supported_array = np.stack(supported_profiles)
    return SeverityResult(
        alpha=alpha,
        baseline_profiles=baseline_array,
        supported_profiles=supported_array,
        baseline_losses_mw=np.array(baseline_losses),
        supported_losses_mw=np.array(supported_losses),
        active_hours=np.array(active_hours),
        main_buses=tuple(main_buses),
        injection_buses=tuple(injection_buses),
        supplied_raw_kwh=sum(
            step.hfc_kwh + step.ess_emergency_kwh for step in run.steps
        ),
        supplied_ac_mwh=sum(
            step.hfc_kwh + step.ess_emergency_kwh for step in run.steps
        ) * mw_per_raw_kwh,
        worst_hour=int(np.argmin(baseline_array.min(axis=1))),
    )


def write_summary(results: tuple[SeverityResult, ...], path: Path) -> None:
    """Record the experiment's assumptions and comparable case statistics."""
    lines = [
        "# Figure 15 severity dispatch validation",
        "",
        "The original Figure 15 and its validation workflow remain unchanged.",
        "Each industrial bus uses P_i,th = α × mean(P_i) over 168 h and "
        "D_i(t) = max(0, P_i(t) − P_i,th).",
        "Severity is S_i = 0.5 D_i/max_j(D_j) + "
        "0.5 max(0, 0.95 − V_i,base)/0.95 (zero demand term if all D_i = 0).",
        "Baseline AC voltage is calculated before the hourly ranking. "
        "Active trucks are placed at the highest-ranked bus with remaining local "
        "excess demand; if all demands are covered, the highest-ranked bus is used. "
        "One truck occupies one bus per hour, and ESS support stays with the main "
        "truck. Multiple trucks may use the same bus.",
        "P1 HFC and ESS emergency outputs, fuel inventories, and financial results "
        "are unchanged. Raw operational kWh is converted to benchmark-feeder MW "
        "using industrial benchmark MW / peak raw industrial kWh, as in the "
        "existing validation. A one-hour interval makes injected MW numerically "
        "equal to benchmark MWh. Voltage violations count hours whose minimum "
        "bus voltage is strictly below 0.95 p.u.",
        "",
        "| α | Active hours | Worst minimum voltage, baseline → support (p.u.) "
        "| Hours V < 0.95, baseline → support | Emergency supply, P1 raw "
        "(MWh) | AC-scaled injection (MWh) | Line losses, baseline → support "
        "(MWh) | Main injection bus frequency |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        frequencies = Counter(bus for bus in result.main_buses if bus is not None)
        frequency_text = ", ".join(
            f"Bus {bus}: {count} h" for bus, count in frequencies.most_common()
        ) or "None"
        lines.append(
            f"| {result.alpha:.1f} | {int(result.active_hours.sum())} "
            f"| {result.baseline_minimum.min():.4f} → "
            f"{result.supported_minimum.min():.4f} "
            f"| {int((result.baseline_minimum < MIN_VOLTAGE_PU).sum())} → "
            f"{int((result.supported_minimum < MIN_VOLTAGE_PU).sum())} "
            f"| {result.supplied_raw_kwh / 1000:.3f} "
            f"| {result.supplied_ac_mwh:.3f} "
            f"| {result.baseline_losses_mw.sum():.3f} → "
            f"{result.supported_losses_mw.sum():.3f} "
            f"| {frequency_text} |"
        )
    lines.extend([
        "",
        "For illustrating voltage support, α = 1.3 is the clearer paper "
        "candidate: it dispatches more often and has the larger minimum-voltage "
        "improvement. α = 1.5 is a less aggressive operating case, but its "
        "voltage effect is small. Neither case reduces the number of hours "
        "below 0.95 p.u.; neither figure should be presented as restoring "
        "full voltage compliance.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Generate only the additional α = 1.3 and 1.5 validation artifacts."""
    results = tuple(simulate(alpha) for alpha in ALPHAS)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, result in enumerate(results, start=1):
        stem = f"fig15_{index}_severity_dispatch_alpha_{str(result.alpha).replace('.', '_')}"
        for suffix in ("png", "pdf"):
            save_severity_figure(result, OUTPUT_DIR / f"{stem}.{suffix}")
    write_summary(results, SUMMARY_PATH)
    print(SUMMARY_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
