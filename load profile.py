
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
# 2. Load and preprocess data
# ---------------------------------------------------------
def load_data(file_path):
    df = pd.read_csv(file_path)

    col_map = {
        "주택용 전력사용량(kWh)": "load_A",
        "산업용 전력사용량(kWh)": "load_B",
        "날짜": "date",
        "시간": "hour",
    }

    df = df.rename(columns=col_map)

    required_cols = ["date", "hour", "load_A", "load_B"]

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
        2, 1,
        figsize=(13, 8.8),
        dpi=PAPER_DPI,
        sharex=True
    )

    # (a) Residential Load
    axes[0].plot(
        df["timestamp_dt"],
        df["load_A"],
        color="royalblue",
        linewidth=LINE_WIDTH,
        label="Residential Load"
    )

    axes[0].set_title(
        "(a) Residential Node",
        pad=14
    )
    axes[0].set_ylabel("Load (kWh)")
    axes[0].grid(True, linestyle="--", alpha=0.4)

    # (b) Industrial Load
    axes[1].plot(
        df["timestamp_dt"],
        df["load_B"],
        color="darkorange",
        linewidth=LINE_WIDTH,
        label="Industrial Load"
    )

    axes[1].set_title(
        "(b) Industrial Node",
        pad=14
    )
    axes[1].set_ylabel("Load (kWh)")
    axes[1].set_xlabel("Date")
    axes[1].grid(True, linestyle="--", alpha=0.4)

    # Date axis formatting
    axes[1].xaxis.set_major_formatter(
        mdates.DateFormatter("%m-%d")
    )
    axes[1].xaxis.set_major_locator(
        mdates.DayLocator(interval=1)
    )

    # Font, tick and legend formatting
    for ax in axes:
        ax.tick_params(axis="both", labelsize=FONT_TICK)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

        ax.legend(
            loc="upper right",
            prop={
                "weight": "bold",
                "size": FONT_LEGEND
            }
        )

        for tick in ax.get_xticklabels() + ax.get_yticklabels():
            tick.set_fontweight("bold")

        ax.yaxis.get_offset_text().set_fontweight("bold")

    fig.tight_layout(pad=2.0, h_pad=2.0)

    # -----------------------------------------------------
    # 4. Save Figures - results folder only
    # -----------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        OUTPUT_DIR / "figure_load_profiles.png",
        dpi=PAPER_DPI,
        bbox_inches="tight"
    )

    fig.savefig(
        OUTPUT_DIR / "figure_load_profiles.pdf",
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
