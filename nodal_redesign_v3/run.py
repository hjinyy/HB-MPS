"""Reproduce the isolated AC-balanced PV variant and its Figs. 13–14.

Run: ``uv run --with-requirements requirements.txt python -m nodal_redesign_v3.run``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from powerflow_validation import INPUT_PATH, load_profiles
from nodal_redesign_v2.experiment import ALPHAS, CASES, CaseRun, simulate
from nodal_redesign_v2.metrics import summarize, validate_run
from nodal_redesign_v2.plots import save_operation, save_voltage

from .pv import PV_VOLTAGE_CEILING_PU, PVPlan, plan_pv, screen_peak_siting

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "nodal_redesign_v3"


def _validate_pv(run: CaseRun, plan: PVPlan) -> None:
    """Require AC export headroom for every PV charge and P2G action."""
    validate_run(run)
    hourly = run.result.hourly
    if not np.allclose(hourly.pv_generation_mw, plan.dispatch_mw):
        raise AssertionError("Actual PV output differs from the AC-feasible plan")
    if not np.allclose(
        hourly.network_pv_surplus_mw,
        plan.hourly.ac_export_surplus_mw,
        atol=1e-7,
    ):
        raise AssertionError("PV surplus differs from baseline AC export")
    if (hourly.pv_use_mw > hourly.network_pv_surplus_mw + 1e-7).any():
        raise AssertionError("PV charging or P2G uses unavailable AC export")
    if np.max(run.result.baseline_profiles) > PV_VOLTAGE_CEILING_PU + 1e-6:
        raise AssertionError("Baseline PV dispatch exceeds the voltage ceiling")


def _summary(run: CaseRun, frame: pd.DataFrame, plan: PVPlan) -> dict[str, float | int | str]:
    """Combine existing operation metrics with PV and upper-voltage evidence."""
    result = summarize(run, frame)
    hourly = run.result.hourly
    result.update({
        "pv_nameplate_mw": plan.nameplate_mw,
        "pv_potential_mwh": float(plan.hourly.pv_potential_mw.sum()),
        "pv_dispatch_mwh": float(plan.hourly.pv_dispatch_mw.sum()),
        "pv_curtailed_mwh": float(plan.hourly.pv_curtailed_mw.sum()),
        "pv_curtailment_hours": int(plan.hourly.pv_curtailed_mw.gt(1e-6).sum()),
        "ac_export_surplus_mwh": float(plan.hourly.ac_export_surplus_mw.sum()),
        "ac_export_hours": int(plan.hourly.ac_export_surplus_mw.gt(1e-6).sum()),
        "pv_use_mwh_grid": float(hourly.pv_use_mw.sum()),
        "pv_use_exceedance_mwh": float(hourly.pv_surplus_shortfall_mw.sum()),
        "reverse_power_peak_mw": float((-plan.hourly.baseline_slack_import_mw).max()),
        "vmax_baseline_pu": float(run.result.baseline_profiles.max()),
        "vmax_supported_pu": float(run.result.supported_profiles.max()),
        "overvoltage_hours_baseline": int(np.any(
            run.result.baseline_profiles > PV_VOLTAGE_CEILING_PU + 1e-6, axis=1
        ).sum()),
        "overvoltage_hours_supported": int(np.any(
            run.result.supported_profiles > PV_VOLTAGE_CEILING_PU + 1e-6, axis=1
        ).sum()),
    })
    return result


def _markdown_table(frame: pd.DataFrame, columns: tuple[str, ...]) -> str:
    headers = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in frame.loc[:, list(columns)].itertuples(index=False, name=None)
    ]
    return "\n".join((headers, divider, *rows))


def _write_report(metrics: pd.DataFrame, screening: pd.DataFrame, plan: PVPlan) -> None:
    """State the PV assumptions, measured gains and remaining constraints."""
    old = pd.read_csv(ROOT / "results" / "nodal_redesign_v2" / "case_metrics.csv")
    old = old.loc[old.case_id.eq("C3") & old.alpha.isin(ALPHAS)]
    comparison = []
    for row in metrics.itertuples(index=False):
        prior = old.loc[old.alpha.eq(row.alpha)].iloc[0]
        comparison.append({
            "α": f"{row.alpha:.1f}",
            "PV 정격: 이전→현재 (MW)": f"0.743→{row.pv_nameplate_mw:.3f}",
            "PV 충전+P2G: 이전→현재 (MWh, 계통)":
                f"{prior['pv_ess_charge_mwh_grid'] + prior['p2g_use_mwh_grid']:.3f}→{row.pv_use_mwh_grid:.3f}",
            "Mode 2 요청/공급 (h)": f"{int(row.mode2_trigger_hours)}/{int(row.mode2_supply_hours)}",
            "최저 지원전압: 이전→현재 (p.u.)":
                f"{prior['vmin_supported_pu']:.4f}→{row.vmin_supported_pu:.4f}",
            "0.95 미만 시간: 이전→현재 (h)":
                f"{int(prior['voltage_violation_hours_supported'])}→{int(row.voltage_violation_hours_supported)}",
            "지원 후 최대전압 (p.u.)": f"{row.vmax_supported_pu:.4f}",
        })
    comparison_frame = pd.DataFrame.from_records(comparison)
    placement = screening.copy()
    for field in ("pv_mw", "vmax_pu", "slack_import_mw", "line_loss_mw"):
        placement[field] = placement[field].map(lambda value: f"{value:.4f}")
    lines = [
        "# IEEE 33-bus PV 전력수지 보정과 Fig. 13–14 재생성",
        "",
        "## 모델링 변경",
        "",
        "이 결과는 기존 `nodal_redesign_v2`의 기본 실행·CSV·그림을 보존한 별도 실험이다. "
        "산업 19개/주거 13개 모선, 각 부하의 정격·프로파일, HB-MPS의 15.43% 공통 환산, "
        "α=1.3/1.5, 차량 5대와 Mode 1/2 운용 규칙은 유지했다. "
        "원본 PV 시간별 발전량(kWh)을 HB-MPS와 같은 비율로 환산한 발전 가능량의 최대값을 "
        "Bus 7 PV 설비 정격으로 정의했다.",
        "",
        f"PV 정격은 {plan.nameplate_mw:.3f} MW이고 잠재 발전량은 "
        f"{plan.hourly.pv_potential_mw.sum():.3f} MWh이다. "
        f"모델링 상한 {PV_VOLTAGE_CEILING_PU:.2f} p.u.를 각 시간의 **HB-MPS 투입 전** "
        "AC 조류계산에 적용하여 PV를 필요한 만큼 출력 제한했다. "
        "제한량은 `pv_hourly.csv`에 저장했다. IEEE benchmark의 모든 선로 "
        "`max_i_ka`가 99,999 kA의 사실상 무제한 값이므로, 이 실험은 유효한 "
        "열 한계를 검증하지 못한다.",
        "",
        "ESS 충전/P2G에 쓸 수 있는 PV 잉여는 원본 발전−부하가 아니라 "
        "**기준 AC 조류계산의 slack 역송전량 `max(−P_slack, 0)`**으로 정의했다. "
        "이 값에는 계통 부하와 활성 선로손실이 반영된다. 기존 비상/경제 운용 순서를 "
        "그대로 적용하되, PV 충전·P2G는 이 잉여 이내에서만 수행한다. "
        "기준 상태의 수출 가능량을 상한으로 사용하므로 HB-MPS 충전으로 생길 수 있는 "
        "추가 PV 수용 여유는 활용하지 않는 보수적 계산이다.",
        "",
        "## PV 출력 및 계통 한계",
        "",
        f"실제 PV 발전 {plan.hourly.pv_dispatch_mw.sum():.3f} MWh, 출력 제한 "
        f"{plan.hourly.pv_curtailed_mw.sum():.3f} MWh "
        f"({int(plan.hourly.pv_curtailed_mw.gt(1e-6).sum())}시간), "
        f"기준 계통 수출 가능 잉여 {plan.hourly.ac_export_surplus_mw.sum():.3f} MWh "
        f"({int(plan.hourly.ac_export_surplus_mw.gt(1e-6).sum())}시간)이다. "
        "이는 공급하지 못한 부하량이 아니라 PV 출력 제한과 기준 역송전 여유다.",
        "",
        "원본 PV의 최고 출력 시각에, 출력 제한 전 15.43% 환산량을 접속 위치별로 "
        "투입해 비교했다. 음수 slack은 상위 계통으로의 역송전을 뜻한다. "
        "정격 비례 분산은 이 한 시각의 전압 상한 문제를 해결하지 못했다. "
        "따라서 실제 재실행은 기존 Bus 7 접속을 유지하고 시간별 출력 제한을 적용했다.",
        "",
        _markdown_table(
            placement,
            ("placement", "peak_hour", "pv_mw", "vmax_pu", "slack_import_mw", "line_loss_mw"),
        ),
        "",
        "PV가 계통 총부하를 초과하는 시간에는 HB-MPS가 잉여 일부를 사용한 뒤에도 "
        "역송전이 남을 수 있다. 이 실험은 역송전을 금지하거나 PV 정격을 최적화했다고 "
        "주장하지 않는다. 1.05 p.u. 상한은 명시적 모델링 가정이다.",
        "",
        "## C3 이전 실험과의 결과 비교",
        "",
        _markdown_table(comparison_frame, tuple(comparison_frame.columns)),
        "",
    ]
    for row in metrics.itertuples(index=False):
        hourly = pd.read_csv(
            OUT / f"alpha_{str(row.alpha).replace('.', '_')}" / "hourly.csv"
        )
        unavailable = hourly.loc[hourly.mode2_trigger & ~hourly.supply_active]
        lines += [
            f"### α={row.alpha:.1f}",
            "",
            f"실제 PV ESS 충전 {row.pv_ess_charge_mwh_grid:.3f} MWh, P2G "
            f"{row.p2g_use_mwh_grid:.3f} MWh, 총 {row.pv_use_mwh_grid:.3f} MWh이다. "
            f"AC 잉여 초과량은 {row.pv_use_exceedance_mwh:.6f} MWh이다. "
            f"기준 최대전압 {row.vmax_baseline_pu:.4f} p.u., 지원 후 최대전압 "
            f"{row.vmax_supported_pu:.4f} p.u.이며, 1.05 초과 시간은 "
            f"기준 {row.overvoltage_hours_baseline}시간/지원 후 "
            f"{row.overvoltage_hours_supported}시간이다. "
            f"기준 역송전 최고량은 {row.reverse_power_peak_mw:.3f} MW이다. "
            f"0.95 미만 전압 시간은 기준 {row.voltage_violation_hours_baseline}시간/"
            f"지원 후 {row.voltage_violation_hours_supported}시간이다.",
            "",
        ]
        if not unavailable.empty:
            hours = ", ".join(str(int(value)) for value in unavailable.t)
            lines += [
                f"Mode 2 요청에도 전혀 공급하지 못한 시각은 t={hours}이다. "
                f"첫 해당 시각의 차량 전체 수소는 "
                f"{max(float(unavailable.fleet_h2_start_kg.iloc[0]), 0.0):.3f} kg, "
                f"Main ESS SOC는 {unavailable.soc_start_pct.iloc[0]:.1f}%였다. "
                "현행 HFC 우선 알고리즘은 HFC 차량을 접속하지 못하면 ESS 단독 "
                "긴급 출동으로 전환하지 않아 공급이 0이었다. 이 상황을 감추기 위해 "
                "차량 자원이나 우선순위를 변경하지 않았다.",
                "",
            ]
    lines += [
        "## Fig. 13–14와 해석 한계",
        "",
        "각 α 폴더에는 Fig. 13(운용·차량 배치)과 Fig. 14(모선 전압)의 PNG·벡터 PDF, "
        "시간/모선/차량 CSV가 있다. Fig. 12의 Bus 7 PV 접속과 IEEE 33-bus 토폴로지는 "
        "변경하지 않았다. Fig. 13의 Mode 2 trigger는 여전히 산업 모선 부하 초과에만 "
        "기반하며 PV 또는 저전압만으로 새로 발동하지 않는다.",
        "",
        "PV 출력 제한은 기준 조류계산에서만 결정한다. 지원 전압이 1.05 p.u.를 "
        "넘는 시간이 있으면 그대로 보고하며, 이를 해소하는 HB-MPS–PV 공동 제어는 "
        "본 운용 알고리즘에 포함되지 않는다. 역송전 허용 및 Bus 7 단일 접속의 "
        "적정성도 현장 계통 제약으로 추가 검증이 필요하다.",
        "",
        "## 재현",
        "",
        "`uv run --with-requirements requirements.txt python -m nodal_redesign_v3.run`",
        "",
    ]
    (OUT / "ANALYSIS_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Generate two PV-consistent nodal cases and save all evidence."""
    frame = load_profiles(INPUT_PATH)
    case = CASES[2]
    OUT.mkdir(parents=True, exist_ok=True)
    plan = plan_pv(frame, case)
    plan.hourly.to_csv(OUT / "pv_hourly.csv", index=False)
    screening = screen_peak_siting(frame, case)
    screening.to_csv(OUT / "pv_siting_screen.csv", index=False)
    rows = []
    for alpha in ALPHAS:
        run = simulate(case, alpha, frame, pv_generation_profile_mw=plan.dispatch_mw)
        _validate_pv(run, plan)
        directory = OUT / f"alpha_{str(alpha).replace('.', '_')}"
        directory.mkdir(parents=True, exist_ok=True)
        run.result.hourly.to_csv(directory / "hourly.csv", index=False)
        run.result.buses.to_csv(directory / "bus_hourly.csv", index=False)
        run.result.trucks.to_csv(directory / "trucks.csv", index=False)
        save_operation(run, directory)
        save_voltage(run, directory)
        rows.append(_summary(run, frame, plan))
        print(f"Saved PV-balanced C3, α={alpha:.1f}: {directory}", flush=True)
    metrics = pd.DataFrame.from_records(rows)
    metrics.to_csv(OUT / "case_metrics.csv", index=False)
    _write_report(metrics, screening, plan)


if __name__ == "__main__":
    main()
