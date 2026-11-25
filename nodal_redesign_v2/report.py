"""Evidence-based Korean analysis report for the six nodal experiment runs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from powerflow_validation import INDUSTRIAL_COLUMN, RESIDENTIAL_COLUMN

from .experiment import CaseRun


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
        "",
    ]


def write_report(
    runs: list[CaseRun], metrics: pd.DataFrame, frame: pd.DataFrame, path: Path
) -> None:
    """Explain model assumptions, six-case outcomes, limitations and selection."""
    records = metrics.sort_values(["alpha", "case_id"]).to_dict("records")
    raw_ind_peak = float(frame[INDUSTRIAL_COLUMN].max()) / 1000
    raw_res_peak = float(frame[RESIDENTIAL_COLUMN].max()) / 1000
    raw_simultaneous_peak = float(
        (frame[INDUSTRIAL_COLUMN] + frame[RESIDENTIAL_COLUMN]).max()
    ) / 1000
    total_rating = float(records[0]["total_rating_mw"])
    separate_peak_ratio = total_rating / (raw_ind_peak + raw_res_peak) * 100
    simultaneous_ratio = total_rating / raw_simultaneous_peak * 100
    c3_tight = next(row for row in records if row["case_id"] == "C3" and row["alpha"] == 1.3)
    c3_standard = next(row for row in records if row["case_id"] == "C3" and row["alpha"] == 1.5)
    c1_tight = next(row for row in records if row["case_id"] == "C1" and row["alpha"] == 1.3)

    lines = [
        "# IEEE 33-bus 모선별 동적 운용 재설계 및 검증",
        "",
        "이 보고서는 원본 메인 시뮬레이션과 기존 Nodal analysis를 변경하지 않고 "
        "별도 `nodal_redesign_v2`에서 168시간 × C1/C2/C3 × α=1.3/1.5를 AC 조류계산으로 재실행한 결과이다. "
        "수치는 `case_metrics.csv`, 모선별/차량별 상세값은 동봉 CSV에서 확인할 수 있다.",
        "",
        "## 1. 기존 모델의 문제점",
        "",
        f"원본 산업·주거 피크는 각각 {raw_ind_peak:.6f}, {raw_res_peak:.6f} MW이다. "
        "기존 C1은 산업 9개 모선 1.010 MW와 산업부하 기준 6.19% HB-MPS 환산을 사용한다. "
        "주거로 분류된 23개 모선의 정격은 2.705 MW이므로 원본 주거 피크 대비 34.90%에 해당한다. "
        "이와 별도로, **기존 코드의 부하 scaling은 그 23개 중 9개에만 순수 주거 프로파일을 적용하고 "
        "14개에는 산업·주거 가중 혼합 프로파일을 적용한다.** C1은 실제 이전 코드를 그대로 재실행한 참조값이며 "
        "이를 순수 9/23 이분류 시계열로 해석하면 안 된다.",
        "",
        "## 2. 모선 재분류와 보존한 계통 제원",
        "",
        "산업 모선은 14–21 및 23–33의 총 19개이며, "
        "주거 모선은 2–13 및 22의 13개이다. Bus 1은 slack(1.0 p.u.)이다. "
        "Bus 7은 주거/PV/ESS 충전/P2G, Bus 9는 주거/계통 ESS 충전이다. "
        "IEEE 33-bus의 결선, 선로 임피던스, 모선별 정격 P·Q와 역률은 바꾸지 않았다.",
        "",
    ]
    lines += _table(
        ("Case", "산업/주거 모선", "산업 정격 MW", "주거 정격 MW", "전체 정격 MW", "산업/주거 원본 피크 환산 %"),
        [
            (
                row["case_id"],
                f"{int(row['industrial_bus_count'])}/{int(row['residential_bus_count'])}",
                f"{row['industrial_rating_mw']:.3f}",
                f"{row['residential_rating_mw']:.3f}",
                f"{row['total_rating_mw']:.3f}",
                f"{row['industrial_load_scale_pct']:.2f}/{row['residential_load_scale_pct']:.2f}",
            )
            for row in records if row["alpha"] == 1.3
        ],
    )
    lines += [
        "## 3. 부하 및 HB-MPS 환산 방식",
        "",
        "각 산업·주거 부하의 원본 시계열은 해당 유형의 개별 최대값으로 나눈 뒤 "
        "각 모선의 IEEE 정격 P·Q에 동일한 시간별 배율을 적용했다(C2/C3). "
        "C1은 이전 혼합부하 scaling을 보존했다. C1과 C2의 HB-MPS는 산업 피크 기준, "
        "C3는 전체 정격을 원본 산업·주거 **개별 피크 합**으로 나눈 공통 비율을 "
        "Mode 1/2 공급과 PV·계통 충전 및 P2G에 한 번씩만 적용했다.",
        "",
        f"개별 피크 합은 {raw_ind_peak + raw_res_peak:.6f} MW, 이 기준 공통 환산은 "
        f"{separate_peak_ratio:.3f}%이다. 원본 산업+주거 **동시 최대값**은 "
        f"{raw_simultaneous_peak:.6f} MW이고 그 기준 비율은 {simultaneous_ratio:.3f}%이다. "
        "개별 피크는 서로 다른 시간에 나타날 수 있으므로 두 분모는 다르다. "
        "동시 최대 기준 16.9%를 C3의 환산계수로 사용하지 않았다.",
        "",
    ]
    lines += _table(
        ("Case", "α", "HB-MPS 환산 %", "시간별 계통 총부하 최대 MW", "Baseline AC 수렴 h"),
        [
            (row["case_id"], f"{row['alpha']:.1f}", f"{row['hb_mps_scale_pct']:.3f}",
             f"{row['total_grid_load_peak_mw']:.3f}",
             str(int(row["baseline_ac_converged_hours"])))
            for row in records
        ],
    )
    lines += [
        "## 4. 유지한 운용 알고리즘",
        "",
        "Mode 1은 기존 가격·SOC·수소 보충 조건을 사용하고, 방전 시 기준 전압이 가장 낮은 "
        "주거 모선을 선택한다. PV 기반 ESS 충전/P2G는 Bus 7, 계통 ESS 충전은 Bus 9에 반영한다. "
        "Mode 2는 산업 모선별 168시간 평균 부하의 α배를 초과한 경우에만 요청된다. "
        "초과량과 0.95 p.u. 전압 부족량을 각각 정규화하고 0.5/0.5로 합쳐 우선순위를 정한다. "
        "한 차량을 배치할 때마다 AC 조류계산을 다시 수행한다. HFC 1+4대 공급 후 "
        "주 차량 접속 모선에 남은 초과량에만 ESS backup을 적용한다. 저전압만으로 Mode 2는 발동하지 않는다.",
        "",
        "## 5. Case별 정량 비교",
        "",
        "다음의 `raw`는 차량 원본 자원 단위, `grid`는 IEEE 33-bus 환산 MWh이다. "
        "`residual excess`는 **가정한 grid supply capacity 대비 산업부하 초과분**이며 "
        "실제 정전·미공급 전력으로 해석하지 않는다.",
        "",
    ]
    lines += _table(
        ("Case", "α", "Mode 1 h/raw MWh", "Mode 2 요청/공급 h", "HFC/ESS raw MWh", "비상공급 grid MWh", "잔여 초과 grid MWh"),
        [
            (row["case_id"], f"{row['alpha']:.1f}",
             f"{int(row['mode1_hours'])}/{row['mode1_ess_mwh_raw']:.3f}",
             f"{int(row['mode2_trigger_hours'])}/{int(row['mode2_supply_hours'])}",
             f"{row['hfc_mwh_raw']:.3f}/{row['ess_emergency_mwh_raw']:.3f}",
             f"{row['emergency_supply_mwh_grid']:.3f}",
             f"{row['residual_industrial_excess_mwh_grid']:.3f}")
            for row in records
        ],
    )
    lines += _table(
        ("Case", "α", "차량 출동/투입 vehicle-h", "접속 모선 수", "SOC 최소/종료 %", "LOH 최소/메인 종료 %", "H₂ 소비/보충 kg"),
        [
            (row["case_id"], f"{row['alpha']:.1f}",
             f"{int(row['truck_dispatches'])}/{int(row['active_truck_hours'])}",
             str(int(row["unique_mode2_connection_buses"])),
             f"{row['soc_min_pct']:.1f}/{row['soc_end_pct']:.1f}",
             f"{row['loh_min_pct']:.1f}/{row['main_loh_end_pct']:.1f}",
             f"{row['h2_consumed_kg']:.1f}/{row['h2_refilled_kg']:.1f}")
            for row in records
        ],
    )
    lines += _table(
        ("Case", "α", "PV ESS 충전 raw/grid MWh", "계통 ESS 충전 raw/grid MWh", "P2G raw/grid MWh"),
        [
            (row["case_id"], f"{row['alpha']:.1f}",
             f"{row['pv_ess_charge_mwh_raw']:.3f}/{row['pv_ess_charge_mwh_grid']:.3f}",
             f"{row['grid_ess_charge_mwh_raw']:.3f}/{row['grid_ess_charge_mwh_grid']:.3f}",
             f"{row['p2g_use_mwh_raw']:.3f}/{row['p2g_use_mwh_grid']:.3f}")
            for row in records
        ],
    )
    deployment_rows = []
    for run in sorted(runs, key=lambda item: (item.result.alpha, item.case.name)):
        deployed = run.result.trucks.loc[
            run.result.trucks["mode"].eq("Mode 2")
            & run.result.trucks.bus.notna()
        ]
        locations = []
        for truck in range(5):
            counts = deployed.loc[deployed.truck.eq(truck), "bus"].astype(int).value_counts()
            locations.append(", ".join(
                f"Bus {bus}:{count}h" for bus, count in counts.head(3).items()
            ) or "-")
        deployment_rows.append(
            (run.case.name, f"{run.result.alpha:.1f}", *locations)
        )
    lines += [
        "Mode 2 차량별 주요 접속 모선과 횟수(상위 3개)는 다음과 같다. "
        "전체 모선·차량 조합과 공급 kWh는 `truck_deployment_summary.csv`에 있다.",
        "",
    ]
    lines += _table(
        ("Case", "α", "Main", "Aux 1", "Aux 2", "Aux 3", "Aux 4"),
        deployment_rows,
    )
    lines += _table(
        ("Case", "α", "최저전압 baseline/지원 pu", "최악 시점 개선 pu", "위반시간 baseline/지원 h", "누적 부족 baseline/지원 pu·bus·h", "선로손실 baseline/지원 MWh"),
        [
            (row["case_id"], f"{row['alpha']:.1f}",
             f"{row['vmin_baseline_pu']:.4f}/{row['vmin_supported_pu']:.4f}",
             f"{row['worst_hour_min_voltage_gain_pu']:.5f}",
             f"{int(row['voltage_violation_hours_baseline'])}/{int(row['voltage_violation_hours_supported'])}",
             f"{row['cumulative_voltage_deficit_baseline_pu_bus_h']:.3f}/{row['cumulative_voltage_deficit_supported_pu_bus_h']:.3f}",
             f"{row['line_losses_baseline_mwh']:.3f}/{row['line_losses_supported_mwh']:.3f}")
            for row in records
        ],
    )
    lines += [
        "모선별 168시간 전압 차이와 위반 횟수는 `bus_voltage_summary.csv`, "
        "각 차량의 모선별 접속 횟수 및 공급량은 `truck_deployment_summary.csv`에 저장했다.",
        "",
        "### 원본 PV 잉여와 실제 IEEE 계통 PV 여유의 차이",
        "",
        "원본 잉여는 `max(raw PV − raw 산업 − raw 주거, 0)`에 해당 Case의 HB-MPS 비율을 곱했다. "
        "계통 PV 여유는 `max(IEEE PV 발전 − IEEE 총부하, 0)`으로 계산했다. "
        "아래 `부족`은 운용 알고리즘이 PV 충전/P2G로 소비한 전력이 이 계통 여유를 넘은 양이다. "
        "이 비교는 계통 전체 순잉여 기준이며 Bus 7의 국지적 역송전 가능성과는 별도이다.",
        "",
    ]
    lines += _table(
        ("Case", "α", "원본 잉여 환산 MWh", "계통 PV 여유 MWh", "PV 충전+P2G grid MWh", "여유 초과 시간 h", "여유 초과 MWh"),
        [
            (row["case_id"], f"{row['alpha']:.1f}",
             f"{row['raw_pv_surplus_mwh_grid']:.3f}",
             f"{row['network_pv_surplus_mwh']:.3f}",
             f"{row['pv_ess_charge_mwh_grid'] + row['p2g_use_mwh_grid']:.3f}",
             str(int(row["pv_surplus_shortfall_hours"])),
             f"{row['pv_surplus_shortfall_mwh']:.3f}")
            for row in records
        ],
    )
    lines += [
        "이 차이를 숨기거나 충전/P2G를 임의로 줄이지 않았다. 따라서 잉여 PV의 물리적 자급을 "
        "입증하는 그림·문장에는 별도 전력수지 일치 실험이 필요하다.",
        "",
        "## 6. Figure별 해석",
        "",
        "각 Case/α 폴더의 Fig. 12는 실제 IEEE 결선과 열린 tie, 모선 유형, Bus 7/9 접속점을 보인다. "
        "주황색 산업 모선은 시간별 동적 Mode 2 접속 후보이며 고정 출동 위치가 아니다. "
        "Fig. 13(a)는 부하와 α·모선 평균 기준의 공급 허용량, (b)는 실제 Mode 1/2 시간, "
        "(c)는 차량별 접속 모선을 보여준다. Mode 2 요청에도 전혀 공급하지 못한 시간이 "
        "0이면 (b)의 `Requested but unavailable` 행을 그리지 않는다. "
        "Fig. 14(a)는 baseline 최악 시각의 모선별 전압과 접속, (b)는 전 기간 최저 모선 전압, "
        "(c)는 모선·시간별 지원 전후 전압 차이다. 0.95 p.u.는 성능 평가선이지 독립 출동 trigger가 아니다.",
        "",
        "## 7. 장점, 영향 분리 및 한계",
        "",
        "C1→C2는 부하 유형의 공간 배치, 동적 접속 후보 수, 그리고 HB-MPS 환산계수가 "
        "동시에 달라진다. 따라서 그 차이를 오직 차량 우선순위 변경 효과로 귀속할 수 없다. "
        "C2→C3는 동일한 19/13 부하 및 후보 모선에서 **HB-MPS 환산계수만** 바꾸므로 "
        "그 영향은 분리해 해석할 수 있다. C1의 14개 혼합 scaling도 독립 교란요인이다. "
        "더 엄격한 인과분해에는 추가 대조 실험이 필요하다. 산업 초과량은 정격부하와 "
        "가정된 허용량의 차이이고, 물리적 계통 미공급 전력 계측값이 아니다.",
        "",
        "## 8. 최종 실험 조건 추천",
        "",
        f"C3의 α=1.3은 비상 요청 {int(c3_tight['mode2_trigger_hours'])}시간과 실제 공급 "
        f"{int(c3_tight['mode2_supply_hours'])}시간을 포함하므로 주요 stress case로, "
        f"α=1.5는 요청 {int(c3_standard['mode2_trigger_hours'])}시간의 보조 비교로 권장한다. "
        "C3는 19/13 부하 구성과 양 Mode의 단일 환산 비율을 일관되게 적용하므로 "
        "새 대표 실험 **후보**로 적합하다. 다만 아래 PV 불일치가 남아 있어 "
        "PV 자급 운용의 최종 물리 검증 사례라고 단정하지 않는다. "
        f"실제로 α=1.3에서 C3 최저 지원전압 {c3_tight['vmin_supported_pu']:.4f} p.u.는 "
        f"C1의 {c1_tight['vmin_supported_pu']:.4f} p.u.보다 낮다. 반면 위반시간은 "
        f"{int(c1_tight['voltage_violation_hours_supported'])}→"
        f"{int(c3_tight['voltage_violation_hours_supported'])}시간으로 줄고, "
        f"누적 부족량은 {c1_tight['cumulative_voltage_deficit_supported_pu_bus_h']:.3f}→"
        f"{c3_tight['cumulative_voltage_deficit_supported_pu_bus_h']:.3f} pu·bus·h로 소폭 증가한다. "
        "따라서 최저전압 개선만을 근거로 C3의 우수성을 주장하지 않는다.",
        "",
        "## 9. 논문 Section IV-E 수정 지침",
        "",
        "1. 산업 19개·주거 13개 모선의 번호와 정격 2.510/1.205 MW를 명시한다.",
        "2. 부하 유형별 피크 정규화와 HB-MPS 공통 15.43% 환산의 분모를 구분한다. "
        "동시 피크 기준 16.9%는 사용하지 않았음을 밝힌다.",
        "3. Mode 2는 산업 모선별 부하 초과에서만 발동하고 전압은 우선순위·성과 지표로 사용한다고 쓴다.",
        "4. 0.95 p.u. 위반 시간, 최저전압, 누적 전압 부족량 및 선로손실은 `case_metrics.csv`의 "
        "C3 α=1.3/1.5 실제 수치로 교체한다. 개선되지 않은 항목도 그대로 보고한다.",
        "5. 차량 원본 kWh/MWh와 IEEE 33-bus 환산 MWh를 혼용하지 않는다. "
        "잔여 산업 초과량을 실제 정전 미공급량이라고 부르지 않는다.",
        "6. Bus 7의 PV 충전/P2G는 현재 네트워크 PV 순잉여와 불일치하므로 "
        "자급 가능한 PV 잉여 운용으로 단정하지 않는다.",
        "",
        "## 10. 재현·검증",
        "",
        "`python -m nodal_redesign_v2.run`으로 전체 Case를 재실행한다. "
        "각 폴더에는 hourly/bus_hourly/trucks CSV와 Fig. 12–14 PNG·벡터 PDF가 저장된다. "
        "`nodal_redesign_v2.metrics.validate_run`은 매 시간 산업 초과량=공급+잔여, "
        "원본/계통 에너지 변환, HFC 출력, SOC·LOH와 수소/ESS 재고, "
        "Mode 1·2 접속 모선, AC 수렴·유한 전압을 검증한다.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
