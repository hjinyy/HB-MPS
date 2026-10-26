"""Time-series AC power-flow validation on a modified IEEE 33-bus feeder.

The measured profiles provide time variation only. Their peaks are anchored to
the corresponding IEEE 33-bus customer-group demand, while every original load
and its bus-specific Q/P ratio are retained. HB-MPS dispatch uses the same raw
industrial-load threshold as the operational simulation and is limited to the
equivalent excess demand instead of injecting full-truck power.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandapower as pp
import pandapower.networks as nw
import pandas as pd

from powerflow_plot import save_figure

BASE_DIR: Final = Path(__file__).resolve().parent
INPUT_PATH: Final = BASE_DIR / "Data file" / "data_file.csv"
OUTPUT_DIR: Final = BASE_DIR / "results"
RESULT_PATH: Final = OUTPUT_DIR / "pf_results.csv"
FIGURE_PATH: Final = OUTPUT_DIR / "fig_powerflow_validation_bold.png"

SCENARIO_MULTIPLIERS: Final = (1.3, 1.5, 1.8)
INDUSTRIAL_BUS_NUMBERS: Final = (18, 17, 16, 15, 14, 33, 32, 31, 30)
RESIDENTIAL_BUS_NUMBERS: Final = (9, 10, 11, 12, 13, 25, 26, 22, 23)
PV_BUS_NUMBER: Final = 7
HB_BUS_NUMBER: Final = 18
SLACK_VOLTAGE_PU: Final = 1.0
MIN_VOLTAGE_PU: Final = 0.95
PV_PENETRATION: Final = 0.20
TRUCK_RATED_OUTPUT_MW: Final = 0.5

DATE_COLUMN: Final = "날짜"
HOUR_COLUMN: Final = "시간"
INDUSTRIAL_COLUMN: Final = "산업용 전력사용량(kWh)"
RESIDENTIAL_COLUMN: Final = "주택용 전력사용량(kWh)"
PV_COLUMN: Final = "E: 태양광 발전량(kWh)"


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    alpha: float
    records: pd.DataFrame
    worst_hour: int
    base_voltages: np.ndarray
    hbmps_voltages: np.ndarray


def load_profiles(path: Path) -> pd.DataFrame:
    """Load, validate, and chronologically order the hourly input profiles."""
    required = [DATE_COLUMN, HOUR_COLUMN, INDUSTRIAL_COLUMN, RESIDENTIAL_COLUMN, PV_COLUMN]
    frame = pd.read_csv(path)
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    frame = frame.loc[:, required].copy()
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=required)

    if frame.empty:
        raise ValueError("No valid hourly load-profile rows were found.")
    if not frame[HOUR_COLUMN].between(1, 24).all():
        raise ValueError("Hour values must be within 1..24.")
    if (frame[[INDUSTRIAL_COLUMN, RESIDENTIAL_COLUMN, PV_COLUMN]] < 0).any().any():
        raise ValueError("Load and PV profiles must be non-negative.")

    dates = pd.to_datetime(
        frame[DATE_COLUMN].astype(int).astype(str), format="%Y%m%d", errors="raise"
    )
    frame["timestamp"] = dates + pd.to_timedelta(frame[HOUR_COLUMN] - 1, unit="h")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("Duplicate hourly timestamps were found.")
    gaps = frame["timestamp"].diff().dropna().dt.total_seconds()
    if not gaps.eq(3600.0).all():
        raise ValueError("The input profile must be a continuous hourly series.")
    return frame


def profile_fraction(values: pd.Series) -> np.ndarray:
    """Anchor a measured profile peak to one unit of benchmark demand."""
    peak = float(values.max())
    if peak <= 0:
        raise ValueError(f"Profile {values.name!r} must contain a positive value.")
    return values.to_numpy(dtype=float) / peak


def build_network() -> pp.pandapowerNet:
    """Create the benchmark feeder and its two time-varying generators."""
    net = nw.case33bw()
    net.ext_grid.loc[:, "vm_pu"] = SLACK_VOLTAGE_PU
    pp.create_sgen(net, PV_BUS_NUMBER - 1, p_mw=0.0, q_mvar=0.0, name="PV")
    pp.create_sgen(net, HB_BUS_NUMBER - 1, p_mw=0.0, q_mvar=0.0, name="HB-MPS")
    return net


def set_operating_point(
    net: pp.pandapowerNet,
    industrial_scale: float,
    residential_scale: float,
    mixed_scale: float,
    pv_mw: float,
    hbmps_mw: float,
) -> None:
    """Apply one hour of PQ-load scaling and generator dispatch in place."""
    industrial_buses = {number - 1 for number in INDUSTRIAL_BUS_NUMBERS}
    residential_buses = {number - 1 for number in RESIDENTIAL_BUS_NUMBERS}
    net.load.loc[:, "scaling"] = mixed_scale
    net.load.loc[net.load.bus.isin(industrial_buses), "scaling"] = industrial_scale
    net.load.loc[net.load.bus.isin(residential_buses), "scaling"] = residential_scale
    net.sgen.loc[net.sgen.name.eq("PV"), "p_mw"] = pv_mw
    net.sgen.loc[net.sgen.name.eq("HB-MPS"), "p_mw"] = hbmps_mw


def solve_network(net: pp.pandapowerNet) -> tuple[np.ndarray, float]:
    """Run the balanced AC load flow and return bus voltages and line losses."""
    initialization = "results" if net.converged else "auto"
    pp.runpp(
        net,
        algorithm="nr",
        calculate_voltage_angles=False,
        init=initialization,
        numba=False,
    )
    if not net.converged:
        raise RuntimeError("Pandapower did not converge.")
    return net.res_bus.vm_pu.sort_index().to_numpy(), float(net.res_line.pl_mw.sum())


def simulate_scenario(
    frame: pd.DataFrame,
    alpha: float,
    industrial_fraction: np.ndarray,
    residential_fraction: np.ndarray,
    pv_fraction: np.ndarray,
) -> ScenarioResult:
    """Run baseline and HB-MPS power flows for one Mode-2 threshold."""
    benchmark = nw.case33bw()
    industrial_indices = {number - 1 for number in INDUSTRIAL_BUS_NUMBERS}
    residential_indices = {number - 1 for number in RESIDENTIAL_BUS_NUMBERS}
    industrial_rating_mw = float(
        benchmark.load.loc[benchmark.load.bus.isin(industrial_indices), "p_mw"].sum()
    )
    residential_rating_mw = float(
        benchmark.load.loc[benchmark.load.bus.isin(residential_indices), "p_mw"].sum()
    )
    system_rating_mw = float(benchmark.load.p_mw.sum())
    pv_rating_mw = system_rating_mw * PV_PENETRATION

    industrial_raw = frame[INDUSTRIAL_COLUMN].to_numpy(dtype=float)
    industrial_peak = float(industrial_raw.max())
    threshold_raw = float(industrial_raw.mean()) * alpha
    group_rating_mw = industrial_rating_mw + residential_rating_mw
    records: list[dict[str, float | int | str]] = []
    base_profiles: list[np.ndarray] = []
    hbmps_profiles: list[np.ndarray] = []
    base_net = build_network()
    hbmps_net = build_network()

    for hour in range(len(frame)):
        mixed_scale = (
            industrial_rating_mw * industrial_fraction[hour]
            + residential_rating_mw * residential_fraction[hour]
        ) / group_rating_mw
        excess_raw_kwh = max(industrial_raw[hour] - threshold_raw, 0.0)
        required_hbmps_mw = excess_raw_kwh / industrial_peak * industrial_rating_mw
        truck_count = (
            math.ceil(required_hbmps_mw / TRUCK_RATED_OUTPUT_MW)
            if required_hbmps_mw > 0
            else 0
        )
        dispatched_hbmps_mw = min(
            required_hbmps_mw, truck_count * TRUCK_RATED_OUTPUT_MW
        )
        pv_mw = pv_fraction[hour] * pv_rating_mw

        set_operating_point(
            base_net,
            industrial_fraction[hour], residential_fraction[hour], mixed_scale, pv_mw, 0.0
        )
        set_operating_point(
            hbmps_net,
            industrial_fraction[hour],
            residential_fraction[hour],
            mixed_scale,
            pv_mw,
            dispatched_hbmps_mw,
        )
        base_voltage, base_loss = solve_network(base_net)
        hbmps_voltage, hbmps_loss = solve_network(hbmps_net)
        base_profiles.append(base_voltage)
        hbmps_profiles.append(hbmps_voltage)

        records.append(
            {
                "alpha": alpha,
                "t": hour,
                "timestamp": str(frame.at[hour, "timestamp"]),
                "mode2": int(excess_raw_kwh > 0),
                "ntruck": truck_count,
                "raw_excess_kwh": excess_raw_kwh,
                "hbmps_mw": dispatched_hbmps_mw,
                "pv_mw": pv_mw,
                "vmin_base": float(base_voltage.min()),
                "vminbus_base": int(base_voltage.argmin()) + 1,
                "ploss_base_mw": base_loss,
                "viol_base": int(base_voltage.min() < MIN_VOLTAGE_PU),
                "vmin_hbmps": float(hbmps_voltage.min()),
                "vminbus_hbmps": int(hbmps_voltage.argmin()) + 1,
                "ploss_hbmps_mw": hbmps_loss,
                "viol_hbmps": int(hbmps_voltage.min() < MIN_VOLTAGE_PU),
            }
        )

    result_frame = pd.DataFrame.from_records(records)
    worst_hour = int(result_frame["vmin_base"].idxmin())
    return ScenarioResult(
        alpha=alpha,
        records=result_frame,
        worst_hour=worst_hour,
        base_voltages=base_profiles[worst_hour],
        hbmps_voltages=hbmps_profiles[worst_hour],
    )


def main() -> None:
    """Execute all validation scenarios and persist reproducible artifacts."""
    frame = load_profiles(INPUT_PATH)
    industrial_fraction = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential_fraction = profile_fraction(frame[RESIDENTIAL_COLUMN])
    pv_fraction = profile_fraction(frame[PV_COLUMN])
    results = [
        simulate_scenario(
            frame, alpha, industrial_fraction, residential_fraction, pv_fraction
        )
        for alpha in SCENARIO_MULTIPLIERS
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.concat([result.records for result in results], ignore_index=True).to_csv(
        RESULT_PATH, index=False
    )
    save_figure(results, FIGURE_PATH, MIN_VOLTAGE_PU, HB_BUS_NUMBER)

    benchmark = nw.case33bw()
    print(
        f"IEEE 33-bus retained load: {benchmark.load.p_mw.sum():.3f} MW / "
        f"{benchmark.load.q_mvar.sum():.3f} MVAr | slack={SLACK_VOLTAGE_PU:.2f} pu"
    )
    for result in results:
        records = result.records
        print(
            f"alpha={result.alpha:.1f} | Mode 2={int(records.mode2.sum())}/{len(records)} | "
            f"HB max={records.hbmps_mw.max():.3f} MW | "
            f"Vmin={records.vmin_base.min():.4f}->{records.vmin_hbmps.min():.4f} pu | "
            f"violations={int(records.viol_base.sum())}->{int(records.viol_hbmps.sum())}"
        )
    print(f"Saved: {RESULT_PATH}")
    print(f"Saved: {FIGURE_PATH}")


if __name__ == "__main__":
    main()
