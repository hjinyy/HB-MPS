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
        "날짜": "date",
        "시간": "hour"
    }

    df = df.rename(columns=col_map)

    required_cols = ["date", "hour", "load_A", "load_B"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column is missing: {col}")

    df["date"] = pd.to_numeric(df["date"], errors="coerce")
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
    df["load_A"] = pd.to_numeric(df["load_A"], errors="coerce")
    df["load_B"] = pd.to_numeric(df["load_B"], errors="coerce")

    df = df.dropna(subset=["date", "hour", "load_A", "load_B"])

    base_dates = pd.to_datetime(
        df["date"].astype(int).astype(str),
        format="%Y%m%d",
        errors="coerce"
    )

    time_deltas = pd.to_timedelta(df["hour"] - 1, unit="h")
    df["timestamp_dt"] = base_dates + time_deltas

    df = df.dropna(subset=["timestamp_dt"])
    df = df.sort_values("timestamp_dt")

    return df


# ---------------------------------------------------------
# 3. Plot two load profiles
# ---------------------------------------------------------
def plot_load_profiles(df):
    fig, axes = plt.subplots(
        2, 1,
        figsize=(10, 5.5),
        dpi=PAPER_DPI,
        sharex=True
    )

    # (a) Residential Node
    axes[0].plot(
        df["timestamp_dt"],
        df["load_A"],
        linewidth=1.8,
        label="Residential Load"
    )
    axes[0].set_title("(a) Residential Node", fontsize=11, fontweight="bold")
    axes[0].set_ylabel("Load (kWh)")
    axes[0].grid(True, linestyle="--", alpha=0.4)
    axes[0].legend(loc="upper right")

    # (b) Industrial Node
    axes[1].plot(
        df["timestamp_dt"],
        df["load_B"],
        linewidth=1.8,
        label="Industrial Load"
    )
    axes[1].set_title("(b) Industrial Node", fontsize=11, fontweight="bold")
    axes[1].set_ylabel("Load (kWh)")
    axes[1].set_xlabel("Date")
    axes[1].grid(True, linestyle="--", alpha=0.4)
    axes[1].legend(loc="upper right")

    # x축에서 시간 제거: 날짜만 표시
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    axes[1].xaxis.set_major_locator(mdates.DayLocator(interval=1))

    plt.xticks(rotation=0)
    plt.tight_layout()

    plt.savefig("figure_load_profiles.png", dpi=PAPER_DPI, bbox_inches="tight")
    plt.savefig("figure_load_profiles.pdf", bbox_inches="tight")

    plt.show()


# ---------------------------------------------------------
# 4. Main
# ---------------------------------------------------------
if __name__ == "__main__":
    df = load_data(FILE_PATH)
    plot_load_profiles(df)