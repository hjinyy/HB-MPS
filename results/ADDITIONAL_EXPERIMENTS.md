# Additional case-study experiments

All figures here use `Data file/data_file.csv` in this repository (168 valid hourly
records, 1–7 August 2025). Rerun from the repository root with the packages in
`requirements.txt`:

```sh
python asset_ablation.py
python powerflow_heatmap.py
python strategy_sensitivity.py
```

## Figures 10–11: ESS/HFC asset ablation (α = 1.3)

`asset_ablation.py` compares ESS-only, HFC-only and Hybrid under two bases:

| Basis | ESS-only | HFC-only | Hybrid |
| --- | --- | --- | --- |
| Original component ratings | 1.5 MWh ESS | 1.5 MWh HFC equivalent | 1.5 + 1.5 MWh |
| Equal total stored energy | 3 MWh ESS | 3 MWh HFC equivalent | 1.5 + 1.5 MWh |

The baseline demand is the positive part of hourly industrial load minus
`1.3 × mean(industrial load)`. A single vehicle is available; no auxiliary
trucks are supplied instantly. HFC output is limited to 500 kWh/h and its
remaining stored hydrogen, while ESS output is limited to 700 kWh/h and energy
above 10% SOC with 95% discharge efficiency. The published main-model
priorities are retained: serve Mode 2, refuel HFC below 60% off-event,
discharge ESS in high-LCOE hours, then charge from solar surplus or cheap grid
electricity. HFC is dispatched before ESS within Mode 2. An hourly energy
balance determines residual unserved load. Hydrogen consumed is valued at the
hourly external hydrogen price; replenishment is not charged again. The
operating-value figure shows operating net plus avoided outage value using
the repository's 60-minute VOLL formula. It excludes investment, fixed O&M,
end-of-horizon inventory value and vehicle size or weight constraints.

| Basis | Configuration | Served (MWh) | Unserved (MWh) | Total operating value (million KRW) |
| --- | --- | ---: | ---: | ---: |
| Original | ESS-only | 4.560 | 56.396 | 21.619 |
| Original | HFC-only | 5.523 | 55.433 | 23.610 |
| Original | Hybrid | 10.083 | 50.873 | 45.229 |
| Equal 3 MWh | ESS-only | 7.040 | 53.916 | 33.259 |
| Equal 3 MWh | HFC-only | 11.046 | 49.910 | 47.221 |
| Equal 3 MWh | Hybrid | 10.083 | 50.873 | 45.229 |

The hybrid wins on the original component basis because it carries twice as
much stored energy as either single-asset case. Under the equal-energy basis,
HFC-only has the highest energy served and total operating value in this
particular week. These figures therefore demonstrate complementarity under
the original design, but do **not** establish hybrid superiority for an equal
size, weight, or investment budget. Full capital-cost and multiweek analysis
would be needed for that claim.

Data: `asset_ablation_hourly.csv` (1,008 rows) and
`asset_ablation_summary.csv` (6 rows).

## Figure 12: dual-mode policy sensitivity (α = 1.3)

`strategy_sensitivity.py` holds the hybrid's 1.5 MWh ESS and 1.5 MWh HFC
constant, then crosses Phase 1 ESS SOC thresholds of 0.2, 0.3 and 0.5 with
high-LCOE dispatch quantiles of 0.4, 0.6 and 0.8. All other ablation rules
are fixed, including 60% HFC off-event refueling. The 3×3 panel reports
unserved energy and operating net; all nine outcomes are saved in
`dual_mode_policy_sensitivity.csv`.

At the 0.3 SOC threshold, using the 0.4 price quantile yields a less-negative
operating net (−3.56 million KRW) but more unserved energy (54.01 MWh) than
the original 0.6 quantile policy (−4.20 million KRW; 50.87 MWh). The 0.8
quantile does not reduce unserved energy further. This is an operational
trade-off for the supplied week; it does not measure mobility or optimize the
policy over other weeks.

## Figure 13: IEEE 33-bus voltage heatmap (α = 1.3)

`powerflow_heatmap.py` reruns both baseline and HB-MPS power flow at all 168
hours, retaining voltage magnitudes at all 33 buses (5,544 bus-hour pairs).
Baseline and HB-MPS panels share the same color scale. The lower panel shows
their difference, and the dotted horizontal line marks HB-MPS bus 18. The
lowest network voltage changes from 0.9236 to 0.9270 p.u.; maximum local
bus-hour improvement is 0.0117 p.u. The full data are in
`powerflow_voltage_by_bus_hour.csv`.

The heatmap follows the existing `powerflow_validation.py` equivalent
injection assumption. It is independent of the single-vehicle energy-limited
ablation above and must not be presented as its direct network outcome.

## Mobility comparison limitation

The input file contains one aggregate industrial profile and no service-node
locations, truck travel times, or node-specific outage demand. A stationary
versus mobile service-success comparison cannot be estimated from these data
without adding explicit spatial and temporal assumptions. No mobility benefit
is claimed by Figures 10–12.
