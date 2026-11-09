"""Adapt the shared P1 physical model to the original Figure 6–9 columns."""

from __future__ import annotations

import pandas as pd

from emergency_dispatch import H2_KWH_PER_KG, VOLL_KRW_PER_KWH, run_scenario
from emergency_dispatch_model import Scenario, Step, Strategy
from emergency_validation import validate_run
from hb_inputs import Hour


def mode_and_action(step: Step) -> tuple[str, str]:
    """Retain the six legacy Mode 1/2 categories used by Figure 9."""
    if step.mode2:
        action = "HFC_DISCHARGE"
        if step.ess_emergency_kwh > 0:
            action += " & ESS_BACKUP"
        return "PHASE 2", action
    if step.main_h2_refill_kg > 0:
        return "H2_MAINTENANCE", "BUY_EXTERNAL_H2"
    if step.phase1_ess_kwh > 0:
        return "PHASE 1", "ESS_DISCHARGE"
    if step.pv_ess_charge_kwh > 0 or step.pv_p2g_kwh > 0:
        return (
            "SOLAR_CHARGE",
            "SOLAR_CHARGE & P2G" if step.pv_p2g_kwh > 0 else "SOLAR_CHARGE",
        )
    if step.grid_ess_charge_kwh > 0:
        return "GRID_CHARGE", "GRID_BUY"
    return "STANDBY", "WAIT"


def simulate_main_p1(
    frame: pd.DataFrame, alpha: float, trucks: int
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Run P1 on the original normalized input frame and map to old plotting keys."""
    hours = [
        Hour(
            timestamp=str(row["timestamp_dt"]),
            residential=float(row["load_A"]),
            industrial=float(row["load_B"]),
            solar=float(row["solar"]),
            lcoe=float(row["LCOE"]),
            smp=float(row["SMP"]),
            h2_price=float(row["h2_cost"]),
        )
        for _, row in frame.iterrows()
    ]
    run = run_scenario(hours, Scenario(alpha, trucks, Strategy.P1))
    validate_run(run)
    threshold = alpha * float(frame["load_B"].mean())
    records = []
    for (_, row), step in zip(frame.iterrows(), run.steps, strict=True):
        mode, action = mode_and_action(step)
        op_cost = step.h2_purchase_krw + step.grid_purchase_krw + step.ess_wear_krw
        records.append(
            {
                "timestamp": row["timestamp_dt"],
                "Load_B": float(row["load_B"]),
                "LCOE": step.lcoe_krw_per_kwh,
                "SMP": step.smp_krw_per_kwh,
                "Mode": mode,
                "Action": action,
                "ESS_SOC": step.soc_end * 100,
                "H2_LOH": step.main_h2_end_kg / (1500.0 / H2_KWH_PER_KG) * 100,
                "Revenue": step.revenue_krw,
                "Op_Cost": op_cost,
                "Net_Step_Profit": step.operating_net_krw,
                "Base_Penalty": step.demand_kwh * VOLL_KRW_PER_KWH,
                "HMEP_Penalty": step.unserved_kwh * VOLL_KRW_PER_KWH,
                "Avoided_Penalty": step.avoided_interruption_krw,
                "Active_Trucks": step.hfc_trucks_dispatched,
                "Required_Trucks": step.required_hfc_trucks,
                "Threshold": threshold,
                "Alpha": alpha,
                "HFC_Supply": step.hfc_kwh,
                "ESS_Emergency_Supply": step.ess_emergency_kwh,
                "ESS_Mode1_Supply": step.phase1_ess_kwh,
                "Unserved_Energy": step.unserved_kwh,
                "H2_External_kg": step.external_h2_kg,
                "Grid_Charge_kWh": step.grid_ess_charge_kwh,
                "ESS_Wear_Cost": step.ess_wear_krw,
            }
        )
    result = pd.DataFrame.from_records(records)
    mode2 = result["Mode"].eq("PHASE 2")
    summary = {
        "alpha": alpha,
        "available_trucks": trucks,
        "max_trucks": int(result["Active_Trucks"].max()),
        "max_required_trucks": int(result["Required_Trucks"].max()),
        "mode2_count": int(mode2.sum()),
        "avg_trucks_mode2": float(result.loc[mode2, "Active_Trucks"].mean())
        if mode2.any()
        else 0.0,
        "net_profit": float(result["Net_Step_Profit"].sum()),
        "base_penalty": float(result["Base_Penalty"].sum()),
        "avoided_penalty": float(result["Avoided_Penalty"].sum()),
        "unserved_kwh": float(result["Unserved_Energy"].sum()),
        "terminal_soc": run.terminal_soc,
        "terminal_loh": run.steps[-1].main_h2_end_kg / (1500.0 / H2_KWH_PER_KG),
    }
    return result, summary
