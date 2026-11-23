# Manuscript figure file map

Source: `v2-ACCESS-manuscript.pdf` supplied on 2026-11-23. Filenames use the manuscript's Figure number and a lowercase, underscore-separated form of the caption title. Each listed file exists in PNG and PDF form in this directory. Subfigure descriptions and scenario qualifiers are retained in the manuscript captions, not repeated in filenames.

| Manuscript label | Caption title | File stem |
|---|---|---|
| Fig. 1 | Overall architecture and operational concept of the proposed HB-MPS in a self-sufficient microgrid | No separate repository file |
| Fig. 2 | Flowchart of the dual-mode operation strategy of the HB-MPS | No separate repository file |
| Fig. 3 | Comparison of load profiles | `fig3_comparison_of_load_profiles` |
| Fig. 4 | Energy supply vs. demand mismatch analysis | `fig4_energy_supply_vs_demand_mismatch_analysis` |
| Fig. 5 | Mode 2 activation and auxiliary truck deployment | `fig5_mode_2_activation_and_auxiliary_truck_deployment` |
| Fig. 6 | ESS SOC and hydrogen LOH profiles | `fig6_ess_soc_and_hydrogen_loh_profiles` |
| Fig. 7 | Distribution of HB-MPS operating modes | `fig7_distribution_of_hb_mps_operating_modes` |
| Fig. 8 | Cumulative financial flow of HB-MPS | `fig8_cumulative_financial_flow_of_hb_mps` |
| Fig. 9 | Comparison of emergency energy delivery and residual unserved demand | `fig9_comparison_of_emergency_energy_delivery_and_residual_unserved_demand` |
| Fig. 10 | Comparison of operating net benefit, avoided interruption benefit, and net societal benefit | `fig10_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit` |
| Fig. 11 | Sensitivity of residual unserved energy and operating net benefit | `fig11_sensitivity_of_residual_unserved_energy_and_operating_net_benefit` |
| Fig. 12 | VOLL sensitivity of net societal benefit | `fig12_voll_sensitivity_of_net_societal_benefit` |
| Fig. 13 | Decomposition of economic opportunity costs and avoided interruption benefits | `fig13_decomposition_of_economic_opportunity_costs_and_avoided_interruption_benefits` |
| Fig. 14 | IEEE 33-bus distribution system configuration for HB-MPS power-flow validation | No separate repository file |
| Fig. 15 | IEEE 33-bus power-flow validation | `fig15_ieee_33_bus_power_flow_validation` |
| Fig. 16 | Spatiotemporal voltage heatmaps of the IEEE 33-bus system | `fig16_spatiotemporal_voltage_heatmaps_of_the_ieee_33_bus_system` |
| Fig. 17 | Hourly deployment of the main ESS-HFC truck and four auxiliary HFC trucks | `fig17_hourly_deployment_of_the_main_ess_hfc_truck_and_four_auxiliary_hfc_trucks` |

The repository's older `P1_*` reports describe the historical figure numbering and filenames used at the time of those runs. The supplementary or legacy plots `figure_economic_value_all_cases`, `fig_powerflow`, `figure_powerflow_voltage_profile`, and the three `emergency_figure_*` pairs have no matching numbered caption in this manuscript and were removed from the current `results` directory. Their historical versions remain available in Git history and the legacy archive. The main simulation and emergency experiment no longer generate these unused plots during their normal runs.

The manuscript and saved results agree on the principal numerical outcomes (including Table II, Table III, and the power-flow minimum voltage), but manuscript Section IV-B states a non-standby share of approximately 56.5–61.9%. The saved `p1_main_hourly.csv` gives 63.69%, 58.93%, and 56.55% for α = 1.3, 1.5, and 1.8 respectively. Thus the range should be approximately 56.5–63.7% if those saved results are the intended final source. The manuscript PDF also contains editorial comments and has no corresponding manuscript source file in this repository; exact manuscript-version identity cannot be established from this repository alone.
