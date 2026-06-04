import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# ---------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------
FILE_PATH = "data_file.csv"
PAPER_DPI = 300


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
        "시간": "hour"
    }

    df = df.rename(columns=col_map)

    required_cols = ["date", "hour", "load_A", "load_B", "solar"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column is missing: {col}")

    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required_cols)

    base_dates = pd.to_datetime(
        df["date"].astype(int).astype(str),
        format="%Y%m%d",
        errors="coerce"
    )

    time_deltas = pd.to_timedelta(df["hour"] - 1, unit="h")
    df["timestamp_dt"] = base_dates + time_deltas

    df = df.dropna(subset=["timestamp_dt"])
    df = df.sort_values("timestamp_dt")

    df["total_load"] = df["load_A"] + df["load_B"]
    df["mismatch"] = df["solar"] - df["total_load"]

    return df


# ---------------------------------------------------------
# 3. Plot Energy Supply vs. Demand Mismatch Analysis
# ---------------------------------------------------------
def plot_supply_demand_mismatch(df):
    fig, axes = plt.subplots(
        2, 1,
        figsize=(10, 5.8),
        dpi=PAPER_DPI,
        sharex=True,
        gridspec_kw={"height_ratios": [2.1, 1.0]}
    )

    # (a) Supply and demand profiles
    axes[0].plot(
        df["timestamp_dt"],
        df["solar"],
        linewidth=1.8,
        label="PV Generation"
    )

    axes[0].plot(
        df["timestamp_dt"],
        df["total_load"],
        linewidth=1.8,
        linestyle="--",
        label="Total Load"
    )

    axes[0].set_title("(a) Energy Supply and Demand Profiles", fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Energy (kWh)")
    axes[0].grid(True, linestyle="--", alpha=0.4)
    axes[0].legend(loc="upper right")

    # (b) Mismatch analysis
    axes[1].axhline(0, linewidth=0.9)

    axes[1].fill_between(
        df["timestamp_dt"],
        df["mismatch"],
        0,
        where=df["mismatch"] >= 0,
        alpha=0.35,
        interpolate=True,
        label="Surplus PV"
    )

    axes[1].fill_between(
        df["timestamp_dt"],
        df["mismatch"],
        0,
        where=df["mismatch"] < 0,
        alpha=0.35,
        interpolate=True,
        label="Energy Deficit"
    )

    axes[1].plot(
        df["timestamp_dt"],
        df["mismatch"],
        linewidth=1.2,
        label="PV - Total Load"
    )

    axes[1].set_title("(b) Supply-Demand Mismatch", fontsize=11, fontweight="bold")
    axes[1].set_ylabel("Mismatch (kWh)")
    axes[1].set_xlabel("Date")
    axes[1].grid(True, linestyle="--", alpha=0.4)
    axes[1].legend(loc="upper right")

    # x축에서 시간 제거: 날짜만 표시
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    axes[1].xaxis.set_major_locator(mdates.DayLocator(interval=1))

    plt.xticks(rotation=0)
    plt.tight_layout()

    plt.savefig("figure_5_energy_supply_demand_mismatch.png", dpi=PAPER_DPI, bbox_inches="tight")
    plt.savefig("figure_5_energy_supply_demand_mismatch.pdf", bbox_inches="tight")

    plt.show()


# ---------------------------------------------------------
# 4. Main
# ---------------------------------------------------------
if __name__ == "__main__":
    df = load_data(FILE_PATH)
    plot_supply_demand_mismatch(df)