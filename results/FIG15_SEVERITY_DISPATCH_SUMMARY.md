# Figure 15 severity dispatch validation

The original Figure 15 and its validation workflow remain unchanged.
Each industrial bus uses P_i,th = α × mean(P_i) over 168 h and D_i(t) = max(0, P_i(t) − P_i,th).
Severity is S_i = 0.5 D_i/max_j(D_j) + 0.5 max(0, 0.95 − V_i,base)/0.95 (zero demand term if all D_i = 0).
Baseline AC voltage is calculated before the hourly ranking. Active trucks are placed at the highest-ranked bus with remaining local excess demand; if all demands are covered, the highest-ranked bus is used. One truck occupies one bus per hour, and ESS support stays with the main truck. Multiple trucks may use the same bus.
P1 HFC and ESS emergency outputs, fuel inventories, and financial results are unchanged. Raw operational kWh is converted to benchmark-feeder MW using industrial benchmark MW / peak raw industrial kWh, as in the existing validation. A one-hour interval makes injected MW numerically equal to benchmark MWh. Voltage violations count hours whose minimum bus voltage is strictly below 0.95 p.u.

| α | Active hours | Worst minimum voltage, baseline → support (p.u.) | Hours V < 0.95, baseline → support | Emergency supply, P1 raw (MWh) | AC-scaled injection (MWh) | Line losses, baseline → support (MWh) | Main injection bus frequency |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1.3 | 22 | 0.9236 → 0.9265 | 99 → 99 | 30.963 | 1.915 | 14.263 → 14.079 | Bus 32: 22 h |
| 1.5 | 8 | 0.9236 → 0.9239 | 99 → 99 | 1.570 | 0.097 | 14.263 → 14.253 | Bus 32: 8 h |

For illustrating voltage support, α = 1.3 is the clearer paper candidate: it dispatches more often and has the larger minimum-voltage improvement. α = 1.5 is a less aggressive operating case, but its voltage effect is small. Neither case reduces the number of hours below 0.95 p.u.; neither figure should be presented as restoring full voltage compliance.
