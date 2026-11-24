"""Reproducible three-strategy comparison for the additional Figure 15 cases."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pandapower as pp

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
    voltage_trigger_hours: int,
    load_response_hours: int,
    voltage_only_response_hours: int,
    hfc_kwh: float,
    ess_kwh: float,
    load_response_mwh_ac: float,
    voltage_only_mwh_ac: float,
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
        "voltage_trigger_hours": voltage_trigger_hours,
        "load_response_hours": load_response_hours,
        "voltage_only_response_hours": voltage_only_response_hours,
        "hfc_mwh_raw": hfc_kwh / 1000,
        "ess_mwh_raw": ess_kwh / 1000,
        "total_mwh_raw": (hfc_kwh + ess_kwh) / 1000,
        "ac_injection_mwh": (hfc_kwh + ess_kwh) * mw_per_raw_kwh,
        "load_response_mwh_ac": load_response_mwh_ac,
        "voltage_only_mwh_ac": voltage_only_mwh_ac,
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
        reference_net = build_network()
        location_net = build_network()
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
        baseline = dynamic.baseline_profiles
        fixed_profiles: list[np.ndarray] = []
        location_profiles: list[np.ndarray] = []
        fixed_losses: list[float] = []
        location_losses: list[float] = []
        fixed_positions: list[tuple[int | None, ...]] = []
        location_positions: list[tuple[int | None, ...]] = []
        fixed_residual = location_residual = 0.0
        saved_alpha = saved_reference.loc[saved_reference.alpha.eq(alpha)].sort_values(
            "t"
        )
        if len(saved_alpha) != len(run.steps):
            raise AssertionError("Saved original Figure 15 reference is incomplete")
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
                raise AssertionError("Original Figure 15 voltage comparison drifted")
            if not np.isclose(fixed_loss, saved_row.ploss_hbmps_mw, atol=1e-8):
                raise AssertionError("Original Figure 15 loss comparison drifted")
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
                baseline[t, np.array(INDUSTRIAL_BUS_NUMBERS) - 1],
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
            fixed_residual += float(np.maximum(demand - fixed_mw, 0.0).sum())
            location_residual += float(np.maximum(demand - placed, 0.0).sum())

        p1_mode2 = sum(step.mode2 for step in run.steps)
        p1_supply = sum(
            step.hfc_kwh + step.ess_emergency_kwh > 1e-7 for step in run.steps
        )
        p1_hfc = sum(step.hfc_kwh for step in run.steps)
        p1_ess = sum(step.ess_emergency_kwh for step in run.steps)
        baseline_losses = dynamic.hourly.line_loss_baseline_mw.to_numpy(dtype=float)
        common = dict(
            alpha=alpha,
            baseline=baseline,
            baseline_losses=baseline_losses,
            voltage_trigger_hours=int(dynamic.hourly.voltage_trigger.sum()),
            hfc_kwh=p1_hfc,
            ess_kwh=p1_ess,
            load_response_mwh_ac=(p1_hfc + p1_ess) * factor,
            voltage_only_mwh_ac=0.0,
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
                "Existing Figure 15",
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
                    strategy=label,
                    supported=np.stack(profiles),
                    supported_losses=np.array(losses),
                    mode2_hours=p1_mode2,
                    supply_hours=p1_supply,
                    load_trigger_hours=p1_mode2,
                    load_response_hours=p1_supply,
                    voltage_only_response_hours=0,
                    residual_excess_mwh_ac=residual,
                    positions=tuple(positions),
                    **common,
                )
            )
        dynamic_positions = tuple(
            tuple(
                int(bus) if pd.notna(bus) else None
                for bus in dynamic.trucks.loc[dynamic.trucks.t.eq(t), "bus"]
            )
            for t in range(len(dynamic.hourly))
        )
        h = dynamic.hourly
        records.append(
            _summary_row(
                alpha=alpha,
                strategy="Dynamic bus-level",
                baseline=baseline,
                supported=dynamic.supported_profiles,
                baseline_losses=baseline_losses,
                supported_losses=h.line_loss_supported_mw.to_numpy(dtype=float),
                mode2_hours=int(h.mode2_trigger.sum()),
                supply_hours=int(h.supply_active.sum()),
                load_trigger_hours=int(h.load_excess_trigger.sum()),
                voltage_trigger_hours=int(h.voltage_trigger.sum()),
                load_response_hours=int(h.load_dispatch_active.sum()),
                voltage_only_response_hours=int(h.voltage_only_dispatch_active.sum()),
                hfc_kwh=float(h.hfc_kwh.sum()),
                ess_kwh=float(h.ess_emergency_kwh.sum()),
                load_response_mwh_ac=float(h.load_response_mw.sum()),
                voltage_only_mwh_ac=float(h.voltage_only_mw.sum()),
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
    """Write assumptions, three-way quantitative results, and limitations."""
    lines = [
        "# Fig. 15(1)·(2): 모선별 동적 HB-MPS 비상운용 검증",
        "",
        "기존 Figure 15 및 메인 P1 시뮬레이션은 수정하지 않았다. "
        "직전 위치 재배치 실험의 "
        "Fig. 15(1)·(2) 출력만 새 동적 운용 결과로 교체했다.",
        "",
        "## 계산 규칙과 단위",
        "",
        "- 9개 산업 모선마다 168시간 평균 부하를 구하고 임계값을 α배로 정했다. "
        "초과분 D_i=max(0,P_i−α mean(P_i))는 **가정된 공급 허용량 대비 부족분**이며 "
        "실측 미공급 전력과 다르다.",
        "- 매 시간 공급 전 33개 모선의 AC 전압을 확인한다. 산업 모선 초과 또는 어느 "
        "모선의 전압이 0.95 p.u. 미만이면 Mode 2 조건이다. "
        "접속은 산업 모선 9개로 제한한다.",
        "- 심각도는 0.5×(모선 초과량/해당 시간 최대 초과량) + "
        "0.5×(모선 전압 위반량/33개 모선 최대 위반량)이다. 후보 모선에 위반이 "
        "없지만 다른 모선에 위반이 있으면 후보 전압의 낮은 순서를 사용한다.",
        "- 차량별로 심각도가 가장 높은 모선에 최대 1곳 접속하고 HFC를 먼저 투입한다. "
        "투입 후 AC를 다시 풀어 남은 부하 초과와 저전압을 평가한다. ESS는 HFC 다음에 "
        "주 차량의 접속 모선에서만 사용한다. 같은 모선에 여러 차량이 접속할 수 있다.",
        "- 전압 지원 필요량은 해당 모선에서 차량 가용 출력으로 AC 시험하고, 0.95를 "
        "달성할 수 있으면 이분 탐색으로 최소 출력을 찾는다. "
        "한 차량으로 달성하지 못하면 "
        "위반량을 줄이는 경우 가용 출력을 쓴다. 공급량은 max(남은 해당 모선 초과분, "
        "전압 지원 필요량)으로 정해 두 요구량을 더하지 않는다.",
        "- IEEE 33-bus MW와 운용 kWh의 환산은 기존 검증과 같은 "
        "(산업 모선 정격 MW)/(입력 산업부하 최대 kWh)이다. "
        "1시간 주입 MW의 수치는 MWh와 같다.",
        "- HFC 정격, 수소·이동 소비, 보충 순서, ESS 효율·SOC 하한, 비상 외 시간의 "
        "Mode 1/충전 규칙은 원 P1과 같다. ESS만 출동하는 주 차량에도 이동 수소를 "
        "차감한다. 차량은 1시간 단위로 재배치하며 이동 시간은 별도로 모델링하지 "
        "않는다. 전압 전용 공급에는 VOLL 회피편익을 계산하지 않았다.",
        "- 부하 대응/전압 전용 에너지는 각 접속 모선의 계산상 초과분을 먼저 충당한 "
        "것으로 회계상 구분했다. 동일 주입이 전압에도 기여하므로 물리적으로 독립된 "
        "두 종류의 전력이 아니다.",
        "",
        "## 세 방식 비교",
        "",
        "기존 Figure 15는 두 고정 모선 주입, 직전 실험은 P1 공급량을 고정한 채 "
        "위치만 재배치, 새 실험은 출동·공급량·상태를 AC 결과에 따라 "
        "매시간 다시 계산한다.",
        "",
        f"공통 무지원 기준: 최저 {comparison.iloc[0].worst_baseline_voltage_pu:.4f} "
        f"p.u., 저전압 {comparison.iloc[0].violation_hours_baseline} h, "
        f"발생 모선 {comparison.iloc[0].unique_violating_buses_baseline}개, "
        f"모선·시간 {comparison.iloc[0].violating_bus_hours_baseline}, "
        "누적 위반 "
        f"{comparison.iloc[0].cumulative_voltage_deficit_baseline_pu_bus_h:.3f} "
        f"p.u.·bus·h, 선로손실 {comparison.iloc[0].line_losses_baseline_mwh:.3f} MWh.",
        "",
        "| α | 방식 | Mode 2 조건/실공급 h | HFC/ESS 원자료 MWh | "
        "최저 전압 p.u. | 저전압 시간/모선 수/모선·시간 | 누적 위반 p.u.·bus·h | "
        "선로손실 MWh |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison.itertuples(index=False):
        lines.append(
            f"| {row.alpha:.1f} | {row.strategy} | "
            f"{row.mode2_trigger_hours}/{row.actual_supply_hours} | "
            f"{row.hfc_mwh_raw:.3f}/{row.ess_mwh_raw:.3f} | "
            f"{row.worst_supported_voltage_pu:.4f} | "
            f"{row.violation_hours_supported}/{row.unique_violating_buses_supported}/"
            f"{row.violating_bus_hours_supported} | "
            f"{row.cumulative_voltage_deficit_supported_pu_bus_h:.3f} | "
            f"{row.line_losses_supported_mwh:.3f} |"
        )
    lines.extend(
        [
            "",
            "두 기준 방식은 산업부하 초과 시에만 출동한다. 새 방식의 부하 초과/저전압 "
            "조건과 실제 저전압 전용 공급 시간은 비교 CSV에 별도로 기록했다. "
            "원자료 에너지 "
            "MWh와 AC 환산 MWh는 서로 다른 스케일이므로 혼용하지 않았다.",
            "",
            "## 동적 운용 상세",
            "",
            "| α | 부하 초과/저전압 조건 h | 부하 초과/저전압 전용 공급 h | "
            "AC 주입/남은 모선 초과 MWh | 부하 대응/전압 전용 MWh | "
            "수소 소비/보충 kg | SOC 초기→최저→종료 % | "
            "주 차량 LOH 초기→최저→종료 % | 차량 출동 회수 |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    dynamic_rows = comparison.loc[comparison.strategy.eq("Dynamic bus-level")]
    for row in dynamic_rows.itertuples(index=False):
        lines.append(
            f"| {row.alpha:.1f} | {row.load_excess_trigger_hours}/"
            f"{row.voltage_trigger_hours} | {row.load_response_hours}/"
            f"{row.voltage_only_response_hours} | {row.ac_injection_mwh:.3f}/"
            f"{row.residual_bus_excess_mwh_ac:.3f} | "
            f"{row.load_response_mwh_ac:.3f}/{row.voltage_only_mwh_ac:.3f} | "
            f"{row.h2_consumed_kg:.3f}/{row.h2_refilled_kg:.3f} | "
            f"40.0→{row.soc_min_pct:.1f}→{row.soc_end_pct:.1f} | "
            f"80.0→{row.main_loh_min_pct:.1f}→{row.main_loh_end_pct:.1f} | "
            f"{row.truck_dispatches} |"
        )
    lines.extend(
        [
            "",
            "차량별 배치 원자료는 `fig15_severity_dynamic_trucks.csv`에 있으며, 전체 "
            "접속 빈도는 다음과 같다.",
            "",
        ]
    )
    for row in dynamic_rows.itertuples(index=False):
        lines.append(
            f"- α={row.alpha:.1f}: 전체 모선:횟수 {row.truck_bus_frequency}; "
            f"주 차량 {row.main_bus_frequency}."
        )
    for result in results:
        lines.append(f"- α={result.alpha:.1f} 차량별 접속 빈도:")
        active = result.trucks.loc[result.trucks.bus.notna()]
        for truck in range(5):
            vehicle_rows = active.loc[active.truck.eq(truck)]
            frequencies = Counter(vehicle_rows.bus.astype(int))
            detail = (
                ", ".join(
                    f"Bus {bus} {count}회" for bus, count in sorted(frequencies.items())
                )
                or "0회"
            )
            role = "주 차량" if truck == 0 else "보조 HFC"
            lines.append(f"  - 차량 {truck} ({role}): {detail}")
    lines.extend(
        [
            "",
            "원 P1과 위치 재배치는 공급량·SOC·LOH·수소 사용량이 같다. 새 방식은 저전압 "
            "대응으로 더 많은 시간 출동할 수 있으므로 전압 효과를 비교할 때 "
            "공급 에너지와 연료 소비 차이를 반드시 함께 봐야 한다. "
            "잔여 모선 초과량은 계산상 임계 초과의 "
            "미충족분이며 물리적 미공급 전력을 뜻하지 않는다.",
            "",
        ]
    )
    for result in results:
        worst = result.hourly.iloc[result.worst_hour]
        no_supply = int(
            (result.hourly.mode2_trigger & ~result.hourly.supply_active).sum()
        )
        lines.append(
            f"- α={result.alpha:.1f}: Mode 2 조건인데 공급하지 못한 시간 "
            f"{no_supply} h. 기준 최악 시간 t={result.worst_hour}에는 "
            f"전압 {worst.vmin_baseline:.4f} p.u., 공급 "
            f"{worst.emergency_supply_mw:.3f} MW, SOC {worst.soc_start_pct:.1f}%, "
            f"함대 수소 {worst.fleet_h2_start_kg:.1f} kg이었다. "
            "기존 P1처럼 Mode 2 중 외부 수소 보충을 하지 않아 자원이 소진된 결과다."
        )
    lines.append("")
    first, second = (dynamic_rows.iloc[0], dynamic_rows.iloc[1])
    if np.isclose(first.ac_injection_mwh, second.ac_injection_mwh):
        lines.append(
            "**논문 조건 선택:** 0.95 p.u. 전압 조건이 출동을 지배하여 두 α의 "
            "Mode 2 조건(99 h), 실제 공급(34 h), 에너지·수소 사용량이 같다. "
            "누적 전압 위반량은 α=1.3의 "
            f"{first.cumulative_voltage_deficit_supported_pu_bus_h:.3f}에서 "
            f"α=1.5의 {second.cumulative_voltage_deficit_supported_pu_bus_h:.3f} "
            "p.u.·bus·h로 소폭 달라졌고, 두 조건 모두 저전압 시간이 80 h다. "
            "α=1.5는 완화된 부하 허용 조건의 대표 사례로 사용할 수 있지만 "
            "전압 성과 우월성을 주장할 근거는 약하다. α=1.3은 더 큰 계산상 모선 "
            "초과·잔여량을 보여 주는 가혹 조건이다. 어느 쪽도 완전한 전압 준수를 "
            "보여 주지 않으므로 논문에서는 이 한계를 명시해야 한다."
        )
    else:
        better = (
            first
            if first.cumulative_voltage_deficit_supported_pu_bus_h
            < second.cumulative_voltage_deficit_supported_pu_bus_h
            else second
        )
        lines.append(
            f"**논문 조건 선택:** 누적 전압 위반량은 α={better.alpha:.1f}가 더 작다. "
            "단, 공급 에너지·수소 소비 차이와 함께 해석해야 한다."
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
