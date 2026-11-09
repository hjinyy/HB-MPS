# HB-MPS final P1 results

**Canonical branch:** `codex/p1-final`. The sole repository data input is [`Data file/data_file.csv`](Data%20file/data_file.csv). The main strategy is P1: HFC first, then ESS backup when needed, with one main truck and at most four auxiliary HFC trucks. The 168-hour scenarios use α = 1.3, 1.5, and 1.8. Power flow uses the standard IEEE 33-bus network and maps the already determined P1 supply to buses 18 and 33; it does not recompute dispatch or economics.

## Figure 8 and Table II

[`results/figure_8_financial_flow_all_cases.png`](results/figure_8_financial_flow_all_cases.png) is the **P1 cumulative operating cash-flow figure**. Its blue line is labeled `Operating Net Benefit` and ends at `Revenue − (H2 purchase + grid purchase + ESS wear)`, or Πop. For α = 1.3 this is **−17.586 million KRW**. Avoided interruption benefit is a separate term, so the blue curve is not expected to end at the societal benefit.

[`results/table_ii_p1.csv`](results/table_ii_p1.csv) is the P1 source for replacing the manuscript's older Table II/IV-B values. The paper itself is not stored in this repository.

| α | Operating net Πop (M KRW) | Avoided interruption Bavoid (M KRW) | Net societal benefit Πop + Bavoid (M KRW) | Residual unserved (MWh) |
|---:|---:|---:|---:|---:|
| 1.3 | −17.586 | 151.802 | 134.216 | 29.993 |
| 1.5 | 0.119 | 7.697 | 7.815 | 0 |
| 1.8 | 0.578 | 0 | 0.578 | 0 |

The earlier **298.850 M KRW** at α = 1.3 is approximately the baseline interruption risk cost (298.852 M KRW in the current input), not P1's avoided interruption benefit. P1 supplies 26.403 MWh via HFC and 4.560 MWh via ESS, leaving 29.993 MWh unserved. Consequently, the older 260.860 M KRW societal figure must be replaced by 134.216 M KRW wherever the manuscript reports this P1 case. Do not label the operating net curve in Figure 8 as societal benefit.

The manuscript should cite the current Figure 8 file and update Table II, Section IV-B, and the conclusion to these same P1 figures. [`HB-MPS main simulation.py`](HB-MPS%20main%20simulation.py) generates the P1 Table II CSV from the same in-memory results saved as `p1_main_summary.csv` and `p1_main_hourly.csv`.

## Reproduce the final outputs

Run from the repository root with Python 3.11 or newer and the packages in `requirements.txt` installed. The final command also requires `pytest`:

```sh
python "load profile.py"
python "Energy Supply vs. Demand Mismatch Analysis.py"
python "HB-MPS main simulation.py"
python asset_ablation.py
python strategy_sensitivity.py
python p1_additional_analysis.py
python powerflow_validation.py
python powerflow_heatmap.py
python -m pytest -q tests
```

| Output in `results/` | Generator | Saved data |
|---|---|---|
| `figure_load_profiles`, `figure_5_energy_supply_demand_mismatch` | input plotting scripts | input CSV |
| `figure_6`, `figure_7`, `figure_8`, `figure_9` | main simulation | `p1_main_hourly.csv`, `p1_main_summary.csv`, `table_ii_p1.csv` |
| `figure_10`, `figure_11` | `asset_ablation.py` | `asset_ablation_summary.csv`, `asset_ablation_hourly.csv` |
| `figure_12` | `strategy_sensitivity.py` | `dual_mode_policy_sensitivity.csv` |
| `figure_14`, `figure_15` | `p1_additional_analysis.py` | `p1_voll_sensitivity.csv`, `p1_voll_break_even.csv`, `p1_opportunity_components.csv`, `p1_fleet_summary.csv` |
| `fig_powerflow_validation_bold`, `figure_16` | `powerflow_validation.py` | `pf_results.csv`, `p1_multibus_hourly_injection.csv`, `p1_multibus_vehicle_dispatch.csv` |
| `figure_13` | `powerflow_heatmap.py` | `powerflow_voltage_by_bus_hour.csv` |

Every figure above is retained as PNG and PDF. Shared physical P1 dispatch is implemented in `emergency_dispatch.py`, `emergency_dispatch_model.py`, and `main_p1_adapter.py`. Older exploratory outputs remain available in Git history and earlier branches.
