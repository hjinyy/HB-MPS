
from pathlib import Path
import math
import logging
import warnings

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as nw
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

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
P_HFC = 0.5

IND_B = [17, 16, 15, 14, 13, 32, 31, 30, 29]
RES_B = [8, 9, 10, 11, 12, 24, 25, 21, 22]
PV_B = 6
HB_B = 17

# Figure style
PAPER_DPI = 300

FONT_TITLE = 33
FONT_LABEL = 32
FONT_TICK = 33
FONT_LEGEND = 22
LINE_WIDTH = 3.2

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
})


# ---------------------------------------------------------
# 2. Load Data and Normalize
# ---------------------------------------------------------
df = pd.read_csv(FILE_PATH).dropna(
    subset=["산업용 전력사용량(kWh)"]
).reset_index(drop=True)

ind = df["산업용 전력사용량(kWh)"].to_numpy()
res = df["주택용 전력사용량(kWh)"].to_numpy()
pv = df["E: 태양광 발전량(kWh)"].to_numpy()

T = len(ind)
base = nw.case33bw()

P_IND = base.load.loc[
    base.load.bus.isin(IND_B), "p_mw"
].sum()

P_RES = base.load.loc[
    base.load.bus.isin(RES_B), "p_mw"
].sum()


def norm(x, lo=0.6, hi=1.1):
    if x.max() == x.min():
        raise ValueError("Cannot normalize constant load data.")

    return lo + (x - x.min()) / (
        x.max() - x.min()
    ) * (hi - lo)


ind_pu = norm(ind)
res_pu = norm(res)

ind_mw = ind_pu * P_IND
res_mw = res_pu * P_RES

pv_mw = (
    (pv / pv.max()) * P_IND
    if pv.max() > 0 else pv * 0
)

E_th_pu = 1.3 * ind_pu.mean()


# ---------------------------------------------------------
# 3. Build IEEE 33-bus Network
# ---------------------------------------------------------
def build(imw, rmw, pmw, hbmw):
    net = nw.case33bw()

    net.ext_grid.vm_pu = VSLACK
    net.load = net.load.iloc[0:0]

    pi = imw / len(IND_B)

    for b in IND_B:
        pp.create_load(
            net, b,
            p_mw=pi,
            q_mvar=pi * TANP
        )

    pr = rmw / len(RES_B)

    for b in RES_B:
        pp.create_load(
            net, b,
            p_mw=pr,
            q_mvar=pr * TANP
        )

    if pmw > 0:
        pp.create_sgen(
            net, PV_B,
            p_mw=pmw,
            q_mvar=0
        )

    if hbmw > 0:
        pp.create_sgen(
            net, HB_B,
            p_mw=hbmw,
            q_mvar=0
        )

    return net


# ---------------------------------------------------------
# 4. Power Flow Validation
# ---------------------------------------------------------
rows = []

for t in range(T):
    ex = max(ind_pu[t] - E_th_pu, 0) * P_IND

    ntr = math.ceil(ex / P_HFC) if ex > 0 else 0
    hbmw = ntr * P_HFC

    r = {
        "t": t,
        "mode2": int(ex > 0),
        "ntruck": ntr
    }

    for tag, hb in [("base", 0.0), ("hbmps", hbmw)]:
        net = build(
            ind_mw[t],
            res_mw[t],
            pv_mw[t],
            hb
        )

        pp.runpp(net, algorithm="nr")

        r[f"vmin_{tag}"] = net.res_bus.vm_pu.min()
        r[f"vminbus_{tag}"] = int(
            net.res_bus.vm_pu.idxmin()
        )
        r[f"ploss_{tag}"] = net.res_line.pl_mw.sum()
        r[f"viol_{tag}"] = int(
            net.res_bus.vm_pu.min() < VMIN
        )

    rows.append(r)

R = pd.DataFrame(rows)

R.to_csv(
    OUTPUT_DIR / "pf_results.csv",
    index=False
)


# ---------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------
m2 = R[R.mode2 == 1]
nm2 = R[R.mode2 == 0]

print("=" * 64)
print(
    f"IEEE 33-bus | slack={VSLACK}pu | PF={PF} | "
    f"산업정격{P_IND:.2f}MW 주거{P_RES:.2f}MW"
)
print("=" * 64)

print(
    f"Mode2 발동 : {R.mode2.sum()}/{T} 시점 "
    f"(최대 {R.ntruck.max()}트럭)"
)

print(
    f"Baseline 전압범위 : "
    f"[{R.vmin_base.min():.4f}, "
    f"{R.vmin_base.max():.4f}] pu"
)

print(
    f"HB-MPS 전압범위 : "
    f"[{R.vmin_hbmps.min():.4f}, "
    f"{R.vmin_hbmps.max():.4f}] pu"
)

print(
    f"전압위반(<0.95pu) : "
    f"base {R.viol_base.sum()} "
    f"-> hbmps {R.viol_hbmps.sum()} 시점"
)

if len(m2):
    vbase = m2.vmin_base.mean()
    vhbmps = m2.vmin_hbmps.mean()

    print(
        f"\nMode2 시점({len(m2)}): "
        f"최저V {vbase:.4f} -> {vhbmps:.4f} pu "
        f"(+{(vhbmps - vbase) * 100:.2f}%p)"
    )

    print(
        f"위반해소: base {m2.viol_base.sum()}/{len(m2)} "
        f"-> hbmps {m2.viol_hbmps.sum()}/{len(m2)}"
    )

else:
    print("\nMode2 발동 시점 없음")

print(
    f"비-Mode2 시점({len(nm2)}): "
    f"최저V {nm2.vmin_base.mean():.4f} pu, "
    f"위반 {nm2.viol_base.sum()}"
)

tp = len(R[(R.mode2 == 1) & (R.viol_base == 1)])
fp = len(R[(R.mode2 == 1) & (R.viol_base == 0)])
fn = len(R[(R.mode2 == 0) & (R.viol_base == 1)])
tn = len(R[(R.mode2 == 0) & (R.viol_base == 0)])

precision = tp / (tp + fp) * 100 if tp + fp else 0
recall = tp / (tp + fn) * 100 if tp + fn else 0

print(
    f"\nMode2 판단 vs 전압위반: "
    f"정밀도 {precision:.0f}% "
    f"재현율 {recall:.0f}%"
)

print(
    f"M2&위반={tp} M2&정상={fp} "
    f"정상판단&위반={fn} 정상&정상={tn}"
)

w = R.loc[R.vmin_base.idxmin()]

print(
    f"\n최악부하 t={int(w.t)}: "
    f"최저V {w.vmin_base:.4f}"
    f"->{w.vmin_hbmps:.4f}pu, "
    f"{int(w.ntruck)}트럭, "
    f"손실 {w.ploss_base * 1000:.1f}"
    f"->{w.ploss_hbmps * 1000:.1f}kW"
)

print(
    f"최저전압 최빈 노드: "
    f"bus {int(R.vminbus_base.mode().iloc[0])} "
    f"(HB-MPS 접속 노드: bus {HB_B})"
)


# ---------------------------------------------------------
# 6. Plot Power Flow Validation Results
# ---------------------------------------------------------
fig, axes = plt.subplots(
    2, 1,
    figsize=(13, 11),
    dpi=PAPER_DPI,
    sharex=True
)

# (a) Minimum Bus Voltage
axes[0].plot(
    R.t,
    R.vmin_base,
    linewidth=LINE_WIDTH,
    label="Baseline",
    color="dimgray"
)

axes[0].plot(
    R.t,
    R.vmin_hbmps,
    linewidth=LINE_WIDTH,
    label="HB-MPS",
    color="royalblue"
)

axes[0].axhline(
    VMIN,
    linestyle="--",
    linewidth=2.2,
    color="red",
    label="Lower Voltage Limit"
)

axes[0].set_title(
    "(a) Minimum Bus Voltage",
    pad=14
)

axes[0].set_ylabel("Voltage (pu)")


# (b) Network Line Loss
axes[1].plot(
    R.t,
    R.ploss_base * 1000,
    linewidth=LINE_WIDTH,
    label="Baseline",
    color="dimgray"
)

axes[1].plot(
    R.t,
    R.ploss_hbmps * 1000,
    linewidth=LINE_WIDTH,
    label="HB-MPS",
    color="royalblue"
)

axes[1].set_title(
    "(b) Network Line Loss",
    pad=14
)

axes[1].set_ylabel("Line Loss (kW)")
axes[1].set_xlabel("Time Step")


# ---------------------------------------------------------
# 7. Figure Formatting
# ---------------------------------------------------------
for ax in axes:
    ax.grid(
        True,
        linestyle="--",
        alpha=0.35
    )

    ax.yaxis.set_major_locator(
        MaxNLocator(nbins=5)
    )

    ax.tick_params(
        axis="both",
        labelsize=FONT_TICK
    )

    ax.legend(
        loc="best",
        prop={
            "weight": "bold",
            "size": FONT_LEGEND
        }
    )

    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontweight("bold")

    ax.yaxis.get_offset_text().set_fontweight("bold")

fig.tight_layout(
    pad=2.0,
    h_pad=2.0
)


# ---------------------------------------------------------
# 8. Save Figure
# ---------------------------------------------------------
fig.savefig(
    OUTPUT_DIR / "figure_powerflow_voltage_loss.png",
    dpi=PAPER_DPI,
    bbox_inches="tight"
)

fig.savefig(
    OUTPUT_DIR / "figure_powerflow_voltage_loss.pdf",
    bbox_inches="tight"
)

plt.close(fig)

print(f"\nResults and figures saved to: {OUTPUT_DIR}")
