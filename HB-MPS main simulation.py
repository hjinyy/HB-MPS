import os
import math
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")  # 팝업 창 없이 저장만 수행

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator

plt.rcParams["font.weight"] = "bold"
plt.rcParams["axes.labelweight"] = "bold"
plt.rcParams["axes.titleweight"] = "bold"

# ---------------------------------------------------------
# 1. Configuration & Constants
# ---------------------------------------------------------
class Config:
    FILE_PATH = "data_file.csv"

    # Figure save path
    FIGURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

    # Scenario multipliers
    SCENARIO_MULTIPLIERS = [1.3, 1.5, 1.8]

    # Font sizes: 기존 대비 약 2배 확대
    FONT_TITLE = 28
    FONT_SUBTITLE = 22
    FONT_LABEL = 25
    FONT_TICK = 25
    FONT_LEGEND = 20
    FONT_TEXT = 20
    FONT_PIE = 23

    # System Capacities
    ESS_CAPACITY = 1500.0
    HFC_CAPACITY_KWH = 1500.0
    HFC_RATED_OUTPUT = 500.0

    # Hydrogen Physics
    KWH_PER_KG_H2 = 16.65
    MAX_H2_KG = HFC_CAPACITY_KWH / KWH_PER_KG_H2
    P2G_KWH_PER_KG = 55.0

    # ESS Efficiency & Limits
    ESS_EFFICIENCY = 0.95
    ESS_MIN_SOC = 0.1
    ESS_MAX_SOC = 0.9

    # Initial States
    INIT_ESS_SOC = 0.6
    INIT_HFC_LOH = 0.8

    # Thresholds
    PHASE1_SOC_LIMIT = 0.3
    PHASE1_LCOE_PERCENTILE = 0.4

    # Maintenance & Charging Logic
    H2_REFUEL_THRESHOLD = 0.6
    H2_TARGET_LEVEL = 0.9
    PENALTY_COST_PER_KWH = 500.0
    CHARGE_SMP_PERCENTILE = 0.25

    # VOLL Coefficients
    VOLL_A = -0.0000206
    VOLL_B = 0.0227011
    VOLL_C = 0.3018905
    SIMULATION_STEP_MIN = 60.0
    VOLL_UNIT_SCALE = 1000.0

    # Transportation and degradation cost
    TRUCK_FUEL_EFFICIENCY = 0.08
    DISTANCE_ONE_WAY = 1.7
    MOVE_H2_COST = TRUCK_FUEL_EFFICIENCY * DISTANCE_ONE_WAY
    BATTERY_WEAR_COST = 50.0


# ---------------------------------------------------------
# 2. HB-MPS Agent Class
# ---------------------------------------------------------
class H_MEP_Truck:
    def __init__(self, config, phase2_multiplier):
        self.cfg = config
        self.phase2_multiplier = phase2_multiplier
        self.ess_kwh = config.ESS_CAPACITY * config.INIT_ESS_SOC
        self.h2_kg = config.MAX_H2_KG * config.INIT_HFC_LOH
        self.history = []

    def get_soc(self):
        return self.ess_kwh / self.cfg.ESS_CAPACITY

    def get_loh(self):
        return self.h2_kg / self.cfg.MAX_H2_KG

    def calculate_voll_unit_cost(self, duration_minutes):
        exponent = (
            self.cfg.VOLL_A * (duration_minutes ** 2)
            + self.cfg.VOLL_B * duration_minutes
            + self.cfg.VOLL_C
        )
        return np.exp(exponent) * self.cfg.VOLL_UNIT_SCALE

    def run_step(
        self,
        timestamp,
        load_a,
        load_b,
        LCOE,
        SMP,
        solar,
        h2_cost,
        b_load_mean,
        LCOE_high_threshold,
        SMP_low_threshold
    ):
        mode = "STANDBY"
        action = "WAIT"
        power_output = 0.0
        revenue = 0.0
        op_cost = 0.0
        n_trucks = 1

        spike_threshold = b_load_mean * self.phase2_multiplier
        excess_load_base = max(0, load_b - spike_threshold)

        voll_unit_price = 0.0
        if excess_load_base > 0:
            voll_unit_price = self.calculate_voll_unit_cost(self.cfg.SIMULATION_STEP_MIN)

        base_penalty_cost = excess_load_base * voll_unit_price
        hmep_penalty_cost = base_penalty_cost
        excess_load_hmep = excess_load_base

        surplus_solar = solar - (load_a + load_b)

        if load_b >= spike_threshold:
            mode = "PHASE 2"
            required_power = excess_load_base

            n_trucks = math.ceil(required_power / self.cfg.HFC_RATED_OUTPUT)
            discharge_kwh = required_power

            if discharge_kwh > 0:
                action = f"HFC_DISCHARGE ({n_trucks} Trucks)"

                total_h2_consumed = discharge_kwh / self.cfg.KWH_PER_KG_H2

                truck1_capacity = min(discharge_kwh, self.cfg.HFC_RATED_OUTPUT)
                truck1_h2_need = truck1_capacity / self.cfg.KWH_PER_KG_H2

                move_h2_need = self.cfg.MOVE_H2_COST
                total_main_consumption = truck1_h2_need + move_h2_need

                if self.h2_kg >= total_main_consumption:
                    self.h2_kg -= total_main_consumption
                else:
                    shortage = total_main_consumption - self.h2_kg
                    self.h2_kg = 0
                    op_cost += shortage * h2_cost

                if n_trucks > 1:
                    aux_h2_need = total_h2_consumed - truck1_h2_need
                    aux_move_need = (n_trucks - 1) * self.cfg.MOVE_H2_COST
                    op_cost += (aux_h2_need + aux_move_need) * h2_cost

                hmep_penalty_cost = 0.0
                excess_load_hmep = 0.0

        elif self.get_loh() < self.cfg.H2_REFUEL_THRESHOLD:
            mode = "H2_MAINTENANCE"
            action = "BUY_EXTERNAL_H2"

            target_kg = self.cfg.MAX_H2_KG * self.cfg.H2_TARGET_LEVEL
            needed_kg = target_kg - self.h2_kg

            if needed_kg > 0:
                self.h2_kg += needed_kg
                op_cost += needed_kg * h2_cost

        elif (LCOE >= LCOE_high_threshold) and (self.get_soc() >= self.cfg.PHASE1_SOC_LIMIT):
            mode = "PHASE 1"

            discharge_cap = 700.0
            energy_avail = self.ess_kwh - (self.cfg.ESS_CAPACITY * self.cfg.ESS_MIN_SOC)
            discharge_kwh = min(discharge_cap, energy_avail)

            self.h2_kg -= self.cfg.MOVE_H2_COST
            op_cost += self.cfg.MOVE_H2_COST * h2_cost

            if discharge_kwh > 0:
                action = "ESS_DISCHARGE"
                self.ess_kwh -= discharge_kwh
                power_output = discharge_kwh * self.cfg.ESS_EFFICIENCY
                revenue = power_output * LCOE

                deg_cost = discharge_kwh * self.cfg.BATTERY_WEAR_COST
                op_cost += deg_cost

        else:
            if surplus_solar > 0:
                mode = "SOLAR_CHARGE"
                remaining_surplus = surplus_solar

                if self.get_soc() < self.cfg.ESS_MAX_SOC:
                    charge_cap = 300.0
                    space_avail = (self.cfg.ESS_CAPACITY * self.cfg.ESS_MAX_SOC) - self.ess_kwh
                    charge_kwh = min(remaining_surplus, charge_cap, space_avail)

                    self.ess_kwh += charge_kwh * self.cfg.ESS_EFFICIENCY
                    remaining_surplus -= charge_kwh
                    op_cost += charge_kwh * self.cfg.BATTERY_WEAR_COST
                    action = "SOLAR_CHARGE"

                if remaining_surplus > 0 and self.get_loh() < 1.0:
                    produced_kg = remaining_surplus / self.cfg.P2G_KWH_PER_KG
                    space_kg = self.cfg.MAX_H2_KG - self.h2_kg
                    real_production = min(produced_kg, space_kg)

                    self.h2_kg += real_production

                    if action == "SOLAR_CHARGE":
                        action = "SOLAR_CHARGE & P2G"
                    else:
                        action = "P2G_ONLY"

            elif (SMP <= SMP_low_threshold) and (self.get_soc() < 0.9):
                charge_cap = 300.0
                space = (self.cfg.ESS_CAPACITY * 0.9) - self.ess_kwh
                charge_kwh = min(charge_cap, space)

                if charge_kwh > 0.1:
                    mode = "GRID_CHARGE"
                    action = "GRID_BUY"

                    self.ess_kwh += charge_kwh * self.cfg.ESS_EFFICIENCY
                    op_cost += (charge_kwh * SMP) + (charge_kwh * self.cfg.BATTERY_WEAR_COST)

        hmep_penalty_cost = excess_load_hmep * voll_unit_price

        self.history.append({
            "timestamp": timestamp,
            "Load_B": load_b,
            "LCOE": LCOE,
            "SMP": SMP,
            "Mode": mode,
            "Action": action,
            "ESS_SOC": self.get_soc() * 100,
            "H2_LOH": self.get_loh() * 100,
            "Revenue": revenue,
            "Op_Cost": op_cost,
            "Net_Step_Profit": revenue - op_cost,
            "Base_Penalty": base_penalty_cost,
            "HMEP_Penalty": hmep_penalty_cost,
            "Avoided_Penalty": base_penalty_cost - hmep_penalty_cost,
            "Active_Trucks": n_trucks,
            "Threshold": spike_threshold,
            "Alpha": self.phase2_multiplier
        })


# ---------------------------------------------------------
# 3. Utility Functions
# ---------------------------------------------------------
def save_figure(fig, filename):
    os.makedirs(Config.FIGURE_DIR, exist_ok=True)

    png_path = os.path.join(Config.FIGURE_DIR, f"{filename}.png")
    pdf_path = os.path.join(Config.FIGURE_DIR, f"{filename}.pdf")

    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {png_path}")
    print(f"Saved: {pdf_path}")


def load_input_data():
    df = pd.read_csv(Config.FILE_PATH)

    col_map = {
        "주택용 전력사용량(kWh)": "load_A",
        "산업용 전력사용량(kWh)": "load_B",
        "LCOE=SMP+REC(원/kWh)": "LCOE",
        "E: 태양광 발전량(kWh)": "solar",
        "SMP(원/kWh)": "SMP",
        "수소 외부계통 충전 비용(원/kg)": "h2_cost",
        "날짜": "date",
        "시간": "hour"
    }

    df = df.rename(columns=col_map)

    df["date"] = pd.to_numeric(df["date"], errors="coerce")
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
    df = df.dropna(subset=["date", "hour"])

    base_dates = pd.to_datetime(
        df["date"].astype(int).astype(str),
        format="%Y%m%d",
        errors="coerce"
    )

    time_deltas = pd.to_timedelta(df["hour"] - 1, unit="h")
    df["timestamp_dt"] = base_dates + time_deltas

    df = df.dropna(subset=["timestamp_dt"])
    df = df.sort_values("timestamp_dt")

    for col in ["load_A", "load_B", "LCOE", "SMP", "solar", "h2_cost"]:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0.0)

    return df


def run_simulation_for_alpha(df, alpha):
    b_load_mean = df["load_B"].mean()
    LCOE_high_threshold = df["LCOE"].quantile(Config.PHASE1_LCOE_PERCENTILE)
    SMP_low_threshold = df["SMP"].quantile(Config.CHARGE_SMP_PERCENTILE)

    truck = H_MEP_Truck(Config, phase2_multiplier=alpha)

    for _, row in df.iterrows():
        truck.run_step(
            timestamp=row["timestamp_dt"],
            load_a=row["load_A"],
            load_b=row["load_B"],
            LCOE=row["LCOE"],
            SMP=row["SMP"],
            solar=row["solar"],
            h2_cost=row["h2_cost"],
            b_load_mean=b_load_mean,
            LCOE_high_threshold=LCOE_high_threshold,
            SMP_low_threshold=SMP_low_threshold
        )

    res = pd.DataFrame(truck.history)

    summary = {
        "alpha": alpha,
        "max_trucks": int(res["Active_Trucks"].max()),
        "mode2_count": int((res["Mode"] == "PHASE 2").sum()),
        "avg_trucks_mode2": (
            res[res["Mode"] == "PHASE 2"]["Active_Trucks"].mean()
            if (res["Mode"] == "PHASE 2").any()
            else 0.0
        ),
        "net_profit": res["Net_Step_Profit"].sum(),
        "base_penalty": res["Base_Penalty"].sum(),
        "avoided_penalty": res["Avoided_Penalty"].sum()
    }

    return res, summary


def run_all_scenarios():
    df = load_input_data()

    scenario_results = {}
    scenario_summaries = {}

    for alpha in Config.SCENARIO_MULTIPLIERS:
        res, summary = run_simulation_for_alpha(df, alpha)
        scenario_results[alpha] = res
        scenario_summaries[alpha] = summary

        print("\n" + "=" * 50)
        print(f"[Scenario alpha={alpha}]")
        print(f"- Maximum Trucks Deployed: {summary['max_trucks']}")
        print(f"- Mode 2 Activation: {summary['mode2_count']}")
        print(f"- Avg Trucks per Mode 2: {summary['avg_trucks_mode2']:.1f}")
        print(f"- Net Profit: {summary['net_profit']:,.0f} KRW")
        print(f"- Avoided Penalty: {summary['avoided_penalty']:,.0f} KRW")
        print("=" * 50)

    return scenario_results, scenario_summaries


# ---------------------------------------------------------
# 4. Drawing Functions
# ---------------------------------------------------------
def scenario_title(alpha):
    if alpha == 1.3:
        return "Tight Grid (α = 1.3)"
    elif alpha == 1.5:
        return "Standard Grid (α = 1.5)"
    elif alpha == 1.8:
        return "Robust Grid (α = 1.8)"
    return f"α = {alpha}"


def format_date_axis(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.tick_params(axis="x", labelsize=Config.FONT_TICK)
    ax.tick_params(axis="y", labelsize=Config.FONT_TICK)
    ax.yaxis.get_offset_text().set_fontsize(Config.FONT_TICK)


def draw_grid_resilience(ax, res, alpha):
    max_trucks = res["Active_Trucks"].max()
    threshold = res["Threshold"].iloc[0]

    ax.plot(
        res["timestamp"],
        res["Load_B"],
        color="gray",
        alpha=0.55,
        linewidth=2.4,
        label="Industrial Load"
    )

    ax.axhline(
        threshold,
        color="red",
        linestyle="--",
        linewidth=2.2,
        label="Mode 2 Trigger"
    )

    p2_mask = res["Mode"] == "PHASE 2"
    if p2_mask.any():
        ax.scatter(
            res[p2_mask]["timestamp"],
            res[p2_mask]["Load_B"],
            color="red",
            s=60,
            zorder=5,
            label="Mode 2 Active"
        )

    ax_right = ax.twinx()

    additional_mask = (res["Mode"] == "PHASE 2") & (res["Active_Trucks"] > 1)
    additional_indices = res[additional_mask].index

    if not additional_indices.empty:
        x_vals = res.loc[additional_indices, "timestamp"]
        y_vals = res.loc[additional_indices, "Active_Trucks"] - 1

        ax_right.bar(
            x_vals,
            y_vals,
            width=0.04,
            color="royalblue",
            alpha=0.6,
            label="Additional Trucks"
        )

    ax.set_title(scenario_title(alpha), fontsize=Config.FONT_SUBTITLE, fontweight="bold")
    ax.set_ylabel("Load (kWh)", fontsize=Config.FONT_LABEL)
    ax.grid(True, linestyle="--", alpha=0.35)

    ax_right.set_ylabel("Additional Trucks", color="royalblue", fontsize=Config.FONT_LABEL)
    ax_right.tick_params(axis="y", labelcolor="royalblue", labelsize=Config.FONT_TICK)

    max_additional = max(0, int(max_trucks) - 1)
    ax_right.set_ylim(0, max_additional + 1.5)
    ax_right.yaxis.set_major_locator(MaxNLocator(integer=True))

    lines_1, labels_1 = ax.get_legend_handles_labels()
    lines_2, labels_2 = ax_right.get_legend_handles_labels()
    ax.legend(
        lines_1 + lines_2,
        labels_1 + labels_2,
        loc="upper left",
        prop={"weight": "bold", "size": Config.FONT_LEGEND}
    )

    format_date_axis(ax)


def draw_asset_status(ax, res, alpha):
    ax.plot(
        res["timestamp"],
        res["ESS_SOC"],
        label="Battery SOC (%)",
        color="green",
        linewidth=2.4
    )

    ax.plot(
        res["timestamp"],
        res["H2_LOH"],
        label="Hydrogen LOH (%)",
        color="orange",
        linewidth=2.4
    )

    buy_mask = res["Action"] == "BUY_EXTERNAL_H2"
    if buy_mask.any():
        ax.scatter(
            res[buy_mask]["timestamp"],
            res[buy_mask]["H2_LOH"],
            color="blue",
            marker="^",
            s=90,
            label="External H2 Refueling"
        )

    grid_mask = res["Mode"] == "GRID_CHARGE"
    if grid_mask.any():
        ax.scatter(
            res[grid_mask]["timestamp"],
            res[grid_mask]["ESS_SOC"],
            color="mediumseagreen",
            s=45,
            label="Grid Charge"
        )

    ax.set_title(scenario_title(alpha), fontsize=Config.FONT_SUBTITLE, fontweight="bold")
    ax.set_ylabel("State (%)", fontsize=Config.FONT_LABEL)
    ax.set_ylim(0, 105)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(
        loc="lower left",
        prop={"weight": "bold", "size": Config.FONT_LEGEND}
    )

    format_date_axis(ax)


def draw_financial_flow(ax, res, alpha):
    revenue_cum = res["Revenue"].cumsum()
    cost_cum = -res["Op_Cost"].cumsum()
    profit_cum = res["Net_Step_Profit"].cumsum()

    ax.plot(
        res["timestamp"],
        revenue_cum,
        label="Revenue",
        color="gold",
        linewidth=2.4
    )

    ax.plot(
        res["timestamp"],
        cost_cum,
        label="Total Op Cost (H2 + Grid)",
        color="red",
        linestyle="--",
        linewidth=2.4
    )

    ax.plot(
        res["timestamp"],
        profit_cum,
        label="Net Profit",
        color="blue",
        linewidth=3.0
    )

    ax.axhline(0, color="black", linewidth=1.2)

    ax.set_title(scenario_title(alpha), fontsize=Config.FONT_SUBTITLE, fontweight="bold")
    ax.set_ylabel("KRW", fontsize=Config.FONT_LABEL)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(
        loc="best",
        prop={"weight": "bold", "size": Config.FONT_LEGEND}
    )

    format_date_axis(ax)


def draw_economic_value(ax, res, alpha):
    total_base_penalty = res["Base_Penalty"].sum()
    total_avoided = res["Avoided_Penalty"].sum()
    total_profit = res["Net_Step_Profit"].sum()

    hmep_value = -(total_base_penalty - total_avoided) + total_profit
    values = [-total_base_penalty, hmep_value]

    bars = ax.bar(
        ["Base Case\nRisk Cost", "HB-MPS\nNet Value"],
        values,
        color=["gray", "royalblue"],
        width=0.5
    )

    ax.axhline(0, color="black", linewidth=1.2)
    ax.set_title(scenario_title(alpha), fontsize=Config.FONT_SUBTITLE, fontweight="bold")
    ax.set_ylabel("KRW", fontsize=Config.FONT_LABEL)
    ax.grid(True, axis="y", linestyle="--", alpha=0.35)

    ax.tick_params(axis="x", labelsize=Config.FONT_TICK)
    ax.tick_params(axis="y", labelsize=Config.FONT_TICK)

    for rect in bars:
        height = rect.get_height()
        ax.text(
            rect.get_x() + rect.get_width() / 2.0,
            height,
            f"{height/1e6:.1f}M",
            ha="center",
            va="bottom" if height > 0 else "top",
            fontsize=Config.FONT_TEXT,
            fontweight="bold"
        )


def draw_mode_distribution(ax, res, alpha):
    mode_counts = res["Mode"].value_counts()

    colors = {
        "STANDBY": "lightgray",
        "PHASE 1": "gold",
        "PHASE 2": "red",
        "SOLAR_CHARGE": "cyan",
        "GRID_CHARGE": "mediumseagreen",
        "H2_MAINTENANCE": "orange"
    }

    pie_colors = []
    for mode_name in mode_counts.index:
        color = "gray"
        for key, value in colors.items():
            if key in mode_name:
                color = value
        pie_colors.append(color)

    wedges, _ = ax.pie(
        mode_counts,
        labels=None,
        colors=pie_colors,
        startangle=90,
        radius=1.2
    )

    total = mode_counts.sum()

    small_label_positions = []
    small_label_count = 0

    for wedge, value in zip(wedges, mode_counts.values):
        pct = value / total * 100

        angle = (wedge.theta1 + wedge.theta2) / 2.0
        x = np.cos(np.deg2rad(angle))
        y = np.sin(np.deg2rad(angle))

        # 큰 조각: pie 내부에 표시
        if pct >= 4:
            ax.text(
                0.62 * x,
                0.62 * y,
                f"{pct:.1f}%",
                ha="center",
                va="center",
                fontsize=Config.FONT_PIE,
                fontweight="bold"
            )

        # 작은 조각: pie 오른쪽 위에 세로 정렬해서 표시
        else:
            text_x = 1.28
            text_y = 0.95 - small_label_count * 0.18
            small_label_count += 1

            ax.text(
                text_x,
                text_y,
                f"{pct:.1f}%",
                ha="left",
                va="center",
                fontsize=Config.FONT_PIE,
                fontweight="bold"
            )

            # 조각과 숫자를 연결하는 선
            ax.annotate(
                "",
                xy=(0.95 * x, 0.95 * y),
                xytext=(text_x - 0.05, text_y),
                arrowprops=dict(
                    arrowstyle="-",
                    linewidth=1.4,
                    color="black"
                )
            )

    ax.legend(
        wedges,
        mode_counts.index,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        prop={"weight": "bold", "size": Config.FONT_LEGEND}
    )

    ax.set_title(
        scenario_title(alpha),
        fontsize=Config.FONT_SUBTITLE,
        fontweight="bold",
        pad=25
    )

    ax.set_aspect("equal")

    # 작은 숫자와 legend가 잘리지 않도록 좌우 공간 확보
    ax.set_xlim(-1.25, 1.75)
    ax.set_ylim(-1.25, 1.25)

# ---------------------------------------------------------
# 5. Multi-Scenario Figure Generation
# ---------------------------------------------------------
def create_grid_resilience_figure(scenario_results):
    fig, axes = plt.subplots(
        3, 1,
        figsize=(13, 16),
        dpi=300,
        sharex=True
    )

    for ax, alpha in zip(axes, Config.SCENARIO_MULTIPLIERS):
        draw_grid_resilience(ax, scenario_results[alpha], alpha)

    fig.suptitle(
        "Grid Resilience & HB-MPS Fleet Deployment",
        fontsize=Config.FONT_TITLE,
        fontweight="bold"
    )

    axes[-1].set_xlabel("Date", fontsize=Config.FONT_LABEL)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.subplots_adjust(hspace=0.25)
    save_figure(fig, "figure_6_grid_resilience_fleet_deployment_all_cases")


def create_asset_status_figure(scenario_results):
    fig, axes = plt.subplots(
        3, 1,
        figsize=(13, 16),
        dpi=300,
        sharex=True
    )

    for ax, alpha in zip(axes, Config.SCENARIO_MULTIPLIERS):
        draw_asset_status(ax, scenario_results[alpha], alpha)

    fig.suptitle(
        "Asset Status (Main Truck)",
        fontsize=Config.FONT_TITLE,
        fontweight="bold"
    )

    axes[-1].set_xlabel("Date", fontsize=Config.FONT_LABEL)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.subplots_adjust(hspace=0.25)
    save_figure(fig, "figure_7_asset_status_main_truck_all_cases")


def create_financial_flow_figure(scenario_results):
    fig, axes = plt.subplots(
        3, 1,
        figsize=(13, 16),
        dpi=300,
        sharex=True
    )

    for ax, alpha in zip(axes, Config.SCENARIO_MULTIPLIERS):
        draw_financial_flow(ax, scenario_results[alpha], alpha)

    fig.suptitle(
        "Financial Flow",
        fontsize=Config.FONT_TITLE,
        fontweight="bold"
    )

    axes[-1].set_xlabel("Date", fontsize=Config.FONT_LABEL)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.subplots_adjust(hspace=0.25)
    save_figure(fig, "figure_8_financial_flow_all_cases")


def create_economic_value_figure(scenario_results):
    fig, axes = plt.subplots(
        3, 1,
        figsize=(12, 15),
        dpi=300
    )

    for ax, alpha in zip(axes, Config.SCENARIO_MULTIPLIERS):
        draw_economic_value(ax, scenario_results[alpha], alpha)

    fig.suptitle(
        "Total Economic Value",
        fontsize=Config.FONT_TITLE,
        fontweight="bold"
    )

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.subplots_adjust(hspace=0.55)
    save_figure(fig, "figure_economic_value_all_cases")


def create_mode_distribution_figure(scenario_results):
    fig, axes = plt.subplots(
        3, 1,
        figsize=(12, 18),
        dpi=300
    )

    for ax, alpha in zip(axes, Config.SCENARIO_MULTIPLIERS):
        draw_mode_distribution(ax, scenario_results[alpha], alpha)

    fig.suptitle(
        "Operational Mode Distribution",
        fontsize=Config.FONT_TITLE,
        fontweight="bold"
    )

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.subplots_adjust(hspace=0.55)
    save_figure(fig, "figure_9_operational_mode_distribution_all_cases")


# ---------------------------------------------------------
# 6. Main
# ---------------------------------------------------------
def main():
    scenario_results, scenario_summaries = run_all_scenarios()

    create_grid_resilience_figure(scenario_results)
    create_asset_status_figure(scenario_results)
    create_financial_flow_figure(scenario_results)
    create_economic_value_figure(scenario_results)
    create_mode_distribution_figure(scenario_results)

    print("\nAll multi-scenario figures have been saved successfully.")
    print(f"Save directory: {Config.FIGURE_DIR}")


if __name__ == "__main__":
    main()
