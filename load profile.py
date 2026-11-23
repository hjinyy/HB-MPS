
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


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
        raise ValueError("No valid load profile data found.")

    return df


# ---------------------------------------------------------
# 3. Plot Load Profiles
# ---------------------------------------------------------
def plot_load_profiles(df):

    fig, axes = plt.subplots(
        3, 1,
        figsize=(13, 13.8),
        dpi=PAPER_DPI,
        sharex=True
    )

    # (a) Residential Load
    axes[0].plot(
        range(1, len(df) + 1),
        df["load_A"] / 1000,
        color="royalblue",
        linewidth=LINE_WIDTH,
        label="Residential Load"
    )

    axes[0].set_ylabel("Residential load (MWh)")
    axes[0].grid(True, linestyle="--", alpha=0.4)

    # (b) Industrial Load
    axes[1].plot(
        range(1, len(df) + 1),
        df["load_B"] / 1000,
        color="darkorange",
        linewidth=LINE_WIDTH,
        label="Industrial Load"
    )

    axes[1].set_ylabel("Industrial load (MWh)")
    axes[1].grid(True, linestyle="--", alpha=0.4)

    axes[2].plot(
        range(1, len(df) + 1),
        df["solar"] / 1000,
        color="seagreen",
        linewidth=LINE_WIDTH,
        label="PV generation",
    )
    axes[2].set_ylabel("PV generation (MWh)")
    axes[2].set_xlabel("Time[h]\n(c)")
    axes[2].grid(True, linestyle="--", alpha=0.4)

    axes[0].set_xlabel("(a)")
    axes[1].set_xlabel("(b)")

    # Font and tick formatting
    for ax in axes:
        ax.set_xlim(0, 168)
        ax.set_xticks(range(0, 169, 24))
        ax.tick_params(axis="both", labelsize=FONT_TICK)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

    fig.tight_layout(pad=2.0, h_pad=3.0)

    # -----------------------------------------------------
    # 4. Save Figures - results folder only
    # -----------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        OUTPUT_DIR / "fig3_comparison_of_load_profiles.png",
        dpi=PAPER_DPI,
        bbox_inches="tight"
    )

    fig.savefig(
        OUTPUT_DIR / "fig3_comparison_of_load_profiles.pdf",
        bbox_inches="tight"
    )

    plt.close(fig)

    print(f"Load profile figures saved to: {OUTPUT_DIR}")


# ---------------------------------------------------------
# 5. Main
# ---------------------------------------------------------
if __name__ == "__main__":
    df = load_data(FILE_PATH)
    plot_load_profiles(df)
