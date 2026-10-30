"""Bus-by-hour voltage maps for P1 at alpha=1.3 on the IEEE 33-bus model.

The original feeder scaling and visual design remain; injection now uses the
actual five-truck P1 hourly HFC plus ESS supply.
"""

from __future__ import annotations

import csv
from typing import Final

import matplotlib
import numpy as np
import pandapower.networks as nw

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox

from emergency_dispatch import run_scenario
from emergency_dispatch_model import Scenario, Strategy
from hb_inputs import INPUT, load_hours
from p1_multibus_dispatch import allocate_p1_supply, validate_main_reference
from powerflow_validation import (
    AUX_BUS_NUMBER,
    HB_BUS_NUMBER,
    INDUSTRIAL_BUS_NUMBERS,
    INDUSTRIAL_COLUMN,
    INPUT_PATH,
    MAIN_REFERENCE_PATH,
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

ALPHA: Final = 1.3
OUTPUT_NAME: Final = "figure_13_powerflow_voltage_heatmap"
CSV_PATH: Final = OUTPUT_DIR / "powerflow_voltage_by_bus_hour.csv"


def calculate_voltages() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Solve both cases at every hour, retaining all 33 bus magnitudes."""
    frame = load_profiles(INPUT_PATH)
    industrial = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential = profile_fraction(frame[RESIDENTIAL_COLUMN])
    pv = profile_fraction(frame[PV_COLUMN])
    raw_industrial = frame[INDUSTRIAL_COLUMN].to_numpy(dtype=float)
    hours = load_hours(INPUT)
    operational = run_scenario(hours, Scenario(ALPHA, 5, Strategy.P1))
    validate_main_reference(operational, MAIN_REFERENCE_PATH)
    if len(operational.steps) != len(frame):
        raise ValueError("Operational and power-flow hours must align.")
    benchmark = nw.case33bw()
    industrial_buses = {bus - 1 for bus in INDUSTRIAL_BUS_NUMBERS}
    residential_buses = {bus - 1 for bus in RESIDENTIAL_BUS_NUMBERS}
    industrial_rating = float(
        benchmark.load.loc[benchmark.load.bus.isin(industrial_buses), "p_mw"].sum()
    )
    bus18_rating = float(
        benchmark.load.loc[benchmark.load.bus.eq(HB_BUS_NUMBER - 1), "p_mw"].sum()
    )
    bus33_rating = float(
        benchmark.load.loc[benchmark.load.bus.eq(AUX_BUS_NUMBER - 1), "p_mw"].sum()
    )
    injections, _ = allocate_p1_supply(
        hours, operational, bus18_rating / (bus18_rating + bus33_rating)
    )
    residential_rating = float(
        benchmark.load.loc[benchmark.load.bus.isin(residential_buses), "p_mw"].sum()
    )
    pv_rating = float(benchmark.load.p_mw.sum()) * PV_PENETRATION
    raw_peak = float(raw_industrial.max())
    base_net = build_network()
    hb_net = build_network()
    base_series: list[np.ndarray] = []
    hb_series: list[np.ndarray] = []

    for hour in range(len(frame)):
        mixed = (
            industrial_rating * industrial[hour]
            + residential_rating * residential[hour]
        ) / (industrial_rating + residential_rating)
        injection = injections[hour]
        hb18_mw = (
            (injection.hfc18_kwh + injection.ess18_kwh) / raw_peak * industrial_rating
        )
        hb33_mw = injection.hfc33_kwh / raw_peak * industrial_rating
        pv_mw = pv[hour] * pv_rating
        set_operating_point(
            base_net, industrial[hour], residential[hour], mixed, pv_mw, 0.0
        )
        set_operating_point(
            hb_net,
            industrial[hour],
            residential[hour],
            mixed,
            pv_mw,
            hb18_mw,
            hb33_mw,
        )
        base_series.append(solve_network(base_net)[0])
        hb_series.append(solve_network(hb_net)[0])

    return (
        np.stack(base_series, axis=1),
        np.stack(hb_series, axis=1),
        [str(timestamp) for timestamp in frame["timestamp"]],
    )


def save_artifacts(base: np.ndarray, hb: np.ndarray, timestamps: list[str]) -> None:
    """Save machine-readable nodal results and matched-scale heatmaps."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(
            ("alpha", "t", "timestamp", "bus", "base_vm_pu", "hb_vm_pu", "delta_vm_pu")
        )
        for hour, timestamp in enumerate(timestamps):
            for bus in range(33):
                writer.writerow(
                    (
                        ALPHA,
                        hour,
                        timestamp,
                        bus + 1,
                        base[bus, hour],
                        hb[bus, hour],
                        hb[bus, hour] - base[bus, hour],
                    )
                )

    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 12})
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), dpi=220, sharex=True)
    voltage_limits = (min(base.min(), hb.min()), max(base.max(), hb.max()))
    panels = (
        (base, "Baseline bus voltages", "viridis", voltage_limits),
        (hb, "HB-MPS bus voltages", "viridis", voltage_limits),
        (
            hb - base,
            "Voltage improvement (HB-MPS − baseline)",
            "YlGnBu",
            (0.0, max((hb - base).max(), 1e-6)),
        ),
    )
    for axis, (values, title, palette, limits) in zip(axes, panels, strict=True):
        artist = axis.imshow(
            values,
            aspect="auto",
            origin="lower",
            cmap=palette,
            extent=(-0.5, len(timestamps) - 0.5, 0.5, 33.5),
            vmin=limits[0],
            vmax=limits[1],
            interpolation="nearest",
        )
        axis.axhline(
            HB_BUS_NUMBER,
            color="black" if axis is axes[2] else "white",
            linestyle=":",
            linewidth=1.2,
        )
        axis.set_title(title, fontweight="bold", loc="left")
        axis.set_ylabel("Bus number")
        axis.set_yticks((1, 9, 18, 25, 33))
        fig.colorbar(
            artist,
            ax=axis,
            label="Voltage (p.u.)" if axis is not axes[2] else "Δ voltage (p.u.)",
            pad=0.012,
        )
    axes[-1].set_xticks(
        np.arange(0, 169, 24),
        ("Aug 1", "Aug 2", "Aug 3", "Aug 4", "Aug 5", "Aug 6", "Aug 7", "Aug 8"),
    )
    axes[-1].set_xlabel("Date (2025)")
    fig.tight_layout()
    fig.canvas.draw()
    # The changing colorbar tick widths alter bbox_inches="tight" by a few
    # pixels. Keep the archived Figure 13 canvas without moving any subplot.
    tight = fig.get_tightbbox(fig.canvas.get_renderer()).padded(0.1)
    target_width, target_height = 2693 / fig.dpi, 2164 / fig.dpi
    horizontal_pad = max((target_width - tight.width) / 2, 0.0)
    vertical_pad = max((target_height - tight.height) / 2, 0.0)
    canvas = Bbox.from_extents(
        tight.x0 - horizontal_pad,
        tight.y0 - vertical_pad,
        tight.x1 + horizontal_pad,
        tight.y1 + vertical_pad,
    )
    for suffix in ("png", "pdf"):
        fig.savefig(
            OUTPUT_DIR / f"{OUTPUT_NAME}.{suffix}", bbox_inches=canvas, pad_inches=0
        )
    plt.close(fig)


def main() -> None:
    """Reproduce and visualize spatial and temporal voltage response."""
    base, hb, timestamps = calculate_voltages()
    save_artifacts(base, hb, timestamps)
    print(f"Shape: {base.shape}; min voltage {base.min():.4f} -> {hb.min():.4f} p.u.")
    print(f"Maximum nodal gain: {(hb - base).max():.4f} p.u.; saved {CSV_PATH}")


if __name__ == "__main__":
    main()
