# P1 메인 알고리즘 통합 및 Figure 재생성 검증

## 범위와 재현 방법

- 작업 브랜치: `codex/p1-main-integration` (`codex/emergency-dispatch-validation`, `9c0d130`에서 분기). `main`과 원격 저장소는 변경하지 않았다.
- 재생성 전 `results/`의 기존 41개 파일을 `legacy_pre_p1.tar.gz`에 보존하고 파일별 SHA-256을 `legacy_pre_p1.sha256`에 기록했다. 이전 결과와 아래 신규 결과는 **트럭·수소·비용 가정이 다르므로** 동일 조건의 성능 비교로 해석하지 않는다.
- 원자료는 저장소의 동일한 168시간 산업·주택 부하, PV, SMP, LCOE, 수소가격이다. 시간 간격은 1시간이다. α는 1.3, 1.5, 1.8이고 메인 Figure 5–9 및 조류계산의 기본 fleet는 **총 5대(주 트럭 1대+보조 최대 4대)**다. 별도 fleet 검증은 총 1·2·5대를 사용한다.
- 재실행: `MPLBACKEND=Agg uv run --offline --python 3.14 --with numpy --with matplotlib --with pandas --with pandapower python 'HB-MPS main simulation.py'`; 나머지는 `python asset_ablation.py`, `python strategy_sensitivity.py`, `python powerflow_validation.py`, `python powerflow_heatmap.py`, `python p1_additional_analysis.py`를 같은 `uv run` 환경에서 실행한다. `asset_ablation.py`와 `strategy_sensitivity.py`는 자체 그림 생성 호출을 포함한다.

## 구현과 기존 알고리즘의 차이

| 파일 | 핵심 역할 |
| --- | --- |
| `HB-MPS main simulation.py`, `main_p1_adapter.py` | 원래 Figure 5–9 plotting 코드를 유지하고 공식 `run_simulation_for_alpha`를 공통 P1 엔진에 연결. 168시간 상태와 집계를 기존 Figure 열로 변환. `run_legacy_simulation_for_alpha`는 이전 재현용으로 보관. |
| `hb_inputs.py`, `emergency_dispatch.py`, `emergency_dispatch_model.py` | 입력 및 P0/P1/P2 공통 엔진. 트럭별 수소, 유한 fleet, HFC 우선, 잔여 수요에만 ESS, Mode 1 경제 운전과 비용 계상. α=1.8과 용량·Mode 1 임계값 변형 지원. |
| `emergency_validation.py`, `emergency_dispatch_experiment.py` | 시나리오 검증을 공유 모듈로 분리. 기존 36개 P0/P1/P2 비교 집계값은 변경 전과 동일함을 확인. |
| `asset_ablation.py`, `strategy_sensitivity.py` | Figure 10–12가 같은 P1 엔진을 사용. ESS-only, HFC-only, Hybrid 및 동일 3 MWh 정격 비교, 3×3 정책 민감도 유지. |
| `powerflow_validation.py`, `powerflow_heatmap.py` | α별 실제 P1 시간별 HFC+ESS 공급을 버스 18 주입으로 변환하여 Figure 13 갱신. |
| `p1_additional_analysis.py` | Figure 14·15, VOLL 손익분기, P0 대비 기회비용, 1·2·5대 fleet 표 생성. |
| `tests/test_p1_main_integration.py` | 메인/ablation 엔진 정합성, 조류계산 주입량, Figure 크기 회귀 검증. |

기존 메인은 필요한 보조 트럭을 즉시 투입하고 수소 부족 때도 초과 수요 전체를 공급 처리할 수 있었다. 새 메인은 각 차량의 저장 수소와 이동 소비량, 시간당 정격을 적용한다. 가용 HFC가 부족할 때만 주 트럭 ESS가 물리적 최소 SOC 0.1까지 보조한다. Reserve SOC를 강제하는 P2와 다르다. Mode 1의 **경제적 방전 진입 기준 SOC 0.3**은 Mode 2의 물리적 하한 0.1과 역할이 다르다.

## 물리·경제 모델

시간 (t)의 요구 에너지와 실제 공급은 다음과 같다. 여기서 모든 에너지는 1시간 구간의 kWh이고, ESS 700 kWh는 **배터리 내부 인출 한도**이므로 AC 공급에 효율 0.95를 한 번 적용한다.

\[
E_{\rm req,t}=\max(E_{\rm Ind,t}-\alpha\overline E_{\rm Ind},0),\quad
E_{\rm HFC,i,t}=\min\{E_{\rm remaining,t},500,(H_{i,t}-0.136)^+\times16.65\}.
\]

투입 차량의 수소 재고에서 발전용 (E_{\rm HFC,i,t}/16.65) kg와 이동용 0.136 kg을 차감한다. 주 트럭부터 가용한 보조 트럭까지 순서대로 투입하고, 저장량이 이동용 수소보다 적으면 투입하지 않는다. 최대 5대는 시간당 최대 2,500 kWh의 명목 HFC 공급능력을 뜻하지만 실제량은 저장량으로 다시 제한된다.

\[
E_{\rm ESS,t}^{\rm emg}=0.95\min\left\{700,\left[E_{\rm ESS,t}-0.1\times1500\right]^+,\frac{[E_{\rm req,t}-E_{\rm HFC,t}]^+}{0.95}\right\},
\quad E_{\rm unserved,t}=E_{\rm req,t}-E_{\rm HFC,t}-E_{\rm ESS,t}^{\rm emg}.
\]

내부 인출량을 그 시간의 ESS 저장 에너지에서 바로 뺀다. 다음 시간 Mode 1의 경제적 방전·계통 충전은 이 상태에서 계속된다. SOC 운전 범위는 0.1–0.9, 초기 SOC는 0.4다. HFC 저장용량은 차량당 전력환산 1,500 kWh, 초기 LOH는 0.8이며 Mode 1에서 LOH<0.6이면 0.9까지 외부 수소를 구매한다. 보조 차량도 각각 독립적으로 보충한다. ESS 충전은 최대 300 kWh/h, 방전 내부 인출은 최대 700 kWh/h다.

\[
\Pi_{\rm op}=R_{\rm Mode1}-C_{\rm H2,purchase}-C_{\rm grid,purchase}-C_{\rm ESS,wear},\quad
B_{\rm avoid}=\sum_t(E_{\rm HFC,t}+E_{\rm ESS,t}^{\rm emg})\,\mathrm{VOLL}_{60},\quad
V_{\rm societal}=\Pi_{\rm op}+B_{\rm avoid}.
\]

60분 VOLL은 원래 지수식의 4,902.751 KRW/kWh다. ESS 비상 공급은 Mode 1 매출에 넣지 않는다. 수소는 외부 구매 시점에만 비용을 기록하며 저장 수소 사용에 구매비를 재계상하지 않는다. ESS 열화비는 내부 인출 또는 충전 kWh당 50 KRW다. 이동 수소는 실제 재고에서 차감한다. **ESS-only ablation**처럼 탱크가 없는 경우 이동용 수소를 현장에서 구매하는 모델 가정이 별도로 적용된다. 종료 재고의 잔존가치는 주 KPI에 합산하지 않고 별도로 검토한다.

## 기존 Figure 5–13 결과

| α, 총 5대 | Mode 2 시간 | HFC (MWh) | ESS 비상 (MWh) | 미공급 (MWh) | Πop (백만원) | Bavoid (백만원) | V사회 (백만원) | 종료 SOC / 주 LOH |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1.3 | 39 | 26.403 | 4.560 | 29.993 | -17.586 | 151.802 | 134.216 | 0.10 / 0.90 |
| 1.5 | 8 | 1.570 | 0 | 0 | 0.119 | 7.697 | 7.815 | 0.29 / 1.00 |
| 1.8 | 0 | 0 | 0 | 0 | 0.578 | 0 | 0.578 | 0.10 / 0.9985 |

Figure 5의 입력 수급 곡선은 공급 전략과 무관하므로 PNG가 원본과 SHA-256까지 동일했다. Figure 6–9의 트럭 투입·SOC/LOH·재무 흐름·모드 비율은 P1 경로를 반영했다. Figure 5–13 PNG 전체의 **픽셀 폭·높이는 백업본과 동일**하며 Figure 5–13의 plotting 함수에서 캔버스, subplot, 색상, 글꼴, 범례, 축 설정은 변경하지 않았다. PDF도 같은 파일명으로 재생성했다. Figure 8의 기존 범례 `Total Op Cost (H2 + Grid)`는 시각 형식 보존 때문에 유지했지만 **새 총비용에는 ESS wear도 포함**된다. 논문 최종 편집에서는 범례를 `H2 + Grid + ESS Wear`로 고쳐야 한다.

α=1.3의 Legacy 메인은 초과수요 약 60.956 MWh를 모두 공급한 것으로 기록하여 Bavoid 298.852백만원, 미공급 0이었다. 유한 fleet·저장 수소를 적용한 P1 메인은 30.963 MWh만 공급하고 29.993 MWh를 남겼다. Legacy의 Πop -37.992백만원과 P1의 -17.586백만원 차이에는 실제 공급 감소와 구매시점 기준으로 통일한 수소 회계가 함께 들어 있으므로 전략 효과만으로 분해할 수 없다. α=1.5는 두 모델 모두 1.570 MWh를 공급하며, Legacy Πop 약 0.086백만원과 P1 0.119백만원 차이는 회계·상태 경로에서 발생한다. α=1.8은 비상 모드가 없으므로 P1 dispatch 효과가 없다.

Figure 10–11의 α=1.3, 총 1대 비교에서 ESS-only는 4.560 MWh, HFC-only는 5.523 MWh, Hybrid P1은 HFC 5.523+ESS 4.560 MWh를 공급했다. Hybrid의 사회적 가치 45.338백만원은 HFC-only 23.704백만원보다 높지만 **동일 총 3 MWh 저장에너지의 HFC-only 47.408백만원보다는 낮다**. 자산조합의 보편적 우월성으로 쓰면 안 된다. Figure 12의 3×3은 Mode 1 방전 시작 SOC와 높은 LCOE 분위수 변화이며, P2의 Mode 2 reserve 민감도와 다른 실험이다. α=1.3에서 Πop은 -4.262~-3.448백만원, 미공급은 50.873~54.022 MWh다. 같은 CSV의 Πop+Bavoid를 산출하면 V사회는 30.494~45.368백만원이므로 설정에 따른 기회비용이 남는다.

Figure 13 조류해석은 원래 IEEE 33-bus 부하배분·정규화, Slack 1.0 pu, PV 버스 7, HB-MPS 접속 버스 18, 주입 무효전력 0을 유지한다. HB-MPS 주입은 원자료의 산업 부하 최대값 대비 **실제 공급 kWh의 비율**을 IEEE 산업군 정격 MW에 곱해 환산한다. 따라서 원자료 kWh를 배전망 MW로 직접 대입하지 않았다. α=1.3 최저 전압은 무주입 0.923565→P1 주입 0.926960 pu, α=1.5는 0.923565→0.924841 pu, α=1.8은 동일 0.923565 pu다. 0.95 pu 미만 시간 수는 각 α에서 **99→99**로 변하지 않았다. 이 결과는 전압 개선 가능성을 보이지만 0.95 pu 기준 충족을 입증하지 않는다. 이동시간·위치·버스별 실제 정전 수요가 없으므로 현재 주입 위치가 실제 dispatch를 보증하지도 않는다.

## Figure 14: VOLL 민감도

`figure_14_voll_sensitivity.png/.pdf`는 α=1.3에서 총 1·2·5대 각각 P0/P1/P2를 비교한다. VOLL 배율 0, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 1.5, 2를 계산했다. Rule-based 운전은 VOLL을 참조하지 않으므로 **물리적 공급량과 운영비는 고정하고 회피편익만 재평가**했다.

P0=P1의 손익분기 VOLL은 세 fleet 모두 **204.347 KRW/kWh**(기준값의 약 4.17%)다. 1대에서 배율 0.025(122.569 KRW/kWh)일 때 P0 V사회 -2.485백만원 > P1 -2.858백만원이다. 배율 0.05(245.138 KRW/kWh)에서는 P1 -1.622백만원 > P0 -1.809백만원으로 순위가 역전된다. 기준 VOLL에서는 P1이 P0보다 21.455백만원 높다. 손익분기 값이 낮아 기준 조건에서 P1의 이점은 크지만 VOLL 가정이 이 결론의 핵심이며, 한 주의 값만으로 다른 고객군·정전시간에 일반화할 수 없다.

## Figure 15: ESS 경제 운용 기회비용

`figure_15_ess_opportunity_cost.png/.pdf`는 **동일 α=1.3·총 1대**에서 P1−P0의 실제 차이를 분해한다. Mode 1 ESS 공급은 8.654→5.709 MWh(-2.945), 계통 충전은 6.106→7.895 MWh(+1.789)이다. PV→ESS 3.010 MWh와 PV→H2 양은 이 입력에서 P0/P1 간 차이가 없다.

| P1−P0 구성요소 | 백만원 |
| --- | ---: |
| Mode 1 매출 감소 | -0.600 |
| 추가 계통 구매비 | -0.159 |
| 추가 ESS 열화비 | -0.174 |
| 외부 수소 구매비 변화 | 0 |
| 추가 공급중단 회피편익 | +22.388 |
| **사회적 순편익 차이** | **+21.455** |

운영 순편익 감소는 -0.933백만원으로 위 항목과 일치한다. 종료 SOC는 P0/P1 모두 0.1이고, 종료 재고 차이를 마지막 시간의 동일한 SMP·수소가격으로 평가하면 약 +0.003백만원으로 주 KPI 순위를 바꾸지 않는다. 이는 종료 후 새로운 정전의 서비스 가치를 평가한 수치가 아니다.

## Fleet availability 검증

단위는 에너지 MWh, 화폐 백만원. 전체 원시값은 `p1_fleet_summary.csv`에 있다.

| α | 총 트럭 | HFC | ESS 비상 | ESS Mode 1 | 미공급 | Πop | Bavoid | V사회 | 최종 SOC/주 LOH |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1.3 | 1 | 5.523 | 4.560 | 5.709 | 50.873 | -4.094 | 49.432 | 45.338 | 0.10/0.90 |
| 1.3 | 2 | 10.741 | 4.560 | 5.709 | 45.655 | -7.467 | 75.016 | 67.549 | 0.10/0.90 |
| 1.3 | 5 | 26.403 | 4.560 | 5.709 | 29.993 | -17.586 | 151.802 | 134.216 | 0.10/0.90 |
| 1.5 | 1/2/5 | 1.570 | 0 | 12.977 | 0 | 0.119 | 7.697 | 7.815 | 0.29/1.00 |
| 1.8 | 1/2/5 | 0 | 0 | 14.060 | 0 | 0.578 | 0 | 0.578 | 0.10/0.9985 |

α=1.3에서는 트럭을 늘려도 수소 재고가 소진되는 사건이 있어 ESS 백업 4.560 MWh가 사라지지 않는다. 5대로도 29.993 MWh가 미공급이다. α=1.5는 한 대 HFC만으로 충분하므로 ESS 백업이 없고 fleet를 늘려도 결과가 같다. α=1.8은 Mode 2 자체가 없다. Figure 6과 이 표가 fleet 효과를 이미 제시하므로 Figure 16은 중복을 피하기 위해 추가하지 않았다.

## 검증 결과와 한계

전체 테스트 **7개 통과**. 공통 검증기는 모든 시간의 수요=HFC+ESS+미공급, SOC/트럭별 LOH와 출력 한계, 투입 대수, H2 및 ESS 에너지 수지, 외부 구매·열화비, 비음수 및 유한값을 검사한다. 합성 테스트는 HFC 소진, ESS 보조, P2 reserve, 구매시점 단일 비용을 강제한다. 메인 5대 결과와 공통 엔진, Hybrid ablation 1대와 공통 엔진, 조류계산 시간별 주입량과 P1 공급량을 각각 대조했다. 기존 P0/P1/P2 36행 요약의 값도 회귀 확인했다. Figure 5–13 PNG 치수와 Figure 5 원본 해시를 검사했다. 검증 실행 명령은 `MPLBACKEND=Agg uv run --offline --python 3.14 --with numpy --with matplotlib --with pandas --with pandapower --with pytest python -m pytest -q tests`다.

입력은 1주일 집계 부하이고 정전 발생 버스·트럭 위치·이동시간·노선 정보가 없다. 이동은 정해진 수소 0.136 kg 소비만 표현한다. 비상 시간 밖에서는 외부 수소를 즉시 보충할 수 있다고 가정한다. 보조 트럭은 동일 1.5 MWh 수소탱크와 500 kWh/h HFC를 가진다. 설비투자비·고정 유지비, PV 판매/출력제한 기회비용, 재고의 미래 옵션가치와 후속 주의 운전은 제외된다. 가격 분위수는 168시간 전체 입력에서 계산하므로 완전한 실시간 정보 제약을 구현한 것은 아니다. 실제 수소 보급속도, 이동 가능성, 버스별 정전 수요, 장기 시계열 및 VOLL의 고객군별 값이 추가 검증되어야 한다.

## 논문 수정안: III-A 및 Algorithm 1

논문 III-A에는 위 `E_req`, 차량별 `E_HFC`, `E_ESS^emg`, `E_unserved` 식을 삽입하고, 경제적 방전 진입 SOC 0.3과 비상 방전 하한 SOC 0.1을 별도 기호로 정의한다. ESS 전력 정격은 내부 인출 기준이므로 효율 0.95는 AC 출력으로 전환할 때 한 번만 곱한다. 수소 구매비는 보충 시점에, ESS 열화비는 충방전 시점에 반영하고, VOLL×실제 공급량만 회피편익으로 계산한다.

**Algorithm 1 교체 흐름:** 매 시간 산업 부하와 α 기준으로 Mode 2를 판정한다. Mode 2이면 주 트럭을 먼저, 이어서 실제 가용 보조 트럭을 순회하면서 각 차량의 정격·수소·이동 소비량에 맞춰 HFC 공급과 LOH를 갱신한다. HFC 이후 잔여량이 양수일 때만 ESS의 내부 인출 한도·남은 저장량·SOC 0.1 하한으로 보조 공급하고 SOC 및 열화비를 갱신한다. 남은 수요를 미공급으로 기록한다. Mode 1이면 기존 수소 보충 우선순위, ESS 경제 방전, PV 충전/P2G, 저가 SMP 계통 충전을 적용한다. 마지막으로 실제 구매비, Mode 1 매출, 실제 비상 공급의 VOLL 편익을 합산한다. `ceil(E_req/500)`은 **필요 대수**일 뿐 실제 투입 대수가 아니다.

논문에 바로 반영할 수 있는 영문 설명:

> During Mode 2, the main HFC is dispatched first, followed by available auxiliary HFC vehicles. Each vehicle is constrained by its rated hourly output and its individual hydrogen inventory after travel consumption. Only the remaining demand is eligible for ESS backup, subject to the battery withdrawal limit and the physical minimum SOC. The ESS discharge is propagated to subsequent Mode 1 operation. Any demand remaining after both resources is recorded as unserved energy. Operating net benefit excludes emergency ESS discharge revenue; avoided interruption benefit is computed from actual HFC and ESS emergency delivery using the 60-minute VOLL. Hydrogen purchase is expensed once at replenishment.

IV장 배치는 **A** grid condition과 Figure 5–9, **B** 자산 구성 Figure 10–11, **C** dual-mode·3×3·VOLL·기회비용 Figure 12·14·15 및 fleet 표, **D** nodal-level power flow Figure 13이 자연스럽다. Figure 14는 VOLL에 따른 평가의 변화, Figure 15는 실제 SOC 경로의 경제적 희생과 회복탄력성 편익을 설명한다. Figure 13에는 0.95 pu 위반 99시간이 남고 bus 18의 등가 주입이며 실제 정전 복구 가능성을 증명하지 않는다는 점을 명시해야 한다.
