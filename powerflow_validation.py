"""IEEE 33-bus HB-MPS power-flow validation and publication figures.

Figure (a): minimum node voltage by hour; Mode 2 markers refer to the BASELINE.
Figure (b): nodal voltage profile at the actual peak of normalized benchmark load.
"""
from pathlib import Path
import logging
import math
import warnings

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as nw
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
logging.getLogger("pandapower").setLevel(logging.ERROR)

# ---------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
FILE_PATH = BASE_DIR / "Data file" / "data_file.csv"
OUTPUT_DIR = BASE_DIR / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PF = 0.9
TANP = math.tan(math.acos(PF))
VMIN = 0.95
VSLACK = 1.03
P_HFC = 0.5  # MW per truck

IND_B = [17, 16, 15, 14, 13, 32, 31, 30, 29]
RES_B = [8, 9, 10, 11, 12, 24, 25, 21, 22]
PV_B = 6
HB_B = 17

PAPER_DPI = 300
FONT_TITLE = 22
FONT_LABEL = 19
FONT_TICK = 15
FONT_LEGEND = 12
LINE_WIDTH = 2.4
MARKER_SIZE = 4

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.weight": "bold",
    "axes.titleweight": "bold",
    "axes.labelweight": "bold",
    "axes.titlesize": FONT_TITLE,
    "axes.labelsize": FONT_LABEL,
    "xtick.labelsize": FONT_TICK,
    "ytick.labelsize": FONT_TICK,
    "legend.fontsize": FONT_LEGEND,
    "pdf.fonttype": 42,
})

# ---------------------------------------------------------
# 2. Load and normalize input profiles
# ---------------------------------------------------------
df = pd.read_csv(FILE_PATH)
cols = ["산업용 전력사용량(kWh)", "주택용 전력사용량(kWh)", "E: 태양광 발전량(kWh)"]
for col in cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df = df.dropna(subset=cols).reset_index(drop=True)
if df.empty:
    raise ValueError("No valid industrial/residential/PV input rows.")

ind = df[cols[0]].to_numpy(dtype=float)
res = df[cols[1]].to_numpy(dtype=float)
pv = df[cols[2]].to_numpy(dtype=float)
T = len(df)

base = nw.case33bw()
P_IND = base.load.loc[base.load.bus.isin(IND_B), "p_mw"].sum()
P_RES = base.load.loc[base.load.bus.isin(RES_B), "p_mw"].sum()


def norm(x, lo=0.6, hi=1.1):
    if np.max(x) == np.min(x):
        raise ValueError("Constant load profile cannot be min-max normalized.")
    return lo + (x - np.min(x)) / (np.max(x) - np.min(x)) * (hi - lo)


ind_pu = norm(ind)
res_pu = norm(res)
ind_mw = ind_pu * P_IND
res_mw = res_pu * P_RES
pv_mw = (pv / pv.max()) * P_IND if pv.max() > 0 else np.zeros_like(pv)
E_th_pu = 1.3 * ind_pu.mean()

# AUTO selection: peak of normalized total IEEE 33-bus load (NOT a fixed t=107).
PEAK_T = int(np.argmax(ind_mw + res_mw))

# ---------------------------------------------------------
# 3. IEEE 33-bus network model
# ---------------------------------------------------------
def build_network(imw, rmw, pmw, hbmw):
    net = nw.case33bw()
    net.ext_grid.loc[:, "vm_pu"] = VSLACK
    net.load = net.load.iloc[0:0].copy()

    pi = imw / len(IND_B)
    for b in IND_B:
        pp.create_load(net, b, p_mw=pi, q_mvar=pi * TANP)

    pr = rmw / len(RES_B)
    for b in RES_B:
        pp.create_load(net, b, p_mw=pr, q_mvar=pr * TANP)

    if pmw > 0:
        pp.create_sgen(net, PV_B, p_mw=pmw, q_mvar=0)
    if hbmw > 0:
        pp.create_sgen(net, HB_B, p_mw=hbmw, q_mvar=0)
    return net


# ---------------------------------------------------------
# 4. Time-series power flow
# ---------------------------------------------------------
rows = []
peak_profiles = {}

for t in range(T):
    excess_mw = max(ind_pu[t] - E_th_pu, 0) * P_IND
    ntr = math.ceil(excess_mw / P_HFC) if excess_mw > 0 else 0
    hbmw = ntr * P_HFC  # Original full-truck injection assumption retained

    result = {"t": t, "mode2": int(excess_mw > 0), "ntruck": ntr}
    for tag, hb in (("base", 0.0), ("hbmps", hbmw)):
        net = build_network(ind_mw[t], res_mw[t], pv_mw[t], hb)
        pp.runpp(net, algorithm="nr")
        voltages = net.res_bus.vm_pu
        result[f"vmin_{tag}"] = float(voltages.min())
        result[f"vminbus_{tag}"] = int(voltages.idxmin())
        result[f"ploss_{tag}"] = float(net.res_line.pl_mw.sum())
        result[f"viol_{tag}"] = int(voltages.min() < VMIN)
        if t == PEAK_T:
            peak_profiles[tag] = voltages.sort_index().copy()
    rows.append(result)

R = pd.DataFrame(rows)
R.to_csv(OUTPUT_DIR / "pf_results.csv", index=False)

print(f"IEEE 33-bus | Vslack={VSLACK} pu | PF={PF}")
print(f"Normalized load peak: t={PEAK_T}; total={ind_mw[PEAK_T]+res_mw[PEAK_T]:.4f} MW")
print(f"Mode 2 triggered: {int(R.mode2.sum())}/{T}; maximum trucks={R.ntruck.max()}")
print(f"Minimum voltage, Base: {R.vmin_base.min():.4f} pu; HB-MPS: {R.vmin_hbmps.min():.4f} pu")
print(f"Hours below {VMIN:.2f} pu: {R.viol_base.sum()} -> {R.viol_hbmps.sum()}")

# ---------------------------------------------------------
# 5. Two-panel figure: same composition as reference
# ---------------------------------------------------------
fig, axes = plt.subplots(2, 1, figsize=(10.5, 9.5), dpi=PAPER_DPI)
red, blue, orange = "#c6382b", "#2574ac", "#e68127"

# (a) Voltage time series: orange markers are on *BASE* red profile.
ax = axes[0]
ax.plot(R.t, R.vmin_base, color=red, lw=LINE_WIDTH, label="Base (no HB-MPS)")
ax.plot(R.t, R.vmin_hbmps, color=blue, lw=LINE_WIDTH, label="With HB-MPS")
ax.axhline(VMIN, color="black", lw=1.8, ls="--", label="0.95 pu limit")
m2 = R.mode2.eq(1)
ax.scatter(R.loc[m2, "t"], R.loc[m2, "vmin_base"],
           color=orange, s=42, zorder=6, label="Mode 2 triggered")
ax.set_title("(a) Minimum node voltage over the operation horizon", pad=10)
ax.set_xlabel("Time (h)")
ax.set_ylabel("Min. bus voltage (pu)")
ax.set_xlim(0, T - 1)
ax.set_ylim(min(VMIN, R.vmin_base.min(), R.vmin_hbmps.min()) - 0.012,
            max(R.vmin_base.max(), R.vmin_hbmps.max()) + 0.008)
ax.legend(loc="lower left", ncol=2, prop={"weight": "bold", "size": FONT_LEGEND})

# (b) All bus voltages at peak normalized total IEEE 33-bus demand.
ax = axes[1]
base_v, hbmps_v = peak_profiles["base"], peak_profiles["hbmps"]
ax.plot(base_v.index, base_v.values, color=red, lw=1.8,
        marker="o", markersize=MARKER_SIZE, label="Base (no HB-MPS)")
ax.plot(hbmps_v.index, hbmps_v.values, color=blue, lw=1.8,
        marker="s", markersize=MARKER_SIZE, label="With HB-MPS")
ax.axhline(VMIN, color="black", lw=1.6, ls="--")
ax.axvline(HB_B, color="#32b16d", lw=1.8, ls=":",
           label=f"HB-MPS node (bus {HB_B})")
ax.set_title(f"(b) Nodal voltage profile at peak-load hour (t={PEAK_T})", pad=10)
ax.set_xlabel("Bus index")
ax.set_ylabel("Voltage (pu)")
ax.set_xlim(int(base_v.index.min()), int(base_v.index.max()))
ax.set_ylim(min(VMIN, base_v.min(), hbmps_v.min()) - 0.006,
            max(base_v.max(), hbmps_v.max()) + 0.005)
ax.legend(loc="lower left", prop={"weight": "bold", "size": FONT_LEGEND})

for ax in axes:
    ax.grid(True, color="0.75", alpha=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=FONT_TICK)
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontweight("bold")

fig.tight_layout(h_pad=1.5)
fig.savefig(OUTPUT_DIR / "figure_powerflow_voltage_profile.png", dpi=PAPER_DPI, bbox_inches="tight")
fig.savefig(OUTPUT_DIR / "figure_powerflow_voltage_profile.pdf", bbox_inches="tight")
plt.close(fig)
print(f"Saved: {OUTPUT_DIR / 'figure_powerflow_voltage_profile.png'}")
