"""Physical checks and comparable metrics for all nodal redesign cases."""

from __future__ import annotations

import numpy as np
import pandas as pd

from emergency_dispatch import (
    ESS_CAPACITY,
    ESS_EFFICIENCY,
    ESS_MIN_SOC,
    H2_CAPACITY_KG,
    HFC_OUTPUT_KWH,
    P2G_KWH_PER_KG,
)
from powerflow_validation import (
    INDUSTRIAL_COLUMN,
    MIN_VOLTAGE_PU,
    RESIDENTIAL_COLUMN,
)
from severity_fleet import FLEET_SIZE

from .experiment import CaseRun


def validate_run(run: CaseRun) -> None:
    """Check every hour's fleet, nodal, AC and inventory balances."""
    result = run.result
    hourly, buses, trucks = result.hourly, result.buses, result.trucks
    if len(hourly) != 168 or len(buses) != 168 * 33 or len(trucks) != 168 * FLEET_SIZE:
        raise AssertionError("Incomplete 168-hour nodal outputs")
    if result.baseline_profiles.shape != (168, 33) or result.supported_profiles.shape != (168, 33):
        raise AssertionError("Voltage profile dimensions are wrong")
    if not np.isfinite(result.baseline_profiles).all() or not np.isfinite(result.supported_profiles).all():
        raise AssertionError("AC power flow returned a non-finite voltage")
    initial_types = buses.loc[buses.t.eq(0), "bus_type"].value_counts()
    if initial_types.get("Industrial", 0) != len(run.case.industrial_buses):
        raise AssertionError("Industrial bus count drifted")
    if initial_types.get("Residential", 0) != len(run.case.residential_buses):
        raise AssertionError("Residential bus count drifted")
    if not (buses.loc[buses.bus.eq(7), "bus_type"] == "Residential").all():
        raise AssertionError("PV/P2G Bus 7 must remain residential")
    if not (buses.loc[buses.bus.eq(9), "bus_type"] == "Residential").all():
        raise AssertionError("Grid charging Bus 9 must remain residential")
    if not (trucks.hfc_kwh <= HFC_OUTPUT_KWH + 1e-7).all():
        raise AssertionError("An HFC truck exceeded its rating")
    if not trucks.h2_end_kg.between(-1e-7, H2_CAPACITY_KG + 1e-7).all():
        raise AssertionError("A truck violated hydrogen tank limits")
    if not hourly.soc_end_pct.between(ESS_MIN_SOC * 100 - 1e-7, 100 + 1e-7).all():
        raise AssertionError("ESS SOC violated its limit")
    for t, row in enumerate(hourly.itertuples(index=False)):
        bus_hour = buses.loc[buses.t.eq(t)]
        truck_hour = trucks.loc[trucks.t.eq(t)]
        if not np.isclose(bus_hour.mode2_injection_mw.sum(), row.emergency_supply_mw):
            raise AssertionError(f"Hour {t}: emergency AC bus injection differs")
        if not np.isclose(bus_hour.mode1_injection_mw.sum(), row.mode1_supply_mw):
            raise AssertionError(f"Hour {t}: Mode 1 AC bus injection differs")
        if not np.isclose(bus_hour.residual_excess_mw.sum(), row.residual_excess_mw):
            raise AssertionError(f"Hour {t}: bus residuals differ")
        if not np.isclose(row.bus_excess_mw, row.emergency_supply_mw + row.residual_excess_mw):
            raise AssertionError(f"Hour {t}: assumed load excess does not balance")
        if not np.isclose(row.emergency_supply_mw, (row.hfc_kwh + row.ess_emergency_kwh) * run.scale_mw_per_raw_kwh):
            raise AssertionError(f"Hour {t}: raw-to-grid emergency scale differs")
        if not np.isclose(truck_hour.hfc_kwh.sum(), row.hfc_kwh):
            raise AssertionError(f"Hour {t}: HFC truck energy differs")
        if not np.isclose(truck_hour.ess_kwh.sum(), row.ess_emergency_kwh):
            raise AssertionError(f"Hour {t}: ESS truck energy differs")
        if not np.isclose(bus_hour.net_hbmps_mw.sum(), row.net_hbmps_mw):
            raise AssertionError(f"Hour {t}: net network injection differs")
        if row.mode1_active and row.mode2_trigger:
            raise AssertionError(f"Hour {t}: both operating modes active")
        if row.mode1_active and int(row.mode1_bus) not in run.case.residential_buses:
            raise AssertionError(f"Hour {t}: Mode 1 used a nonresidential bus")
        if not (bus_hour.loc[bus_hour.mode2_injection_mw.gt(1e-9), "bus"].isin(run.case.industrial_buses)).all():
            raise AssertionError(f"Hour {t}: Mode 2 used a nonindustrial bus")
        if not np.isclose(row.fleet_h2_end_kg, row.fleet_h2_start_kg + row.h2_refilled_kg
                          + row.pv_p2g_kwh / P2G_KWH_PER_KG - row.h2_consumed_kg,
                          atol=1e-7):
            raise AssertionError(f"Hour {t}: hydrogen inventory does not balance")
        soc_end_kwh = (
            row.soc_start_pct / 100 * ESS_CAPACITY
            - row.ess_withdrawal_kwh
            - row.phase1_ess_kwh / ESS_EFFICIENCY
            + (row.pv_ess_charge_kwh + row.grid_ess_charge_kwh) * ESS_EFFICIENCY
        )
        if not np.isclose(row.soc_end_pct / 100 * ESS_CAPACITY, soc_end_kwh, atol=1e-7):
            raise AssertionError(f"Hour {t}: ESS inventory does not balance")
        if not np.isclose(row.pv_use_mw, (row.pv_ess_charge_kwh + row.pv_p2g_kwh)
                          * run.scale_mw_per_raw_kwh):
            raise AssertionError(f"Hour {t}: PV use has duplicate scaling")


def summarize(run: CaseRun, frame: pd.DataFrame) -> dict[str, float | int | str]:
    """Keep raw asset energy and grid-scaled MWh in distinct columns."""
    result = run.result
    hourly, buses, trucks = result.hourly, result.buses, result.trucks
    baseline, supported = result.baseline_profiles, result.supported_profiles
    deficit_base = np.maximum(MIN_VOLTAGE_PU - baseline, 0.0)
    deficit_supported = np.maximum(MIN_VOLTAGE_PU - supported, 0.0)
    raw_industrial_peak_mw = float(frame[INDUSTRIAL_COLUMN].max()) / 1000
    raw_residential_peak_mw = float(frame[RESIDENTIAL_COLUMN].max()) / 1000
    mode2_vehicles = trucks.loc[trucks["mode"].eq("Mode 2") & trucks.bus.notna()]
    gain = supported - baseline
    return {
        "case_id": run.case.name,
        "alpha": result.alpha,
        "industrial_bus_count": len(run.case.industrial_buses),
        "residential_bus_count": len(run.case.residential_buses),
        "industrial_rating_mw": run.industrial_rating_mw,
        "residential_rating_mw": run.residential_rating_mw,
        "total_rating_mw": run.total_rating_mw,
        "industrial_load_scale_pct": run.industrial_rating_mw / raw_industrial_peak_mw * 100,
        "residential_load_scale_pct": run.residential_rating_mw / raw_residential_peak_mw * 100,
        "hb_mps_scale_pct": run.scale_mw_per_raw_kwh * 100_000,
        "total_grid_load_peak_mw": run.total_load_peak_mw,
        "baseline_ac_converged_hours": len(hourly),
        "supported_ac_converged_hours": len(hourly),
        "mode1_hours": int(hourly.mode1_active.sum()),
        "mode1_ess_mwh_raw": float(hourly.phase1_ess_kwh.sum()) / 1000,
        "mode1_ess_mwh_grid": float(hourly.mode1_supply_mw.sum()),
        "mode2_trigger_hours": int(hourly.mode2_trigger.sum()),
        "mode2_supply_hours": int(hourly.supply_active.sum()),
        "hfc_mwh_raw": float(hourly.hfc_kwh.sum()) / 1000,
        "ess_emergency_mwh_raw": float(hourly.ess_emergency_kwh.sum()) / 1000,
        "hfc_mwh_grid": float(hourly.hfc_kwh.sum()) * run.scale_mw_per_raw_kwh,
        "ess_emergency_mwh_grid": float(hourly.ess_emergency_kwh.sum()) * run.scale_mw_per_raw_kwh,
        "emergency_supply_mwh_grid": float(hourly.emergency_supply_mw.sum()),
        "industrial_excess_mwh_grid": float(hourly.bus_excess_mw.sum()),
        "residual_industrial_excess_mwh_grid": float(hourly.residual_excess_mw.sum()),
        "active_truck_hours": int(hourly.active_trucks.sum()),
        "truck_dispatches": len(mode2_vehicles),
        "unique_mode2_connection_buses": int(mode2_vehicles.bus.nunique()),
        "soc_min_pct": float(hourly.soc_end_pct.min()),
        "soc_end_pct": float(hourly.soc_end_pct.iloc[-1]),
        "loh_min_pct": float(trucks.loh_end_pct.min()),
        "main_loh_end_pct": float(hourly.main_loh_end_pct.iloc[-1]),
        "h2_consumed_kg": float(hourly.h2_consumed_kg.sum()),
        "h2_refilled_kg": float(hourly.h2_refilled_kg.sum()),
        "pv_ess_charge_mwh_raw": float(hourly.pv_ess_charge_kwh.sum()) / 1000,
        "grid_ess_charge_mwh_raw": float(hourly.grid_ess_charge_kwh.sum()) / 1000,
        "p2g_use_mwh_raw": float(hourly.pv_p2g_kwh.sum()) / 1000,
        "pv_ess_charge_mwh_grid": float(hourly.pv_ess_charge_kwh.sum()) * run.scale_mw_per_raw_kwh,
        "grid_ess_charge_mwh_grid": float(hourly.grid_ess_charge_kwh.sum()) * run.scale_mw_per_raw_kwh,
        "p2g_use_mwh_grid": float(hourly.pv_p2g_kwh.sum()) * run.scale_mw_per_raw_kwh,
        "raw_pv_surplus_mwh_grid": float(hourly.raw_pv_surplus_scaled_mw.sum()),
        "network_pv_surplus_mwh": float(hourly.network_pv_surplus_mw.sum()),
        "pv_surplus_shortfall_hours": int(hourly.pv_surplus_shortfall_mw.gt(1e-9).sum()),
        "pv_surplus_shortfall_mwh": float(hourly.pv_surplus_shortfall_mw.sum()),
        "worst_hour": result.worst_hour,
        "vmin_baseline_pu": float(baseline.min()),
        "vmin_supported_pu": float(supported.min()),
        "worst_hour_min_voltage_gain_pu": float(
            supported[result.worst_hour].min() - baseline[result.worst_hour].min()
        ),
        "voltage_violation_hours_baseline": int(np.any(deficit_base > 0, axis=1).sum()),
        "voltage_violation_hours_supported": int(np.any(deficit_supported > 0, axis=1).sum()),
        "voltage_violating_bus_hours_baseline": int(np.count_nonzero(deficit_base)),
        "voltage_violating_bus_hours_supported": int(np.count_nonzero(deficit_supported)),
        "cumulative_voltage_deficit_baseline_pu_bus_h": float(deficit_base.sum()),
        "cumulative_voltage_deficit_supported_pu_bus_h": float(deficit_supported.sum()),
        "line_losses_baseline_mwh": float(hourly.line_loss_baseline_mw.sum()),
        "line_losses_supported_mwh": float(hourly.line_loss_supported_mw.sum()),
        "mean_voltage_difference_pu": float(gain.mean()),
        "min_voltage_difference_pu": float(gain.min()),
        "max_voltage_difference_pu": float(gain.max()),
        "buses_with_any_voltage_violation_baseline": int(np.any(deficit_base > 0, axis=0).sum()),
        "buses_with_any_voltage_violation_supported": int(np.any(deficit_supported > 0, axis=0).sum()),
    }


def bus_voltage_summary(run: CaseRun) -> pd.DataFrame:
    baseline = run.result.baseline_profiles
    supported = run.result.supported_profiles
    return pd.DataFrame({
        "case_id": run.case.name,
        "alpha": run.result.alpha,
        "bus": np.arange(1, 34),
        "bus_type": ["Slack" if bus == 1 else "Industrial"
                     if bus in run.case.industrial_buses else "Residential"
                     for bus in range(1, 34)],
        "vmin_baseline_pu": baseline.min(axis=0),
        "vmin_supported_pu": supported.min(axis=0),
        "mean_voltage_difference_pu": (supported - baseline).mean(axis=0),
        "max_voltage_difference_pu": (supported - baseline).max(axis=0),
        "violation_hours_baseline": (baseline < MIN_VOLTAGE_PU).sum(axis=0),
        "violation_hours_supported": (supported < MIN_VOLTAGE_PU).sum(axis=0),
    })


def truck_deployment_summary(run: CaseRun) -> pd.DataFrame:
    trucks = run.result.trucks.copy()
    return (
        trucks.groupby(["case_id", "alpha", "truck", "mode", "bus"],
                       dropna=False, sort=True)
        .agg(hours=("t", "size"), hfc_kwh_raw=("hfc_kwh", "sum"),
             ess_kwh_raw=("ess_kwh", "sum"),
             mode1_ess_kwh_raw=("mode1_ess_kwh", "sum"))
        .reset_index()
    )
