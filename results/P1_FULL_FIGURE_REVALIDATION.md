# 최종 P1 시뮬레이션 및 Figure 재검증

기준 브랜치는 `codex/p1-multibus-powerflow` (`9303993`)이다. 동일한 저장소 입력 `Data file/data_file.csv`로 `HB-MPS main simulation.py`, `asset_ablation.py`, `strategy_sensitivity.py`, `p1_additional_analysis.py`, `emergency_dispatch_experiment.py`, `powerflow_validation.py`, `powerflow_heatmap.py`를 재실행했다. 메인 스크립트의 `run_simulation_for_alpha()`는 `main_p1_adapter.simulate_main_p1(frame, alpha, trucks=5)`를 호출한다. 각 재생성 CSV와 PNG는 아래 Figure 8의 범례 변경을 제외하면 추적된 결과와 바이트 단위로 동일했다. 나머지 PDF는 생성시각 메타데이터만 달라 원본을 유지했다.

## 핵심 수치와 회계

| α, 총 5대 | HFC (MWh) | ESS 비상 (MWh) | 미공급 (MWh) | 운영순편익 Πop (M KRW) | 회피편익 Bavoid (M KRW) | 사회적 순편익 (M KRW) |
|---|---:|---:|---:|---:|---:|---:|
| 1.3 | 26.403 | 4.560 | 29.993 | -17.586 | 151.802 | 134.216 |
| 1.5 | 1.570 | 0 | 0 | 0.119 | 7.697 | 7.815 |
| 1.8 | 0 | 0 | 0 | 0.578 | 0 | 0.578 |

α=1.3의 정확한 원자료 값은 HFC 26,402.814 kWh, ESS 비상 4,559.70075 kWh, 미공급 29,993.366171 kWh, Πop -17,585,824.147 KRW, Bavoid 151,801,503.774 KRW, Πop+Bavoid 134,215,679.628 KRW다. `p1_main_hourly.csv`의 504시간 전체는 P1 엔진의 HFC·ESS 공급, SOC·LOH, 실제 트럭 수, 수익·운영비·회피편익과 `p1_multibus_dispatch.validate_main_reference()`에서 대조된다.

Figure 8의 곡선은 시간별 `Revenue`, `-Op_Cost`, `Net_Step_Profit` 누적합이다. `Op_Cost = H2 구매비 + 계통 구매비 + ESS 열화비`이며, α=1.3에서 각각 16.865+0.786+1.086=18.737 M KRW다. `Revenue` 1.151 M KRW를 차감하면 Πop -17.586 M KRW다. 기존 범례는 ESS 열화비를 누락해 표시했으므로 글자만 `Total Op Cost (H2 + Grid + ESS Wear)`로 고쳤다. 수치, figsize, dpi, 색상, subplot, 글꼴은 변경하지 않았고 PNG 크기 3852×4245픽셀도 유지했다.

`figure_economic_value_all_cases`의 **HB-MPS Net Value**는 `Πop − 잔여 공급중단비용 = Πop + Bavoid − Base Case 위험비용`이다. 이는 기준계통에 비한 순효과를 절대 가치 축에 표시한 것으로, 논문의 `Net Societal Benefit = Πop + Bavoid`와 **같은 지표가 아니다**. α=1.3에서는 Net Value -164.636 M KRW, Base Case Risk Cost -298.852 M KRW이며 두 막대의 차이 134.216 M KRW가 Net Societal Benefit이다. α=1.5에서는 Net Value 0.119 M KRW와 Net Societal Benefit 7.815 M KRW가 다르고, α=1.8에서는 Base Case 위험비용이 0이어서 두 값이 같다. 그림의 기존 정의와 숫자는 바꾸지 않았다.

## 원고 Figure와 저장소 산출물 대응

원고 번호는 로컬 `IEEE_Access_hjyang_scjeon_v4.3.docx`의 caption과 대조했다. 표의 CSV는 그림에 사용한 값의 **저장된 검증본**이다. 생성 함수는 같은 실행 중 메모리의 결과를 직접 그린 뒤 CSV도 저장하므로, 그 CSV를 다시 읽어 그리지는 않는다. `유지`는 스크립트 재실행 후 CSV·PNG가 기존 추적 파일과 동일함을 뜻한다. 모든 Figure는 `.png`와 `.pdf`가 같은 기본 파일명을 쓴다.

| 원고 Figure | 저장소 `results/` 기본 파일명 | 사용 데이터와 생성 함수 | P1 반영 | 이번 재생성 결과 |
|---|---|---|---|---|
| 3 | `figure_load_profiles` | `Data file/data_file.csv`; `load profile.py:plot_load_profiles` | 입력 전용 | 유지, 미실행 |
| 4 | `figure_5_energy_supply_demand_mismatch` | 같은 입력; `Energy Supply vs. Demand Mismatch Analysis.py:plot_supply_demand_mismatch` | 입력 전용 | 유지, 미실행 |
| 5 | `figure_6_grid_resilience_fleet_deployment_all_cases` | `p1_main_hourly.csv`; `create_grid_resilience_figure` | 예, 최대 5대 | 유지 |
| 6 | `figure_7_asset_status_main_truck_all_cases` | `p1_main_hourly.csv`; `create_asset_status_figure` | 예, P1 SOC·LOH | 유지 |
| 7 | `figure_9_operational_mode_distribution_all_cases` | `p1_main_hourly.csv`; `create_mode_distribution_figure` | 예, P1 Mode 1/2 | 유지 |
| 8 | `figure_8_financial_flow_all_cases` | `p1_main_hourly.csv`; `create_financial_flow_figure` | 예, 열화비 포함 | **범례만 수정·재생성** |
| 원고에 없음 | `figure_economic_value_all_cases` | `p1_main_hourly.csv`; `create_economic_value_figure` | 예, Net Value 별도 정의 | 유지 |
| 9 | `figure_10_asset_ablation_energy` | `asset_ablation_summary.csv`; `asset_ablation_plot.plot_results` | 예, 공통 P1 엔진·단일 트럭 | 유지 |
| 10 | `figure_11_asset_ablation_value` | `asset_ablation_summary.csv`; `asset_ablation_plot.plot_results` | 예, 공통 P1 엔진·단일 트럭 | 유지 |
| 11 | `figure_12_dual_mode_policy_sensitivity` | `dual_mode_policy_sensitivity.csv`; `strategy_sensitivity.main` | 예, P1 정책 변형 | 유지 |
| 12 | `figure_14_voll_sensitivity` | `p1_voll_sensitivity.csv`; `p1_additional_analysis.main` | 예, P0/P1/P2 비교 | 유지 |
| 13 | `figure_15_ess_opportunity_cost` | `p1_opportunity_components.csv`; `p1_additional_analysis.main` | 예, P1−P0 기회비용 | 유지 |
| 14 | `figure_13_powerflow_voltage_heatmap` | `powerflow_voltage_by_bus_hour.csv`; `powerflow_heatmap.save_artifacts` | 예, P1 다중 노드 주입 | 유지 |
| 15 | `fig_powerflow_validation_bold` | `pf_results.csv`, `p1_multibus_hourly_injection.csv`; `powerflow_validation.main` → `powerflow_plot.save_figure` | 예, P1 다중 노드 주입 | 유지 |
| 16 | `figure_16_p1_multitruck_deployment` | `p1_multibus_vehicle_dispatch.csv`, `p1_multibus_hourly_injection.csv`; `p1_multibus_timeline.save_fleet_timeline` | 예, 5대 위치·활성시간 | 유지 |

`p1_main_hourly.csv`, `p1_main_summary.csv`, 자산 비교·민감도·VOLL·조류해석의 CSV와 위 표에서 `유지`로 표시한 PNG는 재실행 결과가 기존 파일과 동일하다. P0/P1/P2 별도 비교 Figure `emergency_figure_A_dispatch_energy`, `emergency_figure_B_economic_resilience`, `emergency_figure_C_reserve_sensitivity`도 `emergency_dispatch_summary.csv`를 이용해 재실행했으며 변경되지 않았다. `fig_powerflow.png`와 `figure_powerflow_voltage_profile`은 현재 P1 생성 경로와 연결되지 않은 기존 그림이므로 최종 P1 검증 Figure로 인용하지 않는다.

## 검증 결과

- 메인 시뮬레이션과 위 여섯 부가 스크립트가 모두 정상 완료됐다. α=1.3의 실제 HFC+ESS 공급 30.963 MWh와 미공급 29.993 MWh의 합은 초과수요 60.956 MWh에 일치한다.
- Figure 8 PNG/PDF를 육안 확인했고, 기존 13×15 inch·300 dpi·3행 구성과 PNG 픽셀 크기를 유지했다.
- IEEE 33-bus AC 계산은 세 α의 168시간 모두 수렴했다. α=1.3 최저전압은 0.9236→0.9270 pu, 0.95 pu 미만 시간은 99→99로 남았다. 전압개선과 실제 정전 복구를 동일시하지 않는다.
- 전체 테스트: `MPLBACKEND=Agg uv run --offline --python 3.14 --with numpy --with matplotlib --with pandas --with pandapower --with pytest python -m pytest -q tests` → **10 passed**.
- 입력 CSV와 입력 전용 Figure, 검증된 P1 급전 알고리즘은 수정하지 않았다. 변경된 산출물은 Figure 8 PNG/PDF와 이 검증 보고서뿐이다.
