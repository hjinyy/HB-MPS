# HB-MPS emergency dispatch strategy validation

## Scope and reproducibility

This is an **operational 168-hour experiment**, separate from the IEEE 33-bus power-flow study. It uses only `Data file/data_file.csv` (1–7 August 2025, 168 valid hourly rows). The existing main simulation and Figures 5–13 were not edited. Run from the repository root:

```sh
uv run --with numpy --with matplotlib emergency_dispatch_experiment.py
uv run --with numpy --with matplotlib --with pytest python -m pytest -q tests/test_emergency_dispatch.py
```

The experiment writes `emergency_dispatch_hourly.csv` (36 × 168 = 6,048 rows), `emergency_dispatch_summary.csv` (36 rows), and Figures A–C as PNG and PDF. All new files use an `emergency_` prefix except this report. Figure A and B show a **prespecified P2 reserve of 0.3**; Figure C and the CSV include every reserve from 0.2 to 0.5. No result was used to choose the plotted reserve.

## 1. Exact strategy difference

The three strategies have **identical Mode 1** and identical HFC-first Mode 2 dispatch. They differ only in how they cover **remaining** Mode 2 demand after the available HFC trucks have been dispatched:

| Strategy | Emergency ESS rule |
| --- | --- |
| P0 | ESS is never used in Mode 2. |
| P1 | Discharge ESS up to the 700 kWh/h internal withdrawal limit, stopping at physical minimum SOC 0.1. |
| P2 | Same HFC-first order, but stop emergency ESS discharge at `max(0.1, reserve SOC)`. Reserves 0.2, 0.3, 0.4, 0.5 were tested. |

The **Mode 1 economic-discharge starting gate** remains SOC ≥ 0.3. It controls whether economic discharge starts; it is **not** the P2 emergency reserve. Mode 1 may later draw SOC below a P2 reserve, as the original economic rule allows. Thus P2 protects inventory only during Mode 2; it does not guarantee a terminal SOC floor of 0.3–0.5.

## 2. Code and physical model

- `emergency_dispatch_model.py`: scenario, per-hour output, inventory, and result types.
- `emergency_dispatch.py`: finite-truck hourly state transitions and the three rules.
- `emergency_dispatch_experiment.py`: 36-scenario runner, invariants, hourly CSV, and summary CSV.
- `emergency_dispatch_plot.py`: paper-style Times New Roman Figures A–C.
- `tests/test_emergency_dispatch.py`: targeted finite-fuel, reserve, and purchase-accounting scenarios.

At every hour, the industrial excess demand is `max(load_B − α × mean(load_B), 0)` for α = 1.3 or 1.5. The main vehicle has a 1.5 MWh ESS and 1.5 MWh HFC-equivalent hydrogen inventory. Each auxiliary vehicle adds **one HFC unit and one separate 1.5 MWh-equivalent tank**, following the original main code's 500 kWh/h-per-truck interpretation. Total available vehicles (including the main vehicle) are 1, 2, or 5. This is a modeling interpretation of the original auxiliary-truck abstraction, not a verified vehicle bill of materials.

Each HFC unit is limited to 500 kWh in an hour and to its own stored hydrogen after 0.136 kg travel fuel. The main ESS is limited to 700 kWh withdrawn per hour (at 95% delivery efficiency), SOC 0.1–0.9, and 300 kWh/h charging input. ESS starts at SOC 0.4; every HFC tank starts at LOH 0.8. HFC inventories refill externally to LOH 0.9 only in an off-event hour after falling below 0.6. Auxiliary refills can occur independently; the main tank retains the original refuel-before-Mode-1 priority. Main-tank P2G from PV surplus uses 55 kWh/kg. External purchases are assumed to be available for off-event refilling without delivery delay; their costs are charged at the hourly CSV price. There is no instant emergency fuel purchase. This refill assumption remains an important optimistic limit.

The shared Mode 1 rule uses the original 0.6 whole-week LCOE quantile for economic ESS discharge, the 0.25 SMP quantile for grid charging, and the original PV-surplus priority. These offline quantiles reproduce the original rule; a field implementation would calibrate them from historical information rather than know future prices.

## 3. Benefit accounting

The measured quantities follow the main paper definitions:

\[
\Pi_{op}=\sum_t(\text{ESS Mode 1 revenue}-\text{external H2 purchases}-\text{grid purchases}-\text{ESS wear}),
\]

\[
B_{avoid}=\sum_t(\text{HFC supply}+\text{ESS emergency supply})\times\mathrm{VOLL}_{60},
\quad V_{societal}=\Pi_{op}+B_{avoid}.
\]

The existing 60-minute VOLL function gives **4,902.75 KRW/kWh**. ESS wear is 50 KRW per kWh withdrawn or charged, matching the original code's throughput convention. Grid recharging is expensed at hourly SMP; lost future Mode 1 revenue is measured through the forward state path. Hydrogen is expensed **once when bought for refill**, with no second consumption expense. PV surplus is assumed otherwise curtailed, so its opportunity cost is zero in this accounting; a sellable-PV counterfactual is not available in the data.

The original main code has a mixed H2 convention: main-tank external replenishment is expensed when bought, while auxiliary hydrogen and shortage fuel can be expensed at dispatch. This experiment uses one procurement basis for every tank. Accordingly, its `Π_op` is comparable across P0/P1/P2 but is **not numerically identical to the original paper run**. No legacy result was recalculated or overwritten.

The primary `V_societal` follows the existing definition and **does not add a terminal-inventory salvage value**. As a separate sensitivity, the summary CSV reports the end-minus-start ESS and H2 inventory valued at the **same final-hour SMP and H2 price**, and `inventory_adjusted_societal_krw = V_societal + inventory change`. This isolates quantity differences without mixing in price drift; it is not a new primary paper KPI.

## 4. Summary table and figure interpretation

Units below are MWh for energy and **million KRW** for benefits. `Reserve` is an emergency-only SOC floor. The table shows every α = 1.3 case; the 18 α = 1.5 rows are in the full CSV.

| α | Strategy | Available trucks | Reserve SOC | ESS emergency supply | HFC supply | Residual unserved | Operating net Π_op | Avoided interruption B_avoid | Net societal V_societal |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.3 | P0 | 1 | — | 0.000 | 5.516 | 55.440 | -3.161 | 27.044 | 23.883 |
| 1.3 | P1 | 1 | — | 4.560 | 5.523 | 50.873 | -4.094 | 49.432 | 45.338 |
| 1.3 | P2 | 1 | 0.2 | 3.990 | 5.523 | 51.443 | -4.002 | 46.638 | 42.636 |
| 1.3 | P2 | 1 | 0.3 | 3.420 | 5.518 | 52.018 | -3.863 | 43.821 | 39.958 |
| 1.3 | P2 | 1 | 0.4 | 2.850 | 5.518 | 52.588 | -3.747 | 41.026 | 37.279 |
| 1.3 | P2 | 1 | 0.5 | 2.280 | 5.518 | 53.158 | -3.632 | 38.231 | 34.600 |
| 1.3 | P0 | 2 | — | 0.000 | 10.734 | 50.222 | -6.534 | 52.628 | 46.094 |
| 1.3 | P1 | 2 | — | 4.560 | 10.741 | 45.655 | -7.467 | 75.016 | 67.549 |
| 1.3 | P2 | 2 | 0.2 | 3.990 | 10.741 | 46.225 | -7.375 | 72.222 | 64.847 |
| 1.3 | P2 | 2 | 0.3 | 3.420 | 10.737 | 46.800 | -7.236 | 69.405 | 62.169 |
| 1.3 | P2 | 2 | 0.4 | 2.850 | 10.737 | 47.370 | -7.120 | 66.610 | 59.490 |
| 1.3 | P2 | 2 | 0.5 | 2.280 | 10.737 | 47.940 | -7.005 | 63.815 | 56.811 |
| 1.3 | P0 | 5 | — | 0.000 | 26.396 | 34.560 | -16.653 | 129.413 | 112.760 |
| 1.3 | P1 | 5 | — | 4.560 | 26.403 | 29.993 | -17.586 | 151.802 | 134.216 |
| 1.3 | P2 | 5 | 0.2 | 3.990 | 26.403 | 30.563 | -17.494 | 149.007 | 131.513 |
| 1.3 | P2 | 5 | 0.3 | 3.420 | 26.398 | 31.138 | -17.355 | 146.190 | 128.835 |
| 1.3 | P2 | 5 | 0.4 | 2.850 | 26.398 | 31.708 | -17.239 | 143.396 | 126.156 |
| 1.3 | P2 | 5 | 0.5 | 2.280 | 26.398 | 32.278 | -17.124 | 140.601 | 123.477 |

At α = 1.3 there are **39 Mode 2 hours and 60.956 MWh of excess demand**. Figure A shows that even five finite trucks leave 34.560 MWh unserved under P0. P1 reduces this by 4.567 MWh to 29.993 MWh. Figure B shows P1's operating net is 0.933 million KRW worse than P0, but its avoided-interruption benefit is 22.388 million KRW higher; net societal benefit increases by **21.455 million KRW** for each truck count. Figure C shows that increasing the P2 reserve monotonically increases residual unserved energy and lowers net societal benefit in this week.

At α = 1.5 there are **8 Mode 2 hours and 1.570 MWh of excess demand**. Every tested truck limit and strategy gives HFC supply 1.570 MWh, ESS emergency supply 0, unserved 0, `Π_op` 0.119 million KRW, `B_avoid` 7.697 million KRW, and `V_societal` 7.815 million KRW. The three strategies are observationally identical because HFC alone covers every event.

## 5. ESS emergency use versus later economic operation

For α = 1.3, switching from P0 to P1 yields 4.560 MWh of emergency ESS supply but reduces subsequent Mode 1 ESS delivery from **8.654 to 5.709 MWh** (−2.945 MWh). Mode 1 revenue falls by 0.600 million KRW. Grid charging rises from **6.106 to 7.895 MWh** (+1.789 MWh), raising grid purchase expense by 0.159 million KRW. Additional ESS throughput raises wear expense by 0.174 million KRW. The combined operating-net decrease is 0.933 million KRW. PV-to-ESS charging remains 3.010 MWh and PV-to-H2 conversion is unchanged for P0 versus P1 in this dataset; no PV opportunity shift is observed under the assumed zero-curtailment-value rule.

The primary comparison omits future post-horizon service. P0 and P1 both end at SOC 0.1 under α = 1.3; P2 at reserve 0.2 ends at SOC 0.2, while P2 reserves 0.3–0.5 end at SOC 0.1 after subsequent Mode 1 discharge. The end-minus-start inventory valuation differs by only about **0.003 million KRW between P1 and P0**, so adding it separately does not change the ranking. This week does not establish how a reserve would perform during another outage after hour 168.

## 6. Recommendation and paper text changes

**Recommend P1 as the operational candidate for the tested conditions**: HFC first, then actual remaining demand served by ESS down to physical minimum SOC. It is a rule-based fallback; it leaves Mode 1 unchanged and activates ESS only when HFC and available trucks are insufficient. At α = 1.3 it has the lowest unserved energy and highest `V_societal` for every tested truck count. At α = 1.5 it behaves exactly like P0, because no ESS backup is needed. P2 at SOC 0.2 may be a conservative contingency if future unmodeled outages make stored ESS valuable, but this 168-hour result supplies **no measured net-benefit case** for adopting P2; higher reserves reduce the measured societal benefit. P0 remains reasonable when HFC already covers all events, as in α = 1.5, but is not the best single rule across both tested α values.

For Section III-A, state explicitly that HFC priority is maintained, auxiliary truck count and stored hydrogen are finite, and any residual energy remains unserved unless optional ESS backup is enabled. Distinguish the economic-discharge start gate at SOC 0.3 from the Mode 2 ESS reserve. Define `Π_op`, `B_avoid`, and terminal inventory accounting as above; disclose the 60-minute VOLL choice. For Algorithm 1, replace “required trucks = ceil(excess/500), hence all excess supplied” with a loop over **available** HFC vehicles, each limited by remaining hydrogen after travel fuel and its 500 kWh/h rating. Compute `residual = max(excess − HFC supply, 0)`. For P1 or P2, compute ESS withdrawal `min(700, SOC headroom, residual/0.95)`, subtract that withdrawal from SOC, add `0.95 × withdrawal` to supplied energy, and update residual. Charge H2 **only at external refill**, ESS wear on emergency withdrawal, and grid purchase on recharge. Report P0 as the finite-truck comparator, with the original unlimited-availability run retained only as a historical reproduction.

## 7. Validation and relation to earlier figures

Every one of the 6,048 steps passed checks for: demand = HFC + ESS emergency + unserved; nonnegative residual; ESS SOC 0.1–0.9; each tank 0–1.5 MWh equivalent; HFC ≤ 500 kWh/h per dispatched truck; number dispatched ≤ available trucks; ESS output ≤ 700 × 0.95 kWh/h; H2 mass balance including travel, P2G, and external refill; ESS energy balance including emergency discharge; and nonnegative purchase/wear expenses. Targeted synthetic tests also force HFC depletion, reserve blocking, and purchase-at-refill without double charging. The same 168 input rows, price quantiles, initial SOC/LOH, and vehicle limits are used for all three rules within each α and truck-count condition.

The unchanged main code's α = 1.3 reproduction reports **0 residual unserved energy** and 298.852 million KRW avoided interruption, because it assumes enough auxiliary trucks and fuel to cover every event. Its largest dispatch uses five trucks, but availability is not capped at 1, 2, or 5 and auxiliary fuel is not tracked as onboard inventory. The finite-truck P0 result is therefore a new physical comparator, not an exact reproduction of that historical result.

Earlier Figure 10's one-vehicle Hybrid ablation supplies about **5.523 MWh HFC + 4.560 MWh ESS** at α = 1.3, close to the new one-truck P1 energy result. Earlier Figure 11 reports 45.229 million KRW total operating-plus-avoided value for that Hybrid case versus 45.338 million KRW here; the difference follows the revised per-tank procurement, travel, and Mode 1 state path accounting. Neither headline total includes terminal-inventory valuation. Earlier Figure 12 changes the **Mode 1 economic SOC and LCOE thresholds**; new Figure C changes only the **Mode 2 emergency reserve**. Their horizontal axes represent different decisions and should not be equated. Figures 5–9 and the original 10–13 remain unchanged.

## 8. Limits and further checks

The input has one aggregate industrial load, not node-specific outages, truck location or travel time, so this experiment cannot prove geographic response feasibility or network-voltage benefit. Auxiliary tanks are modeled as identical full-capacity HFC units because that is how the original code scales hourly output; actual platform packaging and hydrogen delivery rates need engineering validation. The off-event refill rule assumes immediate availability, and all cases use only one week and two α thresholds. Capital cost, fixed maintenance, exportable PV value, future outage probability, and post-horizon benefits are excluded. VOLL dominates the societal ranking and should be stress-tested against duration and customer class. A firm recommendation on reserve SOC needs multiweek/weather/outage scenarios, slower refilling, and a terminal-inventory or future-service value model. No IEEE 33-bus power flow was rerun for these energy-limited trajectories.
