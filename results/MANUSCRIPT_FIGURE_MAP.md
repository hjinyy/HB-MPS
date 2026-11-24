# Manuscript figure file map

Caption titles originate from `v2-ACCESS-manuscript.pdf` supplied on 2026-11-23. The labels below reflect the removal of its former Fig. 8; every following figure moves forward by one number. The manuscript PDF itself has not been revised. Each listed file stem has PNG and PDF outputs unless marked otherwise.

| Manuscript label | Caption title | File stem |
|---|---|---|
| Fig. 1 | Overall architecture and operational concept of the proposed HB-MPS in a self-sufficient microgrid | No separate repository file |
| Fig. 2 | Flowchart of the dual-mode operation strategy of the HB-MPS | No separate repository file |
| Fig. 3 | Comparison of load profiles | `fig3_comparison_of_load_profiles` |
| Fig. 4 | Energy supply vs. demand mismatch analysis | `fig4_energy_supply_vs_demand_mismatch_analysis` |
| Fig. 5 | Mode 2 activation and auxiliary truck deployment | `fig5_mode_2_activation_and_auxiliary_truck_deployment` |
| Fig. 6 | ESS SOC and hydrogen LOH profiles | `fig6_ess_soc_and_hydrogen_loh_profiles` |
| Fig. 7 | Distribution of HB-MPS operating modes | `fig7_distribution_of_hb_mps_operating_modes` |
| Fig. 8 | Comparison of emergency energy delivery and residual unserved demand | `fig8_comparison_of_emergency_energy_delivery_and_residual_unserved_demand` |
| Fig. 9 | Comparison of operating net benefit, avoided interruption benefit, and net societal benefit | `fig9_comparison_of_operating_net_benefit_avoided_interruption_benefit_and_net_societal_benefit` |
| Fig. 9_1 (proposed insertion) | Trade-off between economic performance and emergency power supply under different ESS–HFC capacity allocations with an identical total energy storage capacity | `fig9_1_economic_resilience_trade_off_by_ess_hfc_capacity_allocation` |
| Fig. 10 | Sensitivity of residual unserved energy and operating net benefit | `fig10_sensitivity_of_residual_unserved_energy_and_operating_net_benefit` |
| Fig. 11 | VOLL sensitivity of net societal benefit | `fig11_voll_sensitivity_of_net_societal_benefit` |
| Fig. 12 | Decomposition of economic opportunity costs and avoided interruption benefits | `fig12_decomposition_of_economic_opportunity_costs_and_avoided_interruption_benefits` |
| Fig. 13 | IEEE 33-bus distribution system configuration for HB-MPS power-flow validation | No separate repository file |
| Fig. 14 | IEEE 33-bus power-flow validation | `fig14_ieee_33_bus_power_flow_validation` |
| Fig. 14_1 | Dynamic bus-level dual-mode validation, α = 1.3 | `fig14_1_severity_dispatch_alpha_1_3` |
| Fig. 14_2 | Dynamic bus-level dual-mode validation, α = 1.5 | `fig14_2_severity_dispatch_alpha_1_5` |
| Fig. 15 | Spatiotemporal voltage heatmaps of the IEEE 33-bus system | `fig15_spatiotemporal_voltage_heatmaps_of_the_ieee_33_bus_system` |
| Fig. 16 | Hourly deployment of the main ESS-HFC truck and four auxiliary HFC trucks | `fig16_hourly_deployment_of_the_main_ess_hfc_truck_and_four_auxiliary_hfc_trucks` |

The repository's older `P1_*`, `ADDITIONAL_EXPERIMENTS.md`, and `EMERGENCY_DISPATCH_VALIDATION.md` reports describe the historical figure numbering and filenames used at the time of those runs. The supplementary or legacy plots `figure_economic_value_all_cases`, `fig_powerflow`, `figure_powerflow_voltage_profile`, and the three `emergency_figure_*` pairs have no matching numbered caption in this manuscript and were removed from the current `results` directory. Their historical versions remain available in Git history and the legacy archive. The main simulation and emergency experiment no longer generate these unused plots during their normal runs.

The revised Fig. 3 includes residential load, industrial load, and PV generation, so its manuscript caption should describe all three panels when the manuscript source is updated. Revised Fig. 7 has one panel showing the Mode 1, Mode 2, and standby time shares. Figs. 8–9 show both comparison bases from the PDF: (a) original component ratings and (b) equal total storage (3 MWh). In Figs. 5–6, (a), (b), and (c) follow α = 1.3, 1.5, and 1.8; Fig. 11 follows 1, 2, and 5 available trucks. In Fig. 14, panel pairs (a, b), (c, d), and (e, f) follow α = 1.3, 1.5, and 1.8.

The manuscript and saved results agree on the principal numerical outcomes (including Table II, Table III, and the power-flow minimum voltage), but manuscript Section IV-B states a non-standby share of approximately 56.5–61.9%. The saved `p1_main_hourly.csv` gives 63.69%, 58.93%, and 56.55% for α = 1.3, 1.5, and 1.8 respectively. Thus the range should be approximately 56.5–63.7% if those saved results are the intended final source. The manuscript PDF also contains editorial comments and has no corresponding manuscript source file in this repository; exact manuscript-version identity cannot be established from this repository alone.
