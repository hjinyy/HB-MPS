# Fig. 9_1: ESS–HFC capacity allocation trade-off

This proposed figure replaces the earlier grid-margin comparison. Following the removal of the former Fig. 8, it is numbered Fig. 9_1 and the IEEE 33-bus validation is Fig. 14_1. The reproducible source is `../asset_capacity_tradeoff.py`; the full 11-case results are in `fig9_1_economic_resilience_trade_off_by_ess_hfc_capacity_allocation.csv`.

## Controlled experiment

- Total onboard energy capacity is 3 MWh for every case. ESS capacity increases from 0 to 3 MWh in 0.3 MWh steps; HFC capacity decreases by the same amount.
- Grid margin factor α is fixed at 1.3. All cases use the same 168 hourly load, PV, electricity-price, and hydrogen-price inputs and the same single-truck P1 algorithm as Figs. 8–9.
- Hourly power ratings are **held fixed**: HFC output up to 500 kWh/h, ESS withdrawal up to 700 kWh/h, and ESS charging up to 300 kWh/h. Energy inventory, SOC limits, H₂ use/refill, charging efficiency, and price rules follow the same P1 code. Thus only the onboard energy allocation changes; power-to-energy ratios vary across configurations.
- Panel (a) plots booked operating net benefit and delivered emergency energy against ESS share. Panel (b) plots the same two objectives against one another. The dashed line joins simulated cases in allocation order; it is not an interpolated performance model.

## Results

| ESS share | ESS / HFC (MWh) | Emergency supply (MWh) | Operating net benefit (M KRW) | Mode 1 direct margin (M KRW) | Mode 2 resource cost (M KRW) |
|---:|---:|---:|---:|---:|---:|
| 0% | 0.0 / 3.0 | 11.046 | -6.746 | 0.000 | 6.933 |
| 10% | 0.3 / 2.7 | 10.852 | -6.147 | 0.315 | 6.287 |
| 20% | 0.6 / 2.4 | 10.656 | -5.617 | 0.499 | 5.641 |
| 30% | 0.9 / 2.1 | 10.465 | -5.112 | 0.631 | 4.996 |
| 40% | 1.2 / 1.8 | 10.269 | -4.641 | 0.709 | 4.351 |
| **50%** | **1.5 / 1.5** | **10.083** | **-4.094** | **0.836** | **3.707** |
| 60% | 1.8 / 1.2 | 9.883 | -3.591 | 0.933 | 3.061 |
| 70% | 2.1 / 0.9 | 9.438 | -3.035 | 1.067 | 2.401 |
| 80% | 2.4 / 0.6 | 8.801 | -2.502 | 1.033 | 1.730 |
| 90% | 2.7 / 0.3 | 7.863 | -1.858 | 1.112 | 1.045 |
| 100% | 3.0 / 0.0 | 7.040 | -1.257 | 1.156 | 0.389 |

All 11 simulated cases are non-dominated when **booked operating net benefit** and **delivered emergency energy** are both maximized. This is an observed discrete Pareto set, not proof of a continuous frontier or optimal sizing. The 50:50 Hybrid supplies 8.7% less emergency energy than HFC-only, while its operating loss is 39.3% smaller. Relative to ESS-only, it supplies 43.2% more emergency energy but incurs 2.837 M KRW more operating loss. The 50:50 allocation is therefore one feasible compromise; these results do not establish it as the optimum.

## Financial interpretation and limits

The plotted operating net benefit uses the original Fig. 9 bookkeeping: Mode 1 revenue minus external hydrogen purchases, grid electricity purchases, and ESS wear. It excludes capital cost and terminal inventory value. The CSV also records Mode 1 energy and revenue; **Mode 1 direct margin** subtracts Mode 1 ESS-discharge wear and travel hydrogen valued at the hour of use. **Mode 1 net after charging** additionally assigns all ESS grid-purchase and charging-wear costs to Mode 1, a conservative attribution because charging may also support Mode 2. At 50% ESS it is -0.495 M KRW; at 100% ESS it is -0.868 M KRW. Therefore the direct margin increase alone does not establish positive Mode 1 net economics.

**Mode 2 resource cost** values hydrogen consumed during Mode 2 at the hour-of-use hydrogen price and adds Mode 2 ESS-discharge wear. It is an analytical usage cost, while the plotted operating net books hydrogen when externally purchased. The two Mode-specific measures do not sum to plotted operating net because replenishment timing, charging attribution, and inventory changes differ. The CSV separately provides purchase costs, charging wear, and terminal inventory change so these differences can be audited.

The endpoints and 50:50 case reproduce the equal-3-MWh Fig. 8–9 results. Their power ratings remain fixed across the sweep, so the figure isolates **energy allocation under the existing dispatch assumptions**, not a jointly optimized design of energy and power ratings.
