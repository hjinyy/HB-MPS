# Fig. 10_1: asset configuration across grid margins

This proposed insertion follows Fig. 10; the numbering and files of the existing figures are unchanged. The three panels show (a) emergency energy supply, (b) operating net benefit, and (c) net societal benefit. The data and reproducible plotting code are in `fig10_1_asset_configuration_performance_across_grid_margin_factors.csv` and `../asset_grid_margin_comparison.py`.

## Experiment

- Same 168 hourly residential load, industrial load, PV, and price inputs as Figs. 9–10.
- P1 dispatch with one truck, the same equipment output limits, SOC limits, hydrogen use and refill logic, and financial accounting as Figs. 9–10.
- Equal total stored energy: ESS-only 3 + 0 MWh; HFC-only 0 + 3 MWh; Hybrid 1.5 + 1.5 MWh.
- Grid margin factor α = 1.3, 1.5, 1.8. Demand above α times the mean industrial load defines the emergency request.
- Emergency energy supply is delivered ESS plus HFC energy. Operating net benefit is revenue less hydrogen purchase, grid purchase, and ESS wear. Net societal benefit is operating net benefit plus avoided interruption benefit from actual emergency delivery. The figure follows Fig. 10 in excluding capital cost and the terminal inventory value adjustment.

## Results

| α | Configuration | Emergency supply (MWh) | Operating net benefit (M KRW) | Net societal benefit (M KRW) |
|---:|---|---:|---:|---:|
| 1.3 | ESS-only | 7.040 | -1.257 | 33.256 |
| 1.3 | HFC-only | 11.046 | -6.746 | 47.408 |
| 1.3 | Hybrid | 10.083 | -4.094 | 45.338 |
| 1.5 | ESS-only | 1.570 | 0.151 | 7.847 |
| 1.5 | HFC-only | 1.570 | 0.000 | 7.697 |
| 1.5 | Hybrid | 1.570 | 0.119 | 7.815 |
| 1.8 | ESS-only | 0.000 | 0.510 | 0.510 |
| 1.8 | HFC-only | 0.000 | 0.000 | 0.000 |
| 1.8 | Hybrid | 0.000 | 0.578 | 0.578 |

At α=1.3, HFC-only supplies 0.963 MWh more emergency energy and yields 2.070 M KRW more net societal benefit than Hybrid. At α=1.5, all three configurations supply the same emergency energy; ESS-only has the highest net societal benefit, exceeding Hybrid by 0.032 M KRW. At α=1.8, there is no emergency request in the input week, and Hybrid earns the highest operating net benefit, exceeding ESS-only by 0.068 M KRW. The experiment supports **condition-dependent performance**, not universal Hybrid superiority or a precisely located crossover. Only three discrete α values were simulated.

The 3 MWh equality refers to onboard stored energy; it does not equalize ESS and HFC power ratings, replenishment opportunities, conversion efficiency, or capital cost. The saved metrics follow the original Fig. 10 accounting and should not be interpreted as full lifecycle cost-benefit results.
