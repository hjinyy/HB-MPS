# P1 다중 노드 IEEE 33-bus 조류해석

## 범위와 배치 규칙

기준은 `codex/p1-main-integration`의 **동일한 168시간 P1 운용 결과**다. ESS/HFC 공급량, SOC, LOH, 수소 구매 및 경제성 계산은 변경하지 않았다. IEEE 33-bus, Slack 1.0 pu, PV Bus 7, 기존 산업·주택·혼합 부하 정규화도 유지했다. 기존의 Bus 18 단일 주입을 주 트럭 **Bus 18**, 보조 HFC 트럭 **Bus 18 또는 Bus 33** 주입으로 분리했다.

Bus 18과 33의 원래 산업 정격 부하는 각각 0.09 MW, 0.06 MW이므로 두 노드의 시간별 산업 부하 비율은 동일한 정규화하에서 **60%:40%**다. 각 시간에 먼저 주 트럭 HFC와 ESS를 Bus 18에 배치한다. 그 시간의 실제 P1 총 공급량을 60%:40%로 나눈 목표량과 두 노드의 이미 배치된 공급량을 비교하여, 양의 출력이 있는 **보조 트럭 한 대의 HFC 전량**을 목표량 대비 부족분이 더 큰 노드에 순서대로 배치한다. 부족분이 같으면 직전 위치를 유지한다. 전체 트럭의 초기 위치는 Bus 18이다. 각 트럭은 한 시간에 한 노드에만 주입한다.

차량별 HFC 출력은 새로 최적화하거나 재계산하지 않았다. 기존 P1의 차량 순서·500 kWh/h 정격·개별 수소 재고·출동 수소 소비·보충 규칙을 별도 모듈에서 그대로 재생하고, 매 시간 **HFC 합계, 실제 투입 대수, 차량별 수소 합계, 주 트럭 수소 잔량, 구매·소비 수소량**이 기존 P1 출력과 일치함을 검사한다. 더 나아가 저장된 메인 결과 `p1_main_hourly.csv`의 **504개 시간 전체**에 대해 HFC·ESS 공급, 미공급, SOC·LOH, 실제·필요 대수, Mode 1 공급, 외부 수소 보충, 충전, 수익·운영비·회피편익이 일치해야만 조류해석을 진행한다. ESS 비상 공급은 항상 주 트럭의 Bus 18에 남는다. 화성시 석우동의 두 후보 서비스 지역 간 이동이 약 10분 내외라는 이번 실험 가정에 따라 **1시간 시간칸에서 추가 공급 지연은 차감하지 않는다.** 추가 이동거리·연료비도 P1 재고와 경제성을 바꾸지 않도록 부과하지 않는다. 이는 차량 경로·도로거리의 실증 검증이 아니라 접속 노드의 단순 배분 가정이다.

원자료 kWh는 기존 조류해석과 같이 원자료 산업 부하 최대값 16,328.297 kWh에 대한 비율에 IEEE 산업군 정격 1.01 MW를 곱해 MW로 변환한다. 시간별 Bus 18+33 **환산 주입 합계는 원래 P1 공급량의 동일한 환산값**과 정확히 일치한다. 전압은 정상 계통연계 상태의 지원 효과이며 실제 고장구간 복구를 뜻하지 않는다.

## 주요 수치

| α | Bus 18 HFC / ESS (원자료 MWh) | Bus 33 HFC (원자료 MWh) | 계통 최저전압: 단일→다중 (pu) | 0.95 pu 미만 시간: 단일→다중 | 최대 노드 전압개선: 단일→다중 (pu) | 누적 선로손실: 단일→다중 (MWh) |
| --- | --- | ---: | --- | --- | --- | --- |
| 1.3 | 14.328 / 4.560 | 12.075 | 0.926960→0.926997 | 99→99 | 0.011740→0.008487 | 14.059777→14.060820 |
| 1.5 | 1.570 / 0 | 0 | 0.924841→0.924841 | 99→99 | 동일 | 14.251193→14.251193 |
| 1.8 | 0 / 0 | 0 | 0.923565→0.923565 | 99→99 | 0→0 | 14.262578→14.262578 |

α=1.3에서 65개 HFC 차량·시간 가운데 32개 차량·시간의 보조 HFC 출력이 Bus 33에 배치됐다. 분산 후 전 계통 최저전압은 약 **0.000037 pu 높고**, 최대 개별 버스·시간 전압개선은 약 **0.003252 pu 낮으며**, 선로손실은 약 **0.001044 MWh 증가**했다. 0.95 pu 위반 시간 수는 바뀌지 않았다. 즉, 다중 노드 배치가 모든 전압 지표를 개선한다는 주장은 이 결과와 맞지 않는다. α=1.5는 주 트럭만 공급하고 α=1.8은 비상 공급이 없어 기존 단일 Bus 18 결과와 같다.

P1의 총 공급, 미공급, SOC/LOH 및 경제성 CSV는 변경되지 않았다. 예를 들어 α=1.3·5대의 P1 원자료 공급은 HFC 26.403 MWh+ESS 4.560 MWh, 미공급 29.993 MWh, 운영 순편익 -17.586백만원, 공급중단 회피편익 151.802백만원이다. 위 다중 노드 실험에서 달라진 값은 **조류계산의 접속 위치와 전압·손실**뿐이다.

## 산출물과 검증

- `fig_powerflow_validation_bold.png/.pdf`: 기존 **3행×2열**, 15×9 inch, 220 dpi, Times New Roman, 색상·선·마커·범례·축 설정을 유지한 전압 프로파일. 각 α의 왼쪽은 168시간 최저전압, 오른쪽은 baseline 최악 시간 t=107의 노드별 전압이다.
- `figure_13_powerflow_voltage_heatmap.png/.pdf`: 기존 **세로 3패널**, 13×10 inch, 220 dpi, 동일 색상·축·범례 체계의 α=1.3 전압 히트맵. 데이터에 따라 colorbar 글자 폭이 달라져도 원래 PNG의 **2693×2164픽셀 캔버스**를 유지했다.
- `pf_results.csv`, `powerflow_voltage_by_bus_hour.csv`: 각 시간의 전압·손실 및 33×168 전압. `pf_results.csv`에 Bus 18/33 환산 주입 열을 추가했다.
- `p1_multibus_hourly_injection.csv`, `p1_multibus_vehicle_dispatch.csv`: P1 원자료 에너지를 노드와 차량별로 추적한 검증표.
- `figure_16_p1_multitruck_deployment.png/.pdf`: α=1.3의 **주 트럭+보조 4대, 168시간 배치도**. 파랑/초록은 모델에서 유지되는 Bus 18/33 위치, 검은 점은 그 시간 실제 HFC 또는 ESS 공급을 뜻한다. 점이 없는 구간은 해당 위치에서 미투입 상태다. 약 10분 이동은 시간칸 안에 포함되어 별도 transit 구간을 그리지 않는다. 기존 Figure 14·15가 VOLL·ESS 기회비용으로 이미 사용 중이므로 번호를 바꾸지 않고 Figure 16으로 추가했다.

168시간×α 3개에 대해 baseline 및 HB-MPS의 AC 조류계산이 모두 수렴했다. 별도 α=1.3의 baseline/HB-MPS 33버스 히트맵 계산도 전부 수렴했다. 매 시간 차량별 HFC≤500 kWh, 비음수 수소 재고, 주 트럭 Bus 18, ESS Bus 18, 차량별 HFC 합계와 주입량 및 원래 P1 총 공급의 일치를 확인했다. 전체 기존·신규 자동 테스트 **10개 통과**. 기존 Figure 5–12·14–15, P1 메인 코드와 경제성 결과 파일은 변경하지 않았다.

이 결과는 **이동형 다중 노드 접속을 반영한 P1 조류해석**으로 기술해야 한다. 실제 차량 위치·도로 경로·접속시간의 실증 검증이나 고정 설비 대비 이동성의 우월성 비교로 해석하지 않는다.

논문 E절에는 다음처럼 설명할 수 있다: *The 168-hour P1 supply, fleet utilization, SOC, LOH, and operating outcomes are taken directly from the main simulation. The main vehicle is mapped to Bus 18, while each auxiliary HFC vehicle is assigned in whole to Bus 18 or 33 according to the remaining load-proportional nodal supply target. Only the injection location is changed in the IEEE 33-bus power-flow model; aggregate energy and financial outcomes are unchanged. The deployment timeline displays each vehicle's modeled hourly bus and marks the hours with actual HFC or ESS supply. Within-hour travel and physical outage restoration are outside the scope of this voltage validation.*

**Figure 16 caption:** *Hourly placement of the main ESS–HFC vehicle and four auxiliary HFC vehicles used for the α=1.3 IEEE 33-bus power-flow calculation. Blue and green indicate modeled Bus 18 and Bus 33 positions; black dots mark hours with actual P1 HFC or ESS delivery. The allocation changes only the injection bus, not the main simulation's energy, inventory, or economic path.*
