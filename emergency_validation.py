"""Physical and economic invariants shared by all P1 study paths."""

from __future__ import annotations

import math
from dataclasses import asdict

from emergency_dispatch import (
    ESS_EFFICIENCY,
    ESS_MAX_SOC,
    ESS_MIN_SOC,
    ESS_WEAR_KRW_PER_KWH,
    ESS_WITHDRAWAL_KWH,
    H2_KWH_PER_KG,
    HFC_OUTPUT_KWH,
    P2G_KWH_PER_KG,
)
from emergency_dispatch_model import Run, Strategy


def validate_run(run: Run) -> None:
    """Reject energy, output, inventory, and accounting inconsistencies."""
    tolerance = 1e-6
    ess_capacity = run.scenario.ess_capacity_kwh
    h2_capacity = run.scenario.hfc_capacity_kwh / H2_KWH_PER_KG
    for step in run.steps:
        for value in asdict(step).values():
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                raise AssertionError((run.scenario, step.timestamp, "non-finite value"))
        if not math.isclose(
            step.demand_kwh,
            step.hfc_kwh + step.ess_emergency_kwh + step.unserved_kwh,
            abs_tol=tolerance,
        ):
            raise AssertionError((run.scenario, step.timestamp, "supply balance"))
        min_soc = ESS_MIN_SOC if ess_capacity else 0.0
        max_soc = ESS_MAX_SOC if ess_capacity else 0.0
        if not min_soc - tolerance <= step.soc_end <= max_soc + tolerance:
            raise AssertionError((run.scenario, step.timestamp, "SOC bound"))
        if (
            not -tolerance
            <= step.h2_end_kg
            <= run.scenario.trucks * h2_capacity + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "H2 inventory bound"))
        if not (
            -tolerance
            <= step.h2_min_truck_kg
            <= step.h2_max_truck_kg
            <= h2_capacity + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "per-truck H2 bound"))
        if (
            not 0
            <= step.hfc_kwh
            <= step.hfc_trucks_dispatched * HFC_OUTPUT_KWH + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "HFC rating"))
        if (
            not 0
            <= step.ess_emergency_kwh
            <= ESS_WITHDRAWAL_KWH * ESS_EFFICIENCY + tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "ESS rating"))
        if step.hfc_trucks_dispatched > run.scenario.trucks:
            raise AssertionError((run.scenario, step.timestamp, "truck availability"))
        expected_h2_end = (
            step.h2_start_kg
            + step.external_h2_kg
            + step.pv_p2g_kwh / P2G_KWH_PER_KG
            - step.consumed_h2_kg
        )
        if not math.isclose(step.h2_end_kg, expected_h2_end, abs_tol=tolerance):
            raise AssertionError((run.scenario, step.timestamp, "H2 balance"))
        expected_soc_end = step.soc_start + (
            (
                (step.pv_ess_charge_kwh + step.grid_ess_charge_kwh) * ESS_EFFICIENCY
                - (step.ess_emergency_kwh + step.phase1_ess_kwh) / ESS_EFFICIENCY
            )
            / ess_capacity
            if ess_capacity
            else 0.0
        )
        if not math.isclose(step.soc_end, expected_soc_end, abs_tol=tolerance):
            raise AssertionError((run.scenario, step.timestamp, "ESS balance"))
        if (
            step.h2_purchase_krw < 0
            or step.grid_purchase_krw < 0
            or step.ess_wear_krw < 0
        ):
            raise AssertionError((run.scenario, step.timestamp, "negative cost"))
        if not math.isclose(
            step.h2_purchase_krw,
            step.external_h2_kg * step.h2_price_krw_per_kg,
            abs_tol=tolerance,
        ):
            raise AssertionError(
                (run.scenario, step.timestamp, "H2 purchase accounting")
            )
        if not math.isclose(
            step.grid_purchase_krw,
            step.grid_ess_charge_kwh * step.smp_krw_per_kwh,
            abs_tol=tolerance,
        ):
            raise AssertionError(
                (run.scenario, step.timestamp, "grid purchase accounting")
            )
        if not math.isclose(
            step.revenue_krw,
            step.phase1_ess_kwh * step.lcoe_krw_per_kwh,
            abs_tol=tolerance,
        ):
            raise AssertionError(
                (run.scenario, step.timestamp, "Mode 1 revenue accounting")
            )
        wear_throughput = (
            (step.ess_emergency_kwh + step.phase1_ess_kwh) / ESS_EFFICIENCY
            + step.pv_ess_charge_kwh
            + step.grid_ess_charge_kwh
        )
        if not math.isclose(
            step.ess_wear_krw, wear_throughput * ESS_WEAR_KRW_PER_KWH, abs_tol=tolerance
        ):
            raise AssertionError((run.scenario, step.timestamp, "ESS wear accounting"))
    if run.scenario.strategy is Strategy.P0 and run.total("ess_emergency_kwh") != 0:
        raise AssertionError((run.scenario, "P0 ESS emergency supply"))
    if (
        run.scenario.strategy is Strategy.P2
        and ess_capacity
        and run.terminal_soc < ESS_MIN_SOC
    ):
        raise AssertionError((run.scenario, "P2 terminal SOC"))
    if run.scenario.strategy is Strategy.P2:
        for step in run.steps:
            if (
                step.ess_emergency_kwh > 0
                and step.soc_end < (run.scenario.reserve_soc or 0.0) - tolerance
            ):
                raise AssertionError(
                    (run.scenario, step.timestamp, "emergency reserve")
                )
