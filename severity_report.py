"""Reproducible three-strategy comparison for the new Figures 13 and 14."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandapower as pp
import pandas as pd

from emergency_dispatch import H2_CAPACITY_KG, run_scenario
from emergency_dispatch_model import Scenario, Strategy
from hb_inputs import INPUT, load_hours
from p1_multibus_dispatch import allocate_p1_supply, validate_main_reference
from powerflow_validation import (
    INDUSTRIAL_BUS_NUMBERS,
    MAIN_REFERENCE_PATH,
    MIN_VOLTAGE_PU,
    PV_PENETRATION,
    RESIDENTIAL_BUS_NUMBERS,
    RESULT_PATH,
    build_network,
    set_operating_point,
    solve_network,
)

if TYPE_CHECKING:
    from powerflow_validation_severity import SeverityResult


def _previous_location_assignment(
    demand: np.ndarray,
    voltage: np.ndarray,
    hfc_mw: np.ndarray,
    ess_mw: float,
) -> tuple[np.ndarray, tuple[int | None, ...]]:
    """Reproduce commit 14e9309's fixed-P1-supply severity placement."""
    scores = (
        0.5 * demand / max(float(demand.max()), 1e-12)
        + 0.5 * np.maximum(MIN_VOLTAGE_PU - voltage, 0.0) / MIN_VOLTAGE_PU
    )
    ranking = sorted(
        range(len(demand)),
        key=lambda index: (-scores[index], INDUSTRIAL_BUS_NUMBERS[index]),
    )
    remaining = demand.copy()
    injections = np.zeros(len(demand))
    positions: list[int | None] = []
    for truck, output in enumerate(hfc_mw):
        power = float(output) + (ess_mw if truck == 0 else 0.0)
        if power <= 0:
            positions.append(None)
            continue
        candidates = [index for index in ranking if remaining[index] > 1e-12]
        chosen = candidates[0] if candidates else ranking[0]
        injections[chosen] += power
        remaining[chosen] = max(0.0, remaining[chosen] - power)
        positions.append(INDUSTRIAL_BUS_NUMBERS[chosen])
    return injections, tuple(positions)


def _dual_mode_assets(
    net: pp.pandapowerNet, residential_buses: tuple[int, ...]
) -> tuple[dict[int, int], int, int]:
    """Add identical residential supply and charging interfaces to a control."""
    generators = {
        bus: pp.create_sgen(net, bus - 1, p_mw=0.0, q_mvar=0.0)
        for bus in residential_buses
    }
    pv_load = pp.create_load(net, 6, p_mw=0.0, q_mvar=0.0)
    grid_load = pp.create_load(net, 8, p_mw=0.0, q_mvar=0.0)
    return generators, pv_load, grid_load


def _set_dual_mode_assets(
    net: pp.pandapowerNet,
    assets: tuple[dict[int, int], int, int],
    mode1_bus: int,
    mode1_mw: float,
    pv_charging_mw: float,
    grid_charging_mw: float,
) -> None:
    """Apply a P1 Mode 1 step at the same residential bus as the dynamic case."""
    generators, pv_load, grid_load = assets
    net.sgen.loc[list(generators.values()), "p_mw"] = 0.0
    if mode1_mw > 0:
        net.sgen.at[generators[mode1_bus], "p_mw"] = mode1_mw
    net.load.at[pv_load, "p_mw"] = pv_charging_mw
    net.load.at[grid_load, "p_mw"] = grid_charging_mw
    net.load.loc[[pv_load, grid_load], "scaling"] = 1.0


def _summary_row(
    alpha: float,
    strategy: str,
    baseline: np.ndarray,
    supported: np.ndarray,
    baseline_losses: np.ndarray,
    supported_losses: np.ndarray,
    mode2_hours: int,
    supply_hours: int,
    load_trigger_hours: int,
    load_response_hours: int,
    hfc_kwh: float,
    ess_kwh: float,
    mode1_hours: int,
    mode1_ess_kwh: float,
    charging_kwh: float,
    load_response_mwh_ac: float,
    residual_excess_mwh_ac: float,
    h2_consumed_kg: float,
    h2_refilled_kg: float,
    soc_min_pct: float,
    soc_end_pct: float,
    main_loh_min_pct: float,
    main_loh_end_pct: float,
    positions: tuple[tuple[int | None, ...], ...],
    mw_per_raw_kwh: float,
) -> dict[str, float | int | str]:
    """Calculate identical voltage, energy and resource metrics for each rule."""
    all_positions = Counter(
        bus for hour in positions for bus in hour if bus is not None
    )
    main_positions = Counter(hour[0] for hour in positions if hour[0] is not None)
    deficit_base = np.maximum(MIN_VOLTAGE_PU - baseline, 0.0)
    deficit_supported = np.maximum(MIN_VOLTAGE_PU - supported, 0.0)
    return {
        "alpha": alpha,
        "strategy": strategy,
        "mode2_trigger_hours": mode2_hours,
        "actual_supply_hours": supply_hours,
        "load_excess_trigger_hours": load_trigger_hours,
        "load_response_hours": load_response_hours,
        "hfc_mwh_raw": hfc_kwh / 1000,
        "ess_mwh_raw": ess_kwh / 1000,
        "mode1_hours": mode1_hours,
        "mode1_ess_mwh_raw": mode1_ess_kwh / 1000,
        "charging_mwh_raw": charging_kwh / 1000,
        "total_mwh_raw": (hfc_kwh + ess_kwh) / 1000,
        "ac_injection_mwh": (hfc_kwh + ess_kwh) * mw_per_raw_kwh,
        "load_response_mwh_ac": load_response_mwh_ac,
        "residual_bus_excess_mwh_ac": residual_excess_mwh_ac,
        "worst_baseline_voltage_pu": float(baseline.min()),
        "worst_supported_voltage_pu": float(supported.min()),
        "violation_hours_baseline": int(np.any(deficit_base > 0, axis=1).sum()),
        "violation_hours_supported": int(np.any(deficit_supported > 0, axis=1).sum()),
        "unique_violating_buses_baseline": int(np.any(deficit_base > 0, axis=0).sum()),
        "unique_violating_buses_supported": int(
            np.any(deficit_supported > 0, axis=0).sum()
        ),
        "violating_bus_hours_baseline": int(np.count_nonzero(deficit_base)),
        "violating_bus_hours_supported": int(np.count_nonzero(deficit_supported)),
        "cumulative_voltage_deficit_baseline_pu_bus_h": float(deficit_base.sum()),
        "cumulative_voltage_deficit_supported_pu_bus_h": float(deficit_supported.sum()),
        "line_losses_baseline_mwh": float(baseline_losses.sum()),
        "line_losses_supported_mwh": float(supported_losses.sum()),
        "h2_consumed_kg": h2_consumed_kg,
        "h2_refilled_kg": h2_refilled_kg,
        "soc_min_pct": soc_min_pct,
        "soc_end_pct": soc_end_pct,
        "main_loh_min_pct": main_loh_min_pct,
        "main_loh_end_pct": main_loh_end_pct,
        "truck_dispatches": sum(all_positions.values()),
        "truck_bus_frequency": "; ".join(
            f"{bus}:{count}" for bus, count in sorted(all_positions.items())
        ),
        "main_bus_frequency": "; ".join(
            f"{bus}:{count}" for bus, count in sorted(main_positions.items())
        ),
    }


def compare_strategies(results: tuple[SeverityResult, ...]) -> pd.DataFrame:
    """Re-run the two older placements as read-only references for each α."""
    hours = load_hours(INPUT)
    saved_reference = pd.read_csv(RESULT_PATH)
    residential_peak = max(hour.residential for hour in hours)
    pv_peak = max(hour.solar for hour in hours)
    residential_indices = {bus - 1 for bus in RESIDENTIAL_BUS_NUMBERS}
    records: list[dict[str, float | int | str]] = []
    for dynamic in results:
        alpha = dynamic.alpha
        run = run_scenario(hours, Scenario(alpha, 5, Strategy.P1))
        validate_main_reference(run, MAIN_REFERENCE_PATH)
        old_base_net = build_network()
        reference_net = build_network()
        location_net = build_network()
        binary_fixed_net = build_network()
        binary_location_net = build_network()
        residential_buses = tuple(
            sorted(
                int(bus) + 1
                for bus in reference_net.load.bus.unique()
                if bus not in {number - 1 for number in INDUSTRIAL_BUS_NUMBERS}
            )
        )
        fixed_assets = _dual_mode_assets(binary_fixed_net, residential_buses)
        location_assets = _dual_mode_assets(binary_location_net, residential_buses)
        bus_ratings = np.array(
            [
                float(
                    reference_net.load.loc[
                        reference_net.load.bus.eq(bus - 1), "p_mw"
                    ].sum()
                )
                for bus in INDUSTRIAL_BUS_NUMBERS
            ]
        )
        industrial_rating = float(bus_ratings.sum())
        residential_rating = float(
            reference_net.load.loc[
                reference_net.load.bus.isin(residential_indices), "p_mw"
            ].sum()
        )
        pv_rating = float(reference_net.load.p_mw.sum()) * PV_PENETRATION
        raw_peak = max(hour.industrial for hour in hours)
        factor = industrial_rating / raw_peak
        share = bus_ratings[INDUSTRIAL_BUS_NUMBERS.index(18)] / (
            bus_ratings[INDUSTRIAL_BUS_NUMBERS.index(18)]
            + bus_ratings[INDUSTRIAL_BUS_NUMBERS.index(33)]
        )
        fixed_injection, truck_rows = allocate_p1_supply(hours, run, share)
        generators = np.array(
            [
                pp.create_sgen(
                    location_net,
                    bus - 1,
                    p_mw=0.0,
                    q_mvar=0.0,
                    name=f"Old severity-{bus}",
                )
                for bus in INDUSTRIAL_BUS_NUMBERS
            ]
        )
        binary_generators = np.array(
            [
                pp.create_sgen(
                    binary_location_net,
                    bus - 1,
                    p_mw=0.0,
                    q_mvar=0.0,
                    name=f"Binary old severity-{bus}",
                )
                for bus in INDUSTRIAL_BUS_NUMBERS
            ]
        )
        old_baseline_profiles: list[np.ndarray] = []
        old_baseline_losses: list[float] = []
        fixed_profiles: list[np.ndarray] = []
        location_profiles: list[np.ndarray] = []
        binary_fixed_profiles: list[np.ndarray] = []
        binary_location_profiles: list[np.ndarray] = []
        fixed_losses: list[float] = []
        location_losses: list[float] = []
        binary_fixed_losses: list[float] = []
        binary_location_losses: list[float] = []
        fixed_positions: list[tuple[int | None, ...]] = []
        location_positions: list[tuple[int | None, ...]] = []
        binary_location_positions: list[tuple[int | None, ...]] = []
        fixed_residual = location_residual = 0.0
        binary_location_residual = 0.0
        saved_alpha = saved_reference.loc[saved_reference.alpha.eq(alpha)].sort_values(
            "t"
        )
        if len(saved_alpha) != len(run.steps):
            raise AssertionError("Saved fig13_old reference is incomplete")
        for t, step in enumerate(run.steps):
            source = dynamic.hourly.iloc[t]
            industrial_scale = float(source.industrial_load_mw) / industrial_rating
            # The original validation's measured residential/PV scaling is
            # reconstructed from its unchanged hourly input and benchmark.
            residential_scale = hours[t].residential / residential_peak
            mixed_scale = (
                industrial_rating * industrial_scale
                + residential_rating * residential_scale
            ) / (industrial_rating + residential_rating)
            pv_mw = hours[t].solar / pv_peak * pv_rating
            allocation = fixed_injection[t]
            set_operating_point(
                old_base_net,
                industrial_scale,
                residential_scale,
                mixed_scale,
                pv_mw,
                0.0,
            )
            old_voltage, old_loss = solve_network(old_base_net)
            old_baseline_profiles.append(old_voltage)
            old_baseline_losses.append(old_loss)
            fixed_mw = np.zeros(len(INDUSTRIAL_BUS_NUMBERS))
            fixed_mw[INDUSTRIAL_BUS_NUMBERS.index(18)] = (
                allocation.hfc18_kwh + allocation.ess18_kwh
            ) * factor
            fixed_mw[INDUSTRIAL_BUS_NUMBERS.index(33)] = allocation.hfc33_kwh * factor
            set_operating_point(
                reference_net,
                industrial_scale,
                residential_scale,
                mixed_scale,
                pv_mw,
                fixed_mw[0],
                fixed_mw[INDUSTRIAL_BUS_NUMBERS.index(33)],
            )
            fixed_voltage, fixed_loss = solve_network(reference_net)
            saved_row = saved_alpha.iloc[t]
            if not np.isclose(fixed_voltage.min(), saved_row.vmin_hbmps, atol=1e-8):
                raise AssertionError("fig13_old voltage comparison drifted")
            if not np.isclose(fixed_loss, saved_row.ploss_hbmps_mw, atol=1e-8):
                raise AssertionError("fig13_old loss comparison drifted")
            fixed_profiles.append(fixed_voltage)
            fixed_losses.append(fixed_loss)
            rows = truck_rows[t * 5 : (t + 1) * 5]
            fixed_positions.append(
                tuple(
                    row.bus
                    if row.hfc_kwh > 0
                    or (row.truck == 0 and step.ess_emergency_kwh > 0)
                    else None
                    for row in rows
                )
            )

            demand = np.maximum(
                bus_ratings * industrial_scale
                - alpha
                * bus_ratings
                * float(dynamic.hourly.industrial_load_mw.mean())
                / industrial_rating,
                0.0,
            )
            hfc = np.array([row.hfc_kwh for row in rows]) * factor
            placed, positions = _previous_location_assignment(
                demand,
                old_voltage[np.array(INDUSTRIAL_BUS_NUMBERS) - 1],
                hfc,
                step.ess_emergency_kwh * factor,
            )
            binary_placed, binary_positions = _previous_location_assignment(
                demand,
                dynamic.baseline_profiles[t, np.array(INDUSTRIAL_BUS_NUMBERS) - 1],
                hfc,
                step.ess_emergency_kwh * factor,
            )
            set_operating_point(
                location_net,
                industrial_scale,
                residential_scale,
                mixed_scale,
                pv_mw,
                0.0,
            )
            location_net.sgen.loc[generators, "p_mw"] = placed
            location_voltage, location_loss = solve_network(location_net)
            location_profiles.append(location_voltage)
            location_losses.append(location_loss)
            location_positions.append(positions)
            binary_location_positions.append(binary_positions)
            fixed_residual += float(np.maximum(demand - fixed_mw, 0.0).sum())
            location_residual += float(np.maximum(demand - placed, 0.0).sum())
            binary_location_residual += float(
                np.maximum(demand - binary_placed, 0.0).sum()
            )

            # Fair controls use the new binary-load feeder and inject the
            # existing P1 Mode 1 output / charging at the same sites.
            mode1_bus = min(
                residential_buses,
                key=lambda bus: (dynamic.baseline_profiles[t, bus - 1], bus),
            )
            mode1_mw = step.phase1_ess_kwh * factor
            pv_charging_mw = (step.pv_ess_charge_kwh + step.pv_p2g_kwh) * factor
            grid_charging_mw = step.grid_ess_charge_kwh * factor
            for binary_net, assets, hbmps18, hbmps33, distributed in (
                (
                    binary_fixed_net,
                    fixed_assets,
                    fixed_mw[0],
                    fixed_mw[INDUSTRIAL_BUS_NUMBERS.index(33)],
                    None,
                ),
                (binary_location_net, location_assets, 0.0, 0.0, binary_placed),
            ):
                set_operating_point(
                    binary_net,
                    industrial_scale,
                    residential_scale,
                    residential_scale,
                    pv_mw,
                    hbmps18,
                    hbmps33,
                )
                _set_dual_mode_assets(
                    binary_net,
                    assets,
                    mode1_bus,
                    mode1_mw,
                    pv_charging_mw,
                    grid_charging_mw,
                )
                if distributed is not None:
                    binary_net.sgen.loc[binary_generators, "p_mw"] = distributed
                binary_voltage, binary_loss = solve_network(binary_net)
                if distributed is None:
                    binary_fixed_profiles.append(binary_voltage)
                    binary_fixed_losses.append(binary_loss)
                else:
                    binary_location_profiles.append(binary_voltage)
                    binary_location_losses.append(binary_loss)

        p1_mode2 = sum(step.mode2 for step in run.steps)
        p1_supply = sum(
            step.hfc_kwh + step.ess_emergency_kwh > 1e-7 for step in run.steps
        )
        p1_hfc = sum(step.hfc_kwh for step in run.steps)
        p1_ess = sum(step.ess_emergency_kwh for step in run.steps)
        p1_mode1 = sum(step.phase1_ess_kwh for step in run.steps)
        p1_charging = sum(
            step.pv_ess_charge_kwh + step.pv_p2g_kwh + step.grid_ess_charge_kwh
            for step in run.steps
        )
        old_baseline = np.stack(old_baseline_profiles)
        old_losses = np.array(old_baseline_losses)
        baseline_losses = dynamic.hourly.line_loss_baseline_mw.to_numpy(dtype=float)
        common = dict(
            alpha=alpha,
            baseline=old_baseline,
            baseline_losses=old_losses,
            hfc_kwh=p1_hfc,
            ess_kwh=p1_ess,
            mode1_hours=0,
            mode1_ess_kwh=0.0,
            charging_kwh=0.0,
            load_response_mwh_ac=(p1_hfc + p1_ess) * factor,
            h2_consumed_kg=run.total("consumed_h2_kg"),
            h2_refilled_kg=run.total("external_h2_kg"),
            soc_min_pct=min(step.soc_end for step in run.steps) * 100,
            soc_end_pct=run.terminal_soc * 100,
            main_loh_min_pct=min(step.main_h2_end_kg for step in run.steps)
            / H2_CAPACITY_KG
            * 100,
            main_loh_end_pct=run.steps[-1].main_h2_end_kg / H2_CAPACITY_KG * 100,
            mw_per_raw_kwh=factor,
        )
        for label, profiles, losses, residual, positions in (
            (
                "fig13_old",
                fixed_profiles,
                fixed_losses,
                fixed_residual,
                fixed_positions,
            ),
            (
                "Location-only severity",
                location_profiles,
                location_losses,
                location_residual,
                location_positions,
            ),
        ):
            records.append(
                _summary_row(
                    strategy=f"{label} (mixed)",
                    supported=np.stack(profiles),
                    supported_losses=np.array(losses),
                    mode2_hours=p1_mode2,
                    supply_hours=p1_supply,
                    load_trigger_hours=p1_mode2,
                    load_response_hours=p1_supply,
                    residual_excess_mwh_ac=residual,
                    positions=tuple(positions),
                    **common,
                )
            )
        for label, profiles, losses, residual, positions in (
            (
                "Fixed P1 dual-mode (binary)",
                binary_fixed_profiles,
                binary_fixed_losses,
                fixed_residual,
                fixed_positions,
            ),
            (
                "Location-only dual-mode (binary)",
                binary_location_profiles,
                binary_location_losses,
                binary_location_residual,
                binary_location_positions,
            ),
        ):
            binary_common = common | {
                "baseline": dynamic.baseline_profiles,
                "baseline_losses": baseline_losses,
                "mode1_hours": sum(step.phase1_ess_kwh > 0 for step in run.steps),
                "mode1_ess_kwh": p1_mode1,
                "charging_kwh": p1_charging,
            }
            records.append(
                _summary_row(
                    strategy=label,
                    supported=np.stack(profiles),
                    supported_losses=np.array(losses),
                    mode2_hours=p1_mode2,
                    supply_hours=p1_supply,
                    load_trigger_hours=p1_mode2,
                    load_response_hours=p1_supply,
                    residual_excess_mwh_ac=residual,
                    positions=tuple(positions),
                    **binary_common,
                )
            )
        dynamic_positions = tuple(
            tuple(
                int(vehicle.bus)
                if vehicle.mode == "Mode 2" and pd.notna(vehicle.bus)
                else None
                for vehicle in dynamic.trucks.loc[dynamic.trucks.t.eq(t)].itertuples(
                    index=False
                )
            )
            for t in range(len(dynamic.hourly))
        )
        h = dynamic.hourly
        records.append(
            _summary_row(
                alpha=alpha,
                strategy="Dynamic bus-level",
                baseline=dynamic.baseline_profiles,
                supported=dynamic.supported_profiles,
                baseline_losses=baseline_losses,
                supported_losses=h.line_loss_supported_mw.to_numpy(dtype=float),
                mode2_hours=int(h.mode2_trigger.sum()),
                supply_hours=int(h.supply_active.sum()),
                load_trigger_hours=int(h.load_excess_trigger.sum()),
                load_response_hours=int(h.load_dispatch_active.sum()),
                hfc_kwh=float(h.hfc_kwh.sum()),
                ess_kwh=float(h.ess_emergency_kwh.sum()),
                mode1_hours=int(h.mode1_active.sum()),
                mode1_ess_kwh=float(h.phase1_ess_kwh.sum()),
                charging_kwh=float(
                    h.pv_ess_charge_kwh.sum()
                    + h.pv_p2g_kwh.sum()
                    + h.grid_ess_charge_kwh.sum()
                ),
                load_response_mwh_ac=float(h.load_response_mw.sum()),
                residual_excess_mwh_ac=float(h.residual_excess_mw.sum()),
                h2_consumed_kg=float(h.h2_consumed_kg.sum()),
                h2_refilled_kg=float(h.h2_refilled_kg.sum()),
                soc_min_pct=float(h.soc_end_pct.min()),
                soc_end_pct=float(h.soc_end_pct.iloc[-1]),
                main_loh_min_pct=float(h.main_loh_end_pct.min()),
                main_loh_end_pct=float(h.main_loh_end_pct.iloc[-1]),
                positions=dynamic_positions,
                mw_per_raw_kwh=factor,
            )
        )
    return pd.DataFrame.from_records(records)


def write_report(
    results: tuple[SeverityResult, ...], comparison: pd.DataFrame, path: Path
) -> None:
    """Document the binary feeder, dual-mode interfaces and honest comparisons."""
    mixed = comparison.loc[comparison.strategy.eq("fig13_old (mixed)")].iloc[0]
    dynamic = comparison.loc[comparison.strategy.eq("Dynamic bus-level")].sort_values(
        "alpha"
    )
    binary = dynamic.iloc[0]
    lines = [
        "# Figs. 13–14: 산업·주거 모선별 HB-MPS 이중 운용",
        "",
        "기존 fig13_old와 메인 P1 코드는 변경하지 않았다. α=1.3 결과를 "
        "운전·차량 배치 Fig. 13과 전압 효과 Fig. 14로 분리했다.",
        "",
        "## 모선 구성과 운용 규칙",
        "",
        "- IEEE 33-bus의 산업부하 모선 9개를 유지하고, 나머지 부하 모선 23개는 "
        "주거부하로 설정했다. 혼합부하는 사용하지 않는다. Slack 1개 모선, 선로, "
        "모선별 정격 P·Q는 유지한다. 산업·주거 부하는 각각의 실측 프로파일로 "
        "정규화해 시간별 scaling에 적용한다.",
        "- 산업 모선별 임계값은 α×해당 모선의 168시간 평균 부하다. 초과량은 "
        "가정된 공급 허용량 대비 부족분이며 실제 미공급 전력은 아니다. 산업 "
        "모선에서 초과량>0일 때만 Mode 2가 우선한다. 저전압만으로는 "
        "출동하지 않으며 0.95 p.u.는 전압 성능 평가 기준이다.",
        "- Mode 2는 초과량이 있는 산업 모선만 접속 후보로 삼는다. 해당 "
        "모선의 초과량과 0.95 p.u. 위반량을 각각 시간별 최대값으로 "
        "정규화한 뒤 0.5씩 가중하여 배치 순위를 정한다. HFC를 "
        "차량별로 먼저 투입하고 매 주입 후 AC를 다시 계산한다. ESS는 주 차량의 "
        "backup이다. 공급량은 모선별 잔여 초과량과 차량 가용 용량 중 작은 "
        "값이며, 전압 개선만을 위한 추가 공급은 하지 않는다.",
        "- Mode 2가 없을 때에만 기존 P1의 가격·SOC 조건에 따른 Mode 1을 "
        "허용한다. 주 차량 ESS 출력은 주거부하 모선에 AC 주입한다. 주거 모선의 "
        "가격 신호가 같으므로 가장 낮은 기준 전압의 주거 모선을 접속 위치로 "
        "정했다. Mode 1 발동에 주거 전압 임계는 사용하지 않는다.",
        "- PV ESS 충전과 P2G 소비는 PV 연결 Bus 7의 부하로, 계통 ESS 충전은 "
        "주거 Bus 9의 부하로 반영한다. 충전 부하는 별도 요소로 두어 시간별 "
        "주거 scaling을 중복 적용하지 않았다. 차량은 매시간 재배치할 수 있으며 "
        "실제 이동 시간은 모델링하지 않았다.",
        "- HB-MPS의 원자료 kWh→IEEE 계통 MW 환산은 기존 검증과 동일하게 "
        "산업 모선 정격 MW/입력 산업부하 최대 kWh를 모든 공급·충전에 적용한다. "
        "HFC/ESS 정격, 효율, SOC·LOH, 수소 이동 소비·보충 및 Mode 1 가격 "
        "조건은 기존 P1과 같다. 계산상 부하 초과량을 물리적 미공급 전력으로 "
        "간주하거나 그 전체에 VOLL 편익을 자동 부여하지 않는다.",
        "",
        "## 비교 기준",
        "",
        f"기존 혼합부하 계통 무지원 기준: 최저 {mixed.worst_baseline_voltage_pu:.4f} "
        f"p.u., 0.95 미만 {mixed.violation_hours_baseline}시간, "
        f"누적 위반 {mixed.cumulative_voltage_deficit_baseline_pu_bus_h:.3f} "
        "p.u.·bus·h.",
        f"새 산업·주거 계통 무지원 기준: 최저 {binary.worst_baseline_voltage_pu:.4f} "
        f"p.u., 0.95 미만 {binary.violation_hours_baseline}시간, "
        f"누적 위반 {binary.cumulative_voltage_deficit_baseline_pu_bus_h:.3f} "
        "p.u.·bus·h.",
        "기존 혼합부하 fig13_old와 새 이중 운용을 직접 비교하면 부하 구성의 "
        "영향이 섞인다. 이를 분리하려고 같은 산업·주거 계통에 기존 P1 고정 "
        "배치와 직전 위치 재배치를 적용하고, 두 대조군 모두 Mode 1 공급과 "
        "충전도 AC에 반영했다. 기존 혼합부하 결과는 보존용 참고다. 표의 혼합부하 "
        "Mode 1 0시간은 운용량이 0이라는 뜻이 아니라 당시 AC 그림에 Mode 1을 "
        "반영하지 않았다는 뜻이다.",
        "",
        "| α | 계통·전략 | Mode 1 h | Mode 2 조건/실공급 h | "
        "HFC/비상 ESS/Mode 1 ESS 원자료 MWh | 최저 전압 p.u. | "
        "0.95 미만 h | 누적 위반 p.u.·bus·h | 선로손실 MWh |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison.itertuples(index=False):
        lines.append(
            f"| {row.alpha:.1f} | {row.strategy} | {row.mode1_hours} | "
            f"{row.mode2_trigger_hours}/{row.actual_supply_hours} | "
            f"{row.hfc_mwh_raw:.3f}/{row.ess_mwh_raw:.3f}/"
            f"{row.mode1_ess_mwh_raw:.3f} | "
            f"{row.worst_supported_voltage_pu:.4f} | "
            f"{row.violation_hours_supported} | "
            f"{row.cumulative_voltage_deficit_supported_pu_bus_h:.3f} | "
            f"{row.line_losses_supported_mwh:.3f} |"
        )
    lines.extend(
        [
            "",
            "비교 CSV에는 저전압 발생 고유 모선 수·모선시간, AC 주입 에너지, "
            "수소 사용·보충, SOC·LOH 및 차량별 접속 횟수도 포함했다. 공급 에너지와 "
            "자원 소비가 다르므로 전압 개선을 동일 에너지 효율로 해석하지 않는다.",
            "",
            "## 새 이중 운용의 상세 결과",
            "",
            "| α | 산업 초과 h | Mode 2 실공급/Mode 1 공급 h | "
            "Mode 1 ESS/충전 원자료 MWh | 계산상 잔여 초과 MWh(AC) | "
            "SOC 최저→종료 % | 주 차량 LOH 최저→종료 % |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in dynamic.itertuples(index=False):
        lines.append(
            f"| {row.alpha:.1f} | {row.load_excess_trigger_hours} | "
            f"{row.actual_supply_hours}/"
            f"{row.mode1_hours} | {row.mode1_ess_mwh_raw:.3f}/"
            f"{row.charging_mwh_raw:.3f} | "
            f"{row.residual_bus_excess_mwh_ac:.3f} | "
            f"{row.soc_min_pct:.1f}→{row.soc_end_pct:.1f} | "
            f"{row.main_loh_min_pct:.1f}→{row.main_loh_end_pct:.1f} |"
        )
    lines.extend(
        [
            "",
            "차량 위치(모선:출동 횟수)는 비상 Mode 2 기준이며, Mode 1 주 차량 "
            "및 충전 위치는 시간별 차량 CSV에도 기록했다.",
            "",
        ]
    )
    for result in results:
        active = result.trucks.loc[result.trucks["mode"].eq("Mode 2")]
        mode1 = result.trucks.loc[result.trucks["mode"].eq("Mode 1")]
        mode1_buses = Counter(mode1.bus.astype(int))
        lines.append(f"- α={result.alpha:.1f}:")
        lines.append(
            "  - Mode 1 주거 접속: "
            + (
                ", ".join(
                    f"Bus {bus} {count}회" for bus, count in sorted(mode1_buses.items())
                )
                or "없음"
            )
            + "; PV·P2G 충전 Bus 7, 계통 충전 Bus 9."
        )
        for truck in range(5):
            frequencies = Counter(active.loc[active.truck.eq(truck), "bus"].astype(int))
            detail = (
                ", ".join(
                    f"Bus {bus} {count}회" for bus, count in sorted(frequencies.items())
                )
                or "출동 없음"
            )
            lines.append(f"  - 차량 {truck}: {detail}")
        worst = result.hourly.iloc[result.worst_hour]
        lines.append(
            f"  - 기준 최악 시간 t={result.worst_hour}: "
            f"{worst.vmin_baseline:.4f}→{worst.vmin_supported:.4f} p.u., "
            f"Mode 2 공급 {worst.emergency_supply_mw:.3f} MW, "
            f"Mode 1 공급 {worst.mode1_supply_mw:.3f} MW, "
            f"SOC {worst.soc_start_pct:.1f}%, "
            f"함대 수소 {worst.fleet_h2_start_kg:.1f} kg."
        )
    lines.extend(
        [
            "",
            "α=1.3의 Fig. 13은 (a) 합산 산업부하·허용량, (b) Mode 1·2 운용 "
            "시간, (c) 차량별 실제 접속 모선을 표시한다. Fig. 14는 "
            "(a) 기준 최악 시간의 모선별 전압·접속 모선, (b) 33개 모선의 "
            "전압 시계열, (c) 지원 후−기준 모선별 전압 변화를 표시한다. "
            "α=1.5의 기존 6패널 결과는 fig13_2로 별도 보존한다. "
            "전압 변화의 음수는 충전 등으로 전압이 "
            "낮아진 경우도 보여 준다. 0.95 p.u. 선은 출동 조건이 아닌 "
            "전압 평가 기준이다.",
            "전체 33개 모선의 0.95 p.u. 미만 시간은 Mode 1·2 지원 후에도 "
            "남는다. 주거 저전압만으로 Mode 2가 발동하지 않으며, Mode 1은 "
            "경제성·SOC 조건이 맞을 때만 공급하므로 모든 저전압을 해소하지 않는다.",
            "",
        ]
    )
    first, second = dynamic.iloc[0], dynamic.iloc[1]
    if first.violation_hours_supported == second.violation_hours_supported:
        lines.append(
            "**논문 조건 선택:** 두 α의 전체 저전압 시간은 같다. "
            f"산업 초과 조건은 α=1.3에서 {first.load_excess_trigger_hours}시간, "
            f"α=1.5에서 {second.load_excess_trigger_hours}시간이다. "
            f"α=1.5는 Mode 1을 {second.mode1_hours}시간 보여 주며 "
            f"α=1.3의 {first.mode1_hours}시간보다 많다. "
            "다만 누적 전압 위반은 α=1.5가 "
            f"{second.cumulative_voltage_deficit_supported_pu_bus_h:.3f} "
            f"p.u.·bus·h로 α=1.3의 "
            f"{first.cumulative_voltage_deficit_supported_pu_bus_h:.3f}보다 크다. "
            f"비상 공급 원자료 에너지도 α=1.5는 {second.total_mwh_raw:.3f} MWh, "
            f"α=1.3은 {first.total_mwh_raw:.3f} MWh이다. 이중 운용을 "
            "적은 비상 출동과 자원 소비로 보여 주는 대표 그림에는 α=1.5가 "
            "적합하고, 더 큰 전압 개선 효과를 검토할 때는 α=1.3을 함께 "
            "제시해야 한다. 두 경우 모두 남는 저전압을 명시해야 한다."
        )
    else:
        better = min(
            dynamic.itertuples(index=False),
            key=lambda row: row.violation_hours_supported,
        )
        lines.append(
            f"**논문 조건 선택:** α={better.alpha:.1f}에서 저전압 시간이 "
            "더 적다. 공급 에너지·수소 소비·충전량을 함께 해석하고 남는 "
            "전압 위반을 명시해야 한다."
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
