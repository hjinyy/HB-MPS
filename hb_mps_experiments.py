from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SystemConfig:
    data_path: Path
    output_dir: Path
    ess_capacity: float = 1500.0
    ess_emergency_output: float = 700.0
    ess_phase1_output: float = 700.0
    hfc_capacity_kwh: float = 1500.0
    hfc_rated_output: float = 500.0
    kwh_per_kg_h2: float = 16.65
    p2g_kwh_per_kg: float = 55.0
    ess_efficiency: float = 0.95
    ess_min_soc: float = 0.1
    ess_max_soc: float = 0.9
    init_ess_soc: float = 0.6
    init_hfc_loh: float = 0.8
    phase1_soc_limit: float = 0.3
    phase1_lcoe_percentile: float = 0.6  # 60th percentile threshold => dispatch opens for the top 40% LCOE hours
    h2_refuel_threshold: float = 0.6
    single_mode_refuel_threshold: float = 0.2
    h2_target_level: float = 0.9
    single_mode_h2_target: float = 0.5
    charge_smp_percentile: float = 0.25
    voll_a: float = -0.0000206
    voll_b: float = 0.0227011
    voll_c: float = 0.3018905
    simulation_step_min: float = 60.0
    voll_unit_scale: float = 1000.0
    truck_fuel_efficiency: float = 0.08
    distance_one_way: float = 1.7
    battery_wear_cost: float = 50.0
    h2_main_response_delay_min: float = 25.0
    h2_aux_response_delay_min: float = 55.0

    @property
    def max_h2_kg(self) -> float:
        return self.hfc_capacity_kwh / self.kwh_per_kg_h2

    @property
    def move_h2_cost(self) -> float:
        return self.truck_fuel_efficiency * self.distance_one_way


@dataclass(frozen=True)
class CaseDefinition:
    key: str
    label: str
    has_ess: bool
    has_hfc: bool
    policy: str
    allow_aux_trucks: bool = True


DEFAULT_CASES: tuple[CaseDefinition, ...] = (
    CaseDefinition("base_case", "Base Case", False, False, "base", False),
    CaseDefinition("ess_only", "ESS Only", True, False, "ess_only", False),
    CaseDefinition("h2_only", "H2 Only", False, True, "h2_only", True),
    CaseDefinition("hybrid_single_mode", "Hybrid Single-Mode", True, True, "single_mode", True),
    CaseDefinition("hybrid_dual_mode", "Hybrid Dual-Mode", True, True, "dual_mode", True),
)

CASE_COLORS = {
    "base_case": "#7f7f7f",
    "ess_only": "#1f77b4",
    "h2_only": "#ff7f0e",
    "hybrid_single_mode": "#9467bd",
    "hybrid_dual_mode": "#2ca02c",
}


def case_label_map() -> dict[str, str]:
    return {case.key: case.label for case in DEFAULT_CASES}


class MobileEnergySystem:
    def __init__(self, cfg: SystemConfig, case: CaseDefinition):
        self.cfg = cfg
        self.case = case
        self.ess_kwh = cfg.ess_capacity * cfg.init_ess_soc if case.has_ess else 0.0
        self.h2_kg = cfg.max_h2_kg * cfg.init_hfc_loh if case.has_hfc else 0.0
        self.history: list[dict] = []
        self.prev_emergency_active = False

    def get_soc(self) -> float:
        return 0.0 if not self.case.has_ess else self.ess_kwh / self.cfg.ess_capacity

    def get_loh(self) -> float:
        return 0.0 if not self.case.has_hfc else self.h2_kg / self.cfg.max_h2_kg

    def calculate_voll_unit_cost(self, duration_minutes: float) -> float:
        exponent = (
            self.cfg.voll_a * (duration_minutes ** 2)
            + self.cfg.voll_b * duration_minutes
            + self.cfg.voll_c
        )
        return math.exp(exponent) * self.cfg.voll_unit_scale

    def _dispatch_ess(self, required_kwh: float, discharge_cap: float) -> tuple[float, float]:
        if not self.case.has_ess:
            return 0.0, 0.0
        energy_available = max(0.0, self.ess_kwh - (self.cfg.ess_capacity * self.cfg.ess_min_soc))
        discharge_kwh = min(required_kwh, discharge_cap, energy_available)
        if discharge_kwh <= 0:
            return 0.0, 0.0
        self.ess_kwh -= discharge_kwh
        wear_cost = discharge_kwh * self.cfg.battery_wear_cost
        return discharge_kwh, wear_cost

    def _dispatch_h2_emergency(
        self,
        required_kwh: float,
        h2_cost: float,
        event_started: bool,
    ) -> tuple[float, float, int]:
        if not self.case.has_hfc or required_kwh <= 0:
            return 0.0, 0.0, 0

        trucks = max(1, math.ceil(required_kwh / self.cfg.hfc_rated_output)) if self.case.allow_aux_trucks else 1
        if event_started:
            main_factor = max(0.0, 1.0 - (self.cfg.h2_main_response_delay_min / self.cfg.simulation_step_min))
            aux_factor = max(0.0, 1.0 - (self.cfg.h2_aux_response_delay_min / self.cfg.simulation_step_min))
        else:
            main_factor = 1.0
            aux_factor = 1.0

        available_cap = (self.cfg.hfc_rated_output * main_factor) + max(0, trucks - 1) * self.cfg.hfc_rated_output * aux_factor
        discharge_kwh = min(required_kwh, available_cap)
        if discharge_kwh <= 0:
            return 0.0, 0.0, 0

        total_h2_consumed = discharge_kwh / self.cfg.kwh_per_kg_h2
        truck1_supply = min(discharge_kwh, self.cfg.hfc_rated_output * main_factor)
        truck1_h2_need = truck1_supply / self.cfg.kwh_per_kg_h2
        total_main_consumption = truck1_h2_need + self.cfg.move_h2_cost
        op_cost = 0.0

        if self.h2_kg >= total_main_consumption:
            self.h2_kg -= total_main_consumption
        else:
            shortage = total_main_consumption - self.h2_kg
            self.h2_kg = 0.0
            op_cost += shortage * h2_cost

        if trucks > 1:
            aux_h2_need = max(0.0, total_h2_consumed - truck1_h2_need)
            aux_move_need = (trucks - 1) * self.cfg.move_h2_cost
            op_cost += (aux_h2_need + aux_move_need) * h2_cost

        return discharge_kwh, op_cost, trucks

    def _dispatch_h2_economic(self, h2_cost: float, lcoe: float) -> tuple[float, float, float]:
        if not self.case.has_hfc:
            return 0.0, 0.0, 0.0
        available_h2_for_power = max(0.0, self.h2_kg - self.cfg.move_h2_cost)
        discharge_kwh = min(self.cfg.hfc_rated_output, available_h2_for_power * self.cfg.kwh_per_kg_h2)
        if discharge_kwh <= 0:
            return 0.0, 0.0, 0.0
        consumed_h2 = discharge_kwh / self.cfg.kwh_per_kg_h2
        self.h2_kg = max(0.0, self.h2_kg - consumed_h2 - self.cfg.move_h2_cost)
        revenue = discharge_kwh * lcoe
        op_cost = (consumed_h2 + self.cfg.move_h2_cost) * h2_cost
        return discharge_kwh, revenue, op_cost

    def _charge_assets(self, surplus_solar: float, smp: float, smp_low_threshold: float) -> tuple[str, str, dict[str, float]]:
        mode = "STANDBY"
        action = "WAIT"
        breakdown = {
            "ess_wear_cost": 0.0,
            "grid_energy_cost": 0.0,
            "solar_charge_kwh": 0.0,
            "grid_charge_kwh": 0.0,
            "p2g_kg": 0.0,
        }
        remaining_surplus = surplus_solar

        if remaining_surplus > 0:
            if self.case.has_ess and self.get_soc() < self.cfg.ess_max_soc:
                mode = "SOLAR_CHARGE"
                charge_cap = 300.0
                space_avail = (self.cfg.ess_capacity * self.cfg.ess_max_soc) - self.ess_kwh
                charge_kwh = min(remaining_surplus, charge_cap, max(0.0, space_avail))
                if charge_kwh > 0:
                    self.ess_kwh += charge_kwh * self.cfg.ess_efficiency
                    remaining_surplus -= charge_kwh
                    breakdown["solar_charge_kwh"] += charge_kwh
                    breakdown["ess_wear_cost"] += charge_kwh * self.cfg.battery_wear_cost
                    action = "SOLAR_CHARGE"

            if remaining_surplus > 0 and self.case.has_hfc and self.get_loh() < 1.0:
                produced_kg = remaining_surplus / self.cfg.p2g_kwh_per_kg
                space_kg = self.cfg.max_h2_kg - self.h2_kg
                real_production = min(produced_kg, max(0.0, space_kg))
                if real_production > 0:
                    self.h2_kg += real_production
                    breakdown["p2g_kg"] += real_production
                    mode = "SOLAR_CHARGE" if mode == "STANDBY" else mode
                    action = "P2G_ONLY" if action == "WAIT" else f"{action} & P2G"

        elif self.case.has_ess and smp <= smp_low_threshold and self.get_soc() < self.cfg.ess_max_soc:
            charge_cap = 300.0
            space = (self.cfg.ess_capacity * self.cfg.ess_max_soc) - self.ess_kwh
            charge_kwh = min(charge_cap, max(0.0, space))
            if charge_kwh > 0.1:
                mode = "GRID_CHARGE"
                action = "GRID_BUY"
                self.ess_kwh += charge_kwh * self.cfg.ess_efficiency
                breakdown["grid_charge_kwh"] += charge_kwh
                breakdown["grid_energy_cost"] += charge_kwh * smp
                breakdown["ess_wear_cost"] += charge_kwh * self.cfg.battery_wear_cost

        return mode, action, breakdown

    def _refuel(self, h2_cost: float, target_level: float) -> float:
        if not self.case.has_hfc:
            return 0.0
        target_kg = self.cfg.max_h2_kg * target_level
        needed_kg = max(0.0, target_kg - self.h2_kg)
        if needed_kg <= 0:
            return 0.0
        self.h2_kg += needed_kg
        return needed_kg * h2_cost

    def run_step(
        self,
        timestamp: pd.Timestamp,
        load_a: float,
        load_b: float,
        lcoe: float,
        smp: float,
        solar: float,
        h2_cost: float,
        b_load_mean: float,
        alpha: float,
        lcoe_high_threshold: float,
        smp_low_threshold: float,
    ) -> None:
        mode = "STANDBY"
        action = "WAIT"

        ess_emergency_supply = 0.0
        h2_emergency_supply = 0.0
        ess_arbitrage_supply = 0.0
        h2_arbitrage_supply = 0.0
        revenue = 0.0
        ess_revenue = 0.0
        h2_revenue = 0.0
        ess_wear_cost = 0.0
        h2_op_cost = 0.0
        grid_energy_cost = 0.0
        refuel_cost = 0.0
        active_trucks = 0
        solar_charge_kwh = 0.0
        grid_charge_kwh = 0.0
        p2g_kg = 0.0

        spike_threshold = b_load_mean * alpha
        excess_load_base = max(0.0, load_b - spike_threshold)
        voll_unit_price = self.calculate_voll_unit_cost(self.cfg.simulation_step_min) if excess_load_base > 0 else 0.0
        base_penalty_cost = excess_load_base * voll_unit_price
        surplus_solar = solar - (load_a + load_b)
        emergency_event = excess_load_base > 0
        event_started = emergency_event and not self.prev_emergency_active

        if self.case.policy == "base":
            pass
        elif self.case.policy == "dual_mode":
            if emergency_event:
                mode = "PHASE 2"
                ess_emergency_supply, ess_wear_delta = self._dispatch_ess(excess_load_base, self.cfg.ess_emergency_output)
                ess_wear_cost += ess_wear_delta
                remaining = max(0.0, excess_load_base - ess_emergency_supply)
                h2_emergency_supply, h2_cost_step, active_trucks = self._dispatch_h2_emergency(remaining, h2_cost, event_started)
                h2_op_cost += h2_cost_step
                if ess_emergency_supply > 0 or h2_emergency_supply > 0:
                    action = "ESS+HFC_EMERGENCY" if ess_emergency_supply > 0 and h2_emergency_supply > 0 else (
                        "ESS_EMERGENCY" if ess_emergency_supply > 0 else "HFC_EMERGENCY"
                    )
            elif self.case.has_hfc and self.get_loh() < self.cfg.h2_refuel_threshold:
                mode = "H2_MAINTENANCE"
                action = "BUY_EXTERNAL_H2"
                refuel_cost += self._refuel(h2_cost, self.cfg.h2_target_level)
            elif self.case.has_ess and lcoe >= lcoe_high_threshold and self.get_soc() >= self.cfg.phase1_soc_limit:
                mode = "PHASE 1"
                ess_arbitrage_supply, ess_wear_delta = self._dispatch_ess(self.cfg.ess_phase1_output, self.cfg.ess_phase1_output)
                ess_wear_cost += ess_wear_delta
                if ess_arbitrage_supply > 0:
                    ess_revenue = ess_arbitrage_supply * self.cfg.ess_efficiency * lcoe
                    revenue += ess_revenue
                    action = "ESS_DISCHARGE"
            else:
                mode, action, charge_breakdown = self._charge_assets(surplus_solar, smp, smp_low_threshold)
                ess_wear_cost += charge_breakdown["ess_wear_cost"]
                grid_energy_cost += charge_breakdown["grid_energy_cost"]
                solar_charge_kwh += charge_breakdown["solar_charge_kwh"]
                grid_charge_kwh += charge_breakdown["grid_charge_kwh"]
                p2g_kg += charge_breakdown["p2g_kg"]
        elif self.case.policy == "single_mode":
            if emergency_event:
                mode = "SINGLE_MODE_EVENT"
                ess_emergency_supply, ess_wear_delta = self._dispatch_ess(excess_load_base, self.cfg.ess_emergency_output)
                ess_wear_cost += ess_wear_delta
                remaining = max(0.0, excess_load_base - ess_emergency_supply)
                h2_emergency_supply, h2_cost_step, active_trucks = self._dispatch_h2_emergency(remaining, h2_cost, event_started)
                h2_op_cost += h2_cost_step
                action = "UNIFIED_EVENT_DISPATCH"
            elif lcoe >= lcoe_high_threshold:
                mode = "SINGLE_MODE_DISCHARGE"
                ess_arbitrage_supply, ess_wear_delta = self._dispatch_ess(self.cfg.ess_phase1_output, self.cfg.ess_phase1_output)
                ess_wear_cost += ess_wear_delta
                if ess_arbitrage_supply > 0:
                    ess_revenue = ess_arbitrage_supply * self.cfg.ess_efficiency * lcoe
                    revenue += ess_revenue
                h2_arbitrage_supply, h2_revenue, h2_cost_step = self._dispatch_h2_economic(h2_cost, lcoe)
                revenue += h2_revenue
                h2_op_cost += h2_cost_step
                action = "UNIFIED_DISCHARGE"
            elif self.case.has_hfc and self.get_loh() < self.cfg.single_mode_refuel_threshold:
                mode = "LOW_RESERVE_REFUEL"
                action = "BUY_EXTERNAL_H2"
                refuel_cost += self._refuel(h2_cost, self.cfg.single_mode_h2_target)
            else:
                mode, action, charge_breakdown = self._charge_assets(surplus_solar, smp, smp_low_threshold)
                ess_wear_cost += charge_breakdown["ess_wear_cost"]
                grid_energy_cost += charge_breakdown["grid_energy_cost"]
                solar_charge_kwh += charge_breakdown["solar_charge_kwh"]
                grid_charge_kwh += charge_breakdown["grid_charge_kwh"]
                p2g_kg += charge_breakdown["p2g_kg"]
        elif self.case.policy == "ess_only":
            if emergency_event:
                mode = "ESS_EVENT"
                ess_emergency_supply, ess_wear_delta = self._dispatch_ess(excess_load_base, self.cfg.ess_emergency_output)
                ess_wear_cost += ess_wear_delta
                action = "ESS_EMERGENCY" if ess_emergency_supply > 0 else "WAIT"
            elif lcoe >= lcoe_high_threshold and self.get_soc() >= self.cfg.phase1_soc_limit:
                mode = "ESS_ARBITRAGE"
                ess_arbitrage_supply, ess_wear_delta = self._dispatch_ess(self.cfg.ess_phase1_output, self.cfg.ess_phase1_output)
                ess_wear_cost += ess_wear_delta
                if ess_arbitrage_supply > 0:
                    ess_revenue = ess_arbitrage_supply * self.cfg.ess_efficiency * lcoe
                    revenue += ess_revenue
                    action = "ESS_DISCHARGE"
            else:
                mode, action, charge_breakdown = self._charge_assets(surplus_solar, smp, smp_low_threshold)
                ess_wear_cost += charge_breakdown["ess_wear_cost"]
                grid_energy_cost += charge_breakdown["grid_energy_cost"]
                solar_charge_kwh += charge_breakdown["solar_charge_kwh"]
                grid_charge_kwh += charge_breakdown["grid_charge_kwh"]
        elif self.case.policy == "h2_only":
            if emergency_event:
                mode = "H2_EVENT"
                h2_emergency_supply, h2_cost_step, active_trucks = self._dispatch_h2_emergency(excess_load_base, h2_cost, event_started)
                h2_op_cost += h2_cost_step
                action = "HFC_EMERGENCY" if h2_emergency_supply > 0 else "WAIT"
            elif self.get_loh() < self.cfg.h2_refuel_threshold:
                mode = "H2_MAINTENANCE"
                action = "BUY_EXTERNAL_H2"
                refuel_cost += self._refuel(h2_cost, self.cfg.h2_target_level)
            else:
                mode, action, charge_breakdown = self._charge_assets(surplus_solar, smp, smp_low_threshold)
                p2g_kg += charge_breakdown["p2g_kg"]
        else:
            raise ValueError(f"Unknown policy: {self.case.policy}")

        emergency_supply = ess_emergency_supply + h2_emergency_supply
        total_opex = ess_wear_cost + h2_op_cost + grid_energy_cost + refuel_cost
        residual_unserved = max(0.0, excess_load_base - emergency_supply)
        case_penalty = residual_unserved * voll_unit_price
        avoided_penalty = base_penalty_cost - case_penalty
        incremental_value_vs_base = avoided_penalty + (revenue - total_opex)

        self.history.append(
            {
                "timestamp": timestamp,
                "case_key": self.case.key,
                "case_label": self.case.label,
                "alpha": alpha,
                "Load_A": load_a,
                "Load_B": load_b,
                "LCOE": lcoe,
                "SMP": smp,
                "Solar": solar,
                "Mode": mode,
                "Action": action,
                "ESS_SOC": self.get_soc() * 100,
                "H2_LOH": self.get_loh() * 100,
                "Revenue": revenue,
                "ESS_Revenue": ess_revenue,
                "H2_Revenue": h2_revenue,
                "Op_Cost": total_opex,
                "ESS_Wear_Cost": ess_wear_cost,
                "H2_Op_Cost": h2_op_cost,
                "Grid_Energy_Cost": grid_energy_cost,
                "Refuel_Cost": refuel_cost,
                "Net_Step_Profit": revenue - total_opex,
                "Base_Penalty": base_penalty_cost,
                "Case_Penalty": case_penalty,
                "Avoided_Penalty": avoided_penalty,
                "Emergency_Supply": emergency_supply,
                "ESS_Emergency_Supply": ess_emergency_supply,
                "H2_Emergency_Supply": h2_emergency_supply,
                "ESS_Arbitrage_Supply": ess_arbitrage_supply,
                "H2_Arbitrage_Supply": h2_arbitrage_supply,
                "Unserved_Energy": residual_unserved,
                "Active_Trucks": active_trucks,
                "Spike_Threshold": spike_threshold,
                "Incremental_Value_vs_Base": incremental_value_vs_base,
                "Solar_Charge_kWh": solar_charge_kwh,
                "Grid_Charge_kWh": grid_charge_kwh,
                "P2G_kg": p2g_kg,
                "Event_Started": event_started,
                "ESS_Market_Profit": ess_revenue - ess_wear_cost - grid_energy_cost,
            }
        )
        self.prev_emergency_active = emergency_event


def load_input_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    col_map = {
        "주택용 전력사용량(kWh)": "load_A",
        "산업용 전력사용량(kWh)": "load_B",
        "LCOE=SMP+REC(원/kWh)": "LCOE",
        "E: 태양광 발전량(kWh)": "solar",
        "SMP(원/kWh)": "SMP",
        "수소 외부계통 충전 비용(원/kg)": "h2_cost",
        "날짜": "date",
        "시간": "hour",
    }
    df = df.rename(columns=col_map)

    numeric_cols = ["date", "hour", "load_A", "load_B", "LCOE", "SMP", "solar", "h2_cost"]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "hour", "load_A", "load_B"])
    base_dates = pd.to_datetime(df["date"].astype(int).astype(str), format="%Y%m%d", errors="coerce")
    time_deltas = pd.to_timedelta(df["hour"] - 1, unit="h")
    df["timestamp_dt"] = base_dates + time_deltas
    df = df.dropna(subset=["timestamp_dt"])
    df = df.sort_values("timestamp_dt").reset_index(drop=True)

    for col in ["LCOE", "SMP", "solar", "h2_cost"]:
        df[col] = df[col].fillna(0.0)

    return df


def summarize_result(result_df: pd.DataFrame) -> dict:
    ess_market_profit = (
        result_df["ESS_Revenue"].sum()
        - result_df["ESS_Wear_Cost"].sum()
        - result_df["Grid_Energy_Cost"].sum()
    )
    return {
        "case_key": result_df["case_key"].iloc[0],
        "case_label": result_df["case_label"].iloc[0],
        "alpha": float(result_df["alpha"].iloc[0]),
        "total_revenue": result_df["Revenue"].sum(),
        "ess_revenue": result_df["ESS_Revenue"].sum(),
        "h2_revenue": result_df["H2_Revenue"].sum(),
        "total_opex": result_df["Op_Cost"].sum(),
        "ess_wear_cost": result_df["ESS_Wear_Cost"].sum(),
        "h2_op_cost": result_df["H2_Op_Cost"].sum(),
        "grid_energy_cost": result_df["Grid_Energy_Cost"].sum(),
        "refuel_cost": result_df["Refuel_Cost"].sum(),
        "ess_market_profit": ess_market_profit,
        "net_profit": result_df["Net_Step_Profit"].sum(),
        "base_penalty": result_df["Base_Penalty"].sum(),
        "case_penalty": result_df["Case_Penalty"].sum(),
        "avoided_penalty": result_df["Avoided_Penalty"].sum(),
        "unserved_energy": result_df["Unserved_Energy"].sum(),
        "emergency_supply": result_df["Emergency_Supply"].sum(),
        "ess_emergency_supply": result_df["ESS_Emergency_Supply"].sum(),
        "h2_emergency_supply": result_df["H2_Emergency_Supply"].sum(),
        "ess_arbitrage_supply": result_df["ESS_Arbitrage_Supply"].sum(),
        "h2_arbitrage_supply": result_df["H2_Arbitrage_Supply"].sum(),
        "incremental_value_vs_base": result_df["Incremental_Value_vs_Base"].sum(),
        "phase2_events": int((result_df["Base_Penalty"] > 0).sum()),
        "active_truck_max": int(result_df["Active_Trucks"].max()),
        "final_soc": float(result_df["ESS_SOC"].iloc[-1]),
        "final_loh": float(result_df["H2_LOH"].iloc[-1]),
    }


def run_case(df: pd.DataFrame, cfg: SystemConfig, case: CaseDefinition, alpha: float) -> tuple[pd.DataFrame, dict]:
    lcoe_high_threshold = df["LCOE"].quantile(cfg.phase1_lcoe_percentile)
    smp_low_threshold = df["SMP"].quantile(cfg.charge_smp_percentile)
    b_load_mean = df["load_B"].mean()

    system = MobileEnergySystem(cfg, case)
    for row in df.itertuples(index=False):
        system.run_step(
            timestamp=row.timestamp_dt,
            load_a=float(row.load_A),
            load_b=float(row.load_B),
            lcoe=float(row.LCOE),
            smp=float(row.SMP),
            solar=float(row.solar),
            h2_cost=float(row.h2_cost),
            b_load_mean=float(b_load_mean),
            alpha=float(alpha),
            lcoe_high_threshold=float(lcoe_high_threshold),
            smp_low_threshold=float(smp_low_threshold),
        )

    result_df = pd.DataFrame(system.history)
    summary = summarize_result(result_df)
    return result_df, summary


def run_alpha_sweep(
    df: pd.DataFrame,
    cfg: SystemConfig,
    alphas: Sequence[float],
    cases: Sequence[CaseDefinition] = DEFAULT_CASES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trace_frames: list[pd.DataFrame] = []
    summary_rows: list[dict] = []
    trace_dir = cfg.output_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    for alpha in alphas:
        for case in cases:
            result_df, summary = run_case(df, cfg, case, alpha)
            trace_frames.append(result_df)
            summary_rows.append(summary)
            result_df.to_csv(trace_dir / f"{case.key}__alpha_{alpha:.2f}.csv", index=False)

    summary_df = pd.DataFrame(summary_rows).sort_values(["alpha", "case_key"]).reset_index(drop=True)
    all_traces_df = pd.concat(trace_frames, ignore_index=True)
    return all_traces_df, summary_df


def case_order_labels(summary_df: pd.DataFrame) -> list[str]:
    existing = summary_df["case_label"].unique().tolist()
    ordered = [case.label for case in DEFAULT_CASES if case.label in existing]
    extras = [label for label in existing if label not in ordered]
    return ordered + extras


def mkrw(series: pd.Series | float) -> pd.Series | float:
    return series / 1_000_000.0


def mwh(series: pd.Series | float) -> pd.Series | float:
    return series / 1_000.0


def _color_for_label(label: str) -> str:
    reverse = {case.label: case.key for case in DEFAULT_CASES}
    key = reverse.get(label, label)
    return CASE_COLORS.get(key, "#4c72b0")


def annotate_bars(ax: plt.Axes, fmt: str = "{:.1f}") -> None:
    for patch in ax.patches:
        width = patch.get_width() if hasattr(patch, "get_width") else 0.0
        height = patch.get_height() if hasattr(patch, "get_height") else 0.0
        if abs(width) >= abs(height):
            value = width
            ax.text(
                width + (0.02 * max(1.0, abs(width))),
                patch.get_y() + patch.get_height() / 2,
                fmt.format(value),
                va="center",
                fontsize=8,
            )
        else:
            value = height
            ax.text(
                patch.get_x() + patch.get_width() / 2,
                height + (0.02 * max(1.0, abs(height))),
                fmt.format(value),
                ha="center",
                fontsize=8,
            )


def _resolve_story_alpha(available_alphas: Sequence[float], preferred: Sequence[float] | float) -> float:
    available = sorted({round(float(alpha), 6) for alpha in available_alphas})
    if not available:
        raise ValueError("At least one alpha is required to choose story figures")

    preferred_values = [float(preferred)] if isinstance(preferred, (int, float)) else [float(alpha) for alpha in preferred]
    for target in preferred_values:
        for alpha in available:
            if round(alpha, 6) == round(target, 6):
                return float(alpha)

    target = preferred_values[0]
    return float(min(available, key=lambda alpha: (abs(alpha - target), alpha)))


def resolve_story_alphas(available_alphas: Sequence[float]) -> dict[str, float]:
    return {
        "low": _resolve_story_alpha(available_alphas, [1.20, 1.30]),
        "transition": _resolve_story_alpha(available_alphas, 1.50),
        "high": _resolve_story_alpha(available_alphas, 1.80),
    }


def plot_case_comparison(summary_df: pd.DataFrame, alpha: float, figure_dir: Path) -> None:
    alpha_df = summary_df.loc[summary_df["alpha"].round(6) == round(alpha, 6)].copy()
    if alpha_df.empty:
        return
    order = case_order_labels(alpha_df)
    alpha_df["case_label"] = pd.Categorical(alpha_df["case_label"], categories=order, ordered=True)
    alpha_df = alpha_df.sort_values("case_label")
    colors = [_color_for_label(label) for label in alpha_df["case_label"].astype(str)]

    fig, axes = plt.subplots(2, 2, figsize=(15, 9), dpi=220)
    plots = [
        ("incremental_value_vs_base", "Incremental Value vs Base", "M KRW", mkrw, "{:.1f}"),
        ("avoided_penalty", "Avoided Outage Cost", "M KRW", mkrw, "{:.1f}"),
        ("net_profit", "Net Profit", "M KRW", mkrw, "{:.1f}"),
        ("unserved_energy", "Residual Unserved Energy", "MWh", mwh, "{:.1f}"),
    ]
    for ax, (metric, title, xlabel, transform, fmt) in zip(axes.flat, plots):
        values = transform(alpha_df[metric])
        ax.barh(alpha_df["case_label"].astype(str), values, color=colors)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel(xlabel)
        ax.grid(True, axis="x", linestyle="--", alpha=0.35)
        annotate_bars(ax, fmt)
    fig.suptitle(f"Story comparison at alpha={alpha:.2f}", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(figure_dir / f"case_comparison_alpha_{alpha:.2f}.png", bbox_inches="tight")
    plt.close(fig)


def plot_alpha_heatmap(summary_df: pd.DataFrame, figure_dir: Path) -> None:
    metrics = [
        ("incremental_value_vs_base", "Incremental Value vs Base (M KRW)", mkrw),
        ("net_profit", "Net Profit (M KRW)", mkrw),
        ("unserved_energy", "Residual Unserved Energy (MWh)", mwh),
    ]
    cases = [case.label for case in DEFAULT_CASES if case.label in summary_df["case_label"].unique()]
    alphas = sorted(summary_df["alpha"].unique())

    fig, axes = plt.subplots(1, 3, figsize=(17, 5), dpi=220)
    for ax, (metric, title, transform) in zip(axes, metrics):
        pivot = summary_df.pivot(index="case_label", columns="alpha", values=metric).reindex(cases)
        data = transform(pivot).values.astype(float)
        im = ax.imshow(data, aspect="auto", cmap="viridis")
        ax.set_title(title, fontweight="bold")
        ax.set_xticks(range(len(alphas)), [f"{a:.2f}" for a in alphas])
        ax.set_yticks(range(len(cases)), cases)
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                text_color = "white" if np.nan_to_num(data[i, j]) < np.nanmax(data) * 0.65 else "black"
                ax.text(j, i, f"{data[i, j]:.1f}", ha="center", va="center", color=text_color, fontsize=8)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle("Alpha sweep heatmap (easy ranking view)", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(figure_dir / "alpha_heatmap.png", bbox_inches="tight")
    plt.close(fig)


def plot_hybrid_necessity(summary_df: pd.DataFrame, alpha: float, figure_dir: Path) -> None:
    subset = summary_df[
        (summary_df["alpha"].round(6) == round(alpha, 6))
        & (summary_df["case_key"].isin(["ess_only", "h2_only", "hybrid_dual_mode"]))
    ].copy()
    if subset.empty:
        return
    order = [case_label_map()[k] for k in ["ess_only", "h2_only", "hybrid_dual_mode"] if case_label_map()[k] in subset["case_label"].values]
    subset["case_label"] = pd.Categorical(subset["case_label"], categories=order, ordered=True)
    subset = subset.sort_values("case_label")
    colors = [_color_for_label(label) for label in subset["case_label"].astype(str)]

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=220)

    labels = subset["case_label"].astype(str).tolist()
    ess_support = np.asarray(mwh(subset["ess_emergency_supply"]), dtype=float)
    h2_support = np.asarray(mwh(subset["h2_emergency_supply"]), dtype=float)
    x = np.arange(len(labels))
    axes[0, 0].bar(x, ess_support, color="#1f77b4", label="ESS support")
    axes[0, 0].bar(x, h2_support, bottom=ess_support, color="#ff7f0e", label="H2 support")
    axes[0, 0].set_title("Emergency energy served", fontweight="bold")
    axes[0, 0].set_ylabel("MWh")
    axes[0, 0].set_xticks(x, labels, rotation=15)
    for idx, total in enumerate(ess_support + h2_support):
        axes[0, 0].text(idx, total + 1, f"{total:.1f}", ha="center", fontsize=8)
    axes[0, 0].legend(loc="upper right")

    axes[0, 1].bar(subset["case_label"].astype(str), mkrw(subset["avoided_penalty"]), color=colors)
    axes[0, 1].set_title("Resilience value (avoided outage cost)", fontweight="bold")
    axes[0, 1].set_ylabel("M KRW")
    axes[0, 1].tick_params(axis="x", rotation=15)
    annotate_bars(axes[0, 1], "{:.1f}")

    axes[1, 0].bar(subset["case_label"].astype(str), mkrw(subset["ess_market_profit"]), color=colors)
    axes[1, 0].axhline(0, color="black", linewidth=1)
    axes[1, 0].set_title("ESS market-profit contribution", fontweight="bold")
    axes[1, 0].set_ylabel("M KRW")
    axes[1, 0].tick_params(axis="x", rotation=15)
    annotate_bars(axes[1, 0], "{:.1f}")

    axes[1, 1].bar(subset["case_label"].astype(str), mkrw(subset["incremental_value_vs_base"]), color=colors)
    axes[1, 1].set_title("Incremental value vs base", fontweight="bold")
    axes[1, 1].set_ylabel("M KRW")
    axes[1, 1].tick_params(axis="x", rotation=15)
    annotate_bars(axes[1, 1], "{:.1f}")

    fig.suptitle(
        f"Why hybrid? H2 covers resilience, ESS adds market value at alpha={alpha:.2f}",
        fontsize=15,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.92))
    fig.savefig(figure_dir / "hybrid_necessity.png", bbox_inches="tight")
    plt.close(fig)


def plot_dual_mode_justification(summary_df: pd.DataFrame, alpha: float, figure_dir: Path) -> None:
    subset = summary_df[
        (summary_df["alpha"].round(6) == round(alpha, 6))
        & (summary_df["case_key"].isin(["hybrid_single_mode", "hybrid_dual_mode"]))
    ].copy()
    if subset.empty:
        return
    order = [case_label_map()[k] for k in ["hybrid_single_mode", "hybrid_dual_mode"] if case_label_map()[k] in subset["case_label"].values]
    subset["case_label"] = pd.Categorical(subset["case_label"], categories=order, ordered=True)
    subset = subset.sort_values("case_label")

    components = ["avoided_penalty", "total_revenue", "total_opex", "incremental_value_vs_base"]
    display = ["Avoided outage", "Revenue", "OpEx", "Incremental value vs base"]
    transformed = pd.DataFrame(index=display)
    for _, row in subset.iterrows():
        transformed[row["case_label"]] = [
            mkrw(row["avoided_penalty"]),
            mkrw(row["total_revenue"]),
            -mkrw(row["total_opex"]),
            mkrw(row["incremental_value_vs_base"]),
        ]

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), dpi=220)
    transformed.plot(kind="bar", ax=axes[0], color=[_color_for_label(label) for label in transformed.columns])
    axes[0].set_title("Single vs Dual: value composition", fontweight="bold")
    axes[0].set_ylabel("M KRW")
    axes[0].tick_params(axis="x", rotation=15)

    dual = subset.loc[subset["case_key"] == "hybrid_dual_mode"].iloc[0]
    single = subset.loc[subset["case_key"] == "hybrid_single_mode"].iloc[0]
    delta = pd.Series({
        "Avoided outage": dual["avoided_penalty"] - single["avoided_penalty"],
        "Revenue": dual["total_revenue"] - single["total_revenue"],
        "OpEx": -(dual["total_opex"] - single["total_opex"]),
        "Incremental value vs base": dual["incremental_value_vs_base"] - single["incremental_value_vs_base"],
    })
    delta_colors = ["#2ca02c" if v >= 0 else "#d62728" for v in delta.values]
    axes[1].bar(delta.index, mkrw(delta.values), color=delta_colors)
    axes[1].axhline(0, color="black", linewidth=1)
    axes[1].set_title("Dual minus Single", fontweight="bold")
    axes[1].set_ylabel("M KRW")
    axes[1].tick_params(axis="x", rotation=15)
    annotate_bars(axes[1], "{:.1f}")

    fig.suptitle(f"Why dual-mode? Clear delta view at alpha={alpha:.2f}", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(figure_dir / "dual_mode_justification.png", bbox_inches="tight")
    plt.close(fig)


def plot_event_zoom(all_traces_df: pd.DataFrame, alpha: float, figure_dir: Path) -> None:
    alpha_mask = all_traces_df["alpha"].round(6) == round(alpha, 6)
    hybrid = all_traces_df[alpha_mask & (all_traces_df["case_key"] == "hybrid_dual_mode")].copy()
    if hybrid.empty:
        return

    event_rows = hybrid[hybrid["Base_Penalty"] > 0]
    if event_rows.empty:
        return
    peak_idx = (event_rows["Load_B"] - event_rows["Spike_Threshold"]).idxmax()
    peak_time = hybrid.loc[peak_idx, "timestamp"]
    window_start = peak_time - pd.Timedelta(hours=18)
    window_end = peak_time + pd.Timedelta(hours=18)

    window = all_traces_df[alpha_mask & (all_traces_df["timestamp"] >= window_start) & (all_traces_df["timestamp"] <= window_end)].copy()
    hybrid_window = window[window["case_key"] == "hybrid_dual_mode"]
    ess_window = window[window["case_key"] == "ess_only"]
    h2_window = window[window["case_key"] == "h2_only"]
    event_bar_width = pd.Timedelta(minutes=50)

    fig, axes = plt.subplots(3, 1, figsize=(15, 9), dpi=220, sharex=True)
    axes[0].plot(hybrid_window["timestamp"], hybrid_window["Load_B"], color="gray", label="Industrial load")
    axes[0].plot(hybrid_window["timestamp"], hybrid_window["Spike_Threshold"], linestyle="--", color="red", label="Threshold")
    axes[0].bar(
        hybrid_window["timestamp"],
        hybrid_window["ESS_Emergency_Supply"],
        width=event_bar_width,
        color="#1f77b4",
        alpha=0.6,
        label="ESS support",
    )
    axes[0].bar(
        hybrid_window["timestamp"],
        hybrid_window["H2_Emergency_Supply"],
        width=event_bar_width,
        bottom=hybrid_window["ESS_Emergency_Supply"],
        color="#ff7f0e",
        alpha=0.6,
        label="H2 support",
    )
    axes[0].set_title("Event zoom: load, threshold, and hybrid support", fontweight="bold")
    axes[0].legend(loc="upper left")

    axes[1].plot(ess_window["timestamp"], mwh(ess_window["Unserved_Energy"]), label="ESS only", color=CASE_COLORS["ess_only"])
    axes[1].plot(h2_window["timestamp"], mwh(h2_window["Unserved_Energy"]), label="H2 only", color=CASE_COLORS["h2_only"])
    axes[1].plot(hybrid_window["timestamp"], mwh(hybrid_window["Unserved_Energy"]), label="Hybrid dual-mode", color=CASE_COLORS["hybrid_dual_mode"])
    axes[1].set_ylabel("Unserved energy (MWh)")
    axes[1].set_title("Which case still leaves unmet demand?", fontweight="bold")
    axes[1].legend(loc="upper left")

    axes[2].plot(
        hybrid_window["timestamp"],
        mkrw(hybrid_window["Incremental_Value_vs_Base"].cumsum()),
        color=CASE_COLORS["hybrid_dual_mode"],
        label="Hybrid incremental value vs base",
    )
    axes[2].plot(
        h2_window["timestamp"],
        mkrw(h2_window["Incremental_Value_vs_Base"].cumsum()),
        color=CASE_COLORS["h2_only"],
        label="H2-only incremental value vs base",
    )
    axes[2].plot(hybrid_window["timestamp"], mkrw(hybrid_window["ESS_Market_Profit"].cumsum()), color=CASE_COLORS["ess_only"], linestyle="--", label="Hybrid ESS market profit")
    axes[2].set_ylabel("Cumulative value (M KRW)")
    axes[2].set_title("Hybrid adds ESS market value on top of H2 resilience", fontweight="bold")
    axes[2].legend(loc="upper left")

    fig.suptitle(f"Event zoom around strongest spike at alpha={alpha:.2f}", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(figure_dir / f"event_zoom_alpha_{alpha:.2f}.png", bbox_inches="tight")
    plt.close(fig)


def plot_alpha_sweep(summary_df: pd.DataFrame, figure_dir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), dpi=220)
    plots = [
        ("incremental_value_vs_base", "Incremental value vs base", "M KRW", mkrw),
        ("net_profit", "Net profit", "M KRW", mkrw),
        ("avoided_penalty", "Avoided outage cost", "M KRW", mkrw),
        ("unserved_energy", "Residual unmet demand", "MWh", mwh),
    ]
    for ax, (metric, title, ylabel, transform) in zip(axes.flat, plots):
        for case_key, case_df in summary_df.groupby("case_key"):
            ax.plot(
                case_df["alpha"],
                transform(case_df[metric]),
                marker="o",
                linewidth=2.2,
                label=case_label_map().get(case_key, case_key),
                color=CASE_COLORS.get(case_key, None),
            )
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("alpha")
        ax.set_ylabel(ylabel)
        ax.grid(True, linestyle="--", alpha=0.35)
    axes[0, 0].legend(loc="best")
    fig.suptitle("Alpha sweep (readable trend view)", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(figure_dir / "alpha_sweep_overview.png", bbox_inches="tight")
    plt.close(fig)


def save_outputs(all_traces_df: pd.DataFrame, summary_df: pd.DataFrame, cfg: SystemConfig, alphas: Sequence[float]) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir = cfg.output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    summary_df.to_csv(cfg.output_dir / "comparison_summary.csv", index=False)
    all_traces_df.to_csv(cfg.output_dir / "all_case_traces.csv", index=False)

    story_alphas = resolve_story_alphas(alphas)
    for alpha in dict.fromkeys(story_alphas.values()):
        plot_case_comparison(summary_df, alpha, figure_dir)
    plot_alpha_sweep(summary_df, figure_dir)
    plot_alpha_heatmap(summary_df, figure_dir)
    plot_hybrid_necessity(summary_df, story_alphas["low"], figure_dir)
    plot_dual_mode_justification(summary_df, story_alphas["transition"], figure_dir)
    plot_event_zoom(all_traces_df, story_alphas["transition"], figure_dir)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HB-MPS comparison experiments with automatic alpha sweep")
    parser.add_argument("--data", type=Path, default=Path(__file__).with_name("data_file.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("outputs"))
    parser.add_argument(
        "--alphas",
        type=float,
        nargs="+",
        default=[1.20, 1.30, 1.40, 1.50, 1.80],
        help="Phase-2 alpha values to sweep automatically",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = SystemConfig(data_path=args.data.resolve(), output_dir=args.output_dir.resolve())
    df = load_input_data(cfg.data_path)
    all_traces_df, summary_df = run_alpha_sweep(df, cfg, args.alphas, DEFAULT_CASES)
    save_outputs(all_traces_df, summary_df, cfg, args.alphas)
    story_alphas = resolve_story_alphas(args.alphas)

    print("=== HB-MPS comparison experiment complete ===")
    print(f"Data rows: {len(df)}")
    print(f"Alpha values: {', '.join(f'{alpha:.2f}' for alpha in args.alphas)}")
    print(
        "Story alphas: "
        f"low={story_alphas['low']:.2f}, "
        f"transition={story_alphas['transition']:.2f}, "
        f"high={story_alphas['high']:.2f}"
    )
    print(f"Summary CSV: {cfg.output_dir / 'comparison_summary.csv'}")
    print(f"Figure directory: {cfg.output_dir / 'figures'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
