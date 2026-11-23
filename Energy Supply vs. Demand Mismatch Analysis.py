from matplotlib.ticker import MultipleLocator
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# ---------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
FILE_PATH = BASE_DIR / "Data file" / "data_file.csv"
OUTPUT_DIR = BASE_DIR / "results"
PAPER_DPI = 300

FONT_TITLE = 33
FONT_LABEL = 32
FONT_TICK = 33
FONT_LEGEND = 22
LINE_WIDTH = 3.2

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.weight": "normal",
    "axes.titleweight": "normal",
    "axes.labelweight": "normal",
    "axes.titlesize": FONT_TITLE,
    "axes.labelsize": FONT_LABEL,
    "xtick.labelsize": FONT_TICK,
    "ytick.labelsize": FONT_TICK,
    "legend.fontsize": FONT_LEGEND,
})


# ---------------------------------------------------------
# 2. Load and preprocess data
# ---------------------------------------------------------
def load_data(file_path):
    df = pd.read_csv(file_path)

    col_map = {
        "주택용 전력사용량(kWh)": "load_A",
        "산업용 전력사용량(kWh)": "load_B",
        "E: 태양광 발전량(kWh)": "solar",
        "날짜": "date",
        "시간": "hour",
    }
    df = df.rename(columns=col_map)

    required_cols = ["date", "hour", "load_A", "load_B", "solar"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column is missing: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required_cols).copy()

    base_dates = pd.to_datetime(
        df["date"].astype(int).astype(str),
        format="%Y%m%d",
        errors="coerce",
    )

    df["timestamp_dt"] = base_dates + pd.to_timedelta(
        df["hour"] - 1, unit="h"
    )

    df = df.dropna(subset=["timestamp_dt"])
    df = df.sort_values("timestamp_dt")

    if df.empty:
        raise ValueError("No valid data rows were found in the CSV file.")

    df["total_load"] = df["load_A"] + df["load_B"]
    df["mismatch"] = df["solar"] - df["total_load"]

    return df


# ---------------------------------------------------------
# 3. Plot Energy Supply vs. Demand Mismatch Analysis
# ---------------------------------------------------------
def plot_supply_demand_mismatch(df):
    fig, axes = plt.subplots(
        2, 1,
        figsize=(13, 11),
        dpi=PAPER_DPI,
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1]},
    )
    # Y축 눈금 간격 설정
    axes[0].yaxis.set_major_locator(MultipleLocator(20000))
    axes[1].yaxis.set_major_locator(MultipleLocator(20000))

    # (a) Supply and demand profiles
    axes[0].plot(
        range(1, len(df) + 1),
        df["solar"],
        linewidth=LINE_WIDTH,
        label="PV Generation",
    )

    axes[0].plot(
        range(1, len(df) + 1),
        df["total_load"],
        linewidth=LINE_WIDTH,
        linestyle="--",
        label="Total Load",
    )

    axes[0].set_ylabel("Energy (kWh)")
    axes[0].grid(True, linestyle="--", alpha=0.4)

    # (b) Mismatch analysis
    x = range(1, len(df) + 1)
    mismatch = df["mismatch"].to_numpy()

    axes[1].axhline(
        0, color="black", linewidth=1.8
    )

    axes[1].fill_between(
        x, mismatch, 0,
        where=mismatch >= 0,
        alpha=0.35,
        interpolate=True,
        label="Surplus PV",
    )

    axes[1].fill_between(
        x, mismatch, 0,
        where=mismatch < 0,
        alpha=0.35,
        interpolate=True,
        label="Energy Deficit",
    )

    axes[1].plot(
        x, mismatch,
        linewidth=2.8,
        label="PV - Total Load",
    )

    axes[1].set_ylabel("Mismatch (kWh)")
    axes[0].set_xlabel("(a)")
    axes[1].set_xlabel("Time[h]\n(b)")
    axes[1].grid(True, linestyle="--", alpha=0.4)

    # Font and legend formatting
    for ax in axes:
        ax.set_xlim(0, 168)
        ax.set_xticks(range(0, 169, 24))
        ax.tick_params(axis="both", labelsize=FONT_TICK)

        ax.legend(
            loc="upper right",
            prop={"weight": "normal", "size": FONT_LEGEND}
        )

    fig.tight_layout(pad=2.0, h_pad=2.0)

    # Save figures
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        OUTPUT_DIR / "fig4_energy_supply_vs_demand_mismatch_analysis.png",
        dpi=PAPER_DPI,
        bbox_inches="tight"
    )

    fig.savefig(
        OUTPUT_DIR / "fig4_energy_supply_vs_demand_mismatch_analysis.pdf",
        bbox_inches="tight"
    )



# ---------------------------------------------------------
# 4. Main
# ---------------------------------------------------------
if __name__ == "__main__":
    df = load_data(FILE_PATH)
    plot_supply_demand_mismatch(df)
