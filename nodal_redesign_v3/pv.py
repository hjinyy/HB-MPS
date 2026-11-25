"""Map original PV to the feeder and curtail output at an explicit voltage cap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandapower as pp
import pandas as pd

from powerflow_validation import (
    INDUSTRIAL_COLUMN,
    PV_COLUMN,
    RESIDENTIAL_COLUMN,
    build_network,
    profile_fraction,
    solve_network,
)
from nodal_redesign_v2.experiment import Case, _ratings, _scale, _set_loads

PV_VOLTAGE_CEILING_PU: Final = 1.05
PV_DISPATCH_PRECISION_MW: Final = 0.001


@dataclass(frozen=True, slots=True)
class PVPlan:
    """Hourly PV potential, feasible dispatch and AC-flow diagnostics."""

    hourly: pd.DataFrame
    nameplate_mw: float
    scale_mw_per_raw_kwh: float

    @property
    def dispatch_mw(self) -> np.ndarray:
        return self.hourly.pv_dispatch_mw.to_numpy(dtype=float)


def _flow(net: pp.pandapowerNet, pv_mw: float) -> tuple[float, float, float]:
    """Return peak voltage, slack import and active line losses for one PV output."""
    net.sgen.loc[net.sgen.name.eq("PV"), "p_mw"] = pv_mw
    voltage, losses = solve_network(net)
    return float(voltage.max()), float(net.res_ext_grid.p_mw.sum()), losses


def plan_pv(frame: pd.DataFrame, case: Case) -> PVPlan:
    """Curtail scaled Bus 7 PV only when an hourly baseline exceeds 1.05 p.u."""
    net = build_network()
    ratings = _ratings(case, net)
    scale = _scale(case, frame, ratings)
    potential = frame[PV_COLUMN].to_numpy(dtype=float) * scale
    industrial = profile_fraction(frame[INDUSTRIAL_COLUMN])
    residential = profile_fraction(frame[RESIDENTIAL_COLUMN])
    base_load_indices = tuple(net.load.index)
    records: list[dict[str, float | int]] = []

    for t, requested_mw in enumerate(potential):
        _set_loads(
            net, base_load_indices, case.industrial_buses,
            float(industrial[t]), float(residential[t]), 0.0,
        )
        requested_mw = float(requested_mw)
        try:
            raw_vmax, raw_slack, _ = _flow(net, requested_mw)
        except (pp.LoadflowNotConverged, RuntimeError):
            raw_vmax, raw_slack = float("nan"), float("nan")
        if np.isfinite(raw_vmax) and raw_vmax <= PV_VOLTAGE_CEILING_PU:
            dispatch_mw = requested_mw
            vmax, slack, losses = raw_vmax, raw_slack, float(net.res_line.pl_mw.sum())
        else:
            low, high = 0.0, requested_mw
            while high - low > PV_DISPATCH_PRECISION_MW:
                midpoint = (low + high) / 2
                try:
                    midpoint_vmax, _, _ = _flow(net, midpoint)
                except (pp.LoadflowNotConverged, RuntimeError):
                    midpoint_vmax = float("inf")
                if midpoint_vmax <= PV_VOLTAGE_CEILING_PU:
                    low = midpoint
                else:
                    high = midpoint
            dispatch_mw = low
            vmax, slack, losses = _flow(net, dispatch_mw)
        if vmax > PV_VOLTAGE_CEILING_PU + 1e-7:
            raise AssertionError(f"Hour {t}: PV dispatch exceeds voltage ceiling")
        load_mw = float(ratings[0] * industrial[t] + ratings[1] * residential[t])
        records.append({
            "t": t,
            "pv_potential_mw": requested_mw,
            "pv_dispatch_mw": dispatch_mw,
            "pv_curtailed_mw": requested_mw - dispatch_mw,
            "total_load_mw": load_mw,
            "uncurtailed_vmax_pu": raw_vmax,
            "uncurtailed_slack_import_mw": raw_slack,
            "baseline_vmax_pu": vmax,
            "baseline_slack_import_mw": slack,
            "baseline_line_loss_mw": losses,
            "ac_export_surplus_mw": max(-slack, 0.0),
        })
    return PVPlan(pd.DataFrame.from_records(records), float(potential.max()), scale)


def screen_peak_siting(frame: pd.DataFrame, case: Case) -> pd.DataFrame:
    """Compare uncurtailed peak PV at Bus 7 and rating-weighted bus groups."""
    ratings = _ratings(case, build_network())
    scale = _scale(case, frame, ratings)
    peak_hour = int(np.argmax(frame[PV_COLUMN].to_numpy(dtype=float)))
    peak_mw = float(frame[PV_COLUMN].iloc[peak_hour]) * scale
    industrial = float(profile_fraction(frame[INDUSTRIAL_COLUMN])[peak_hour])
    residential = float(profile_fraction(frame[RESIDENTIAL_COLUMN])[peak_hour])
    records: list[dict[str, float | int | str]] = []
    configurations = (
        ("Bus 7", (7,)),
        ("Residential rating-weighted", case.residential_buses),
        ("All load buses rating-weighted", tuple(range(2, 34))),
    )
    for label, buses in configurations:
        net = build_network()
        _set_loads(net, tuple(net.load.index), case.industrial_buses,
                   industrial, residential, 0.0)
        weights = np.array([
            float(net.load.loc[net.load.bus.eq(bus - 1), "p_mw"].sum())
            for bus in buses
        ])
        weights /= weights.sum()
        for bus, weight in zip(buses, weights, strict=True):
            pp.create_sgen(net, bus - 1, p_mw=peak_mw * float(weight), q_mvar=0.0)
        voltage, losses = solve_network(net)
        records.append({
            "placement": label, "peak_hour": peak_hour, "pv_mw": peak_mw,
            "vmax_pu": float(voltage.max()),
            "slack_import_mw": float(net.res_ext_grid.p_mw.sum()),
            "line_loss_mw": losses,
        })
    return pd.DataFrame.from_records(records)
