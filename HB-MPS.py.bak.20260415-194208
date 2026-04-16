import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# ---------------------------------------------------------
# 1. Configuration & Constants
# ---------------------------------------------------------
class Config:
    FILE_PATH = 'data_file.csv'

    # System Capacitaies
    ESS_CAPACITY = 1500.0  # kWh
    HFC_CAPACITY_KWH = 1500.0  # kWh
    HFC_RATED_OUTPUT = 500.0  # kW

    # Hydrogen Physics
    KWH_PER_KG_H2 = 16.65
    MAX_H2_KG = HFC_CAPACITY_KWH / KWH_PER_KG_H2  # approx 90.1 kg
    P2G_KWH_PER_KG = 55.0

    # ESS Efficiency & Limits
    ESS_EFFICIENCY = 0.95
    ESS_MIN_SOC = 0.1
    ESS_MAX_SOC = 0.9

    # Initial States
    INIT_ESS_SOC = 0.6
    INIT_HFC_LOH = 0.8

    # Thresholds
    PHASE2_MULTIPLIER = 1.8
    PHASE1_SOC_LIMIT = 0.3
    PHASE1_LCOE_PERCENTILE = 0.4

    # Maintenance & Charging Logic
    H2_REFUEL_THRESHOLD = 0.6
    H2_TARGET_LEVEL = 0.9  # 90%까지 충전
    PENALTY_COST_PER_KWH = 500.0
    CHARGE_SMP_PERCENTILE = 0.25  # SMP 하위 25%

    #VOLL (Value of Lost Load) Coefficients
    # 식: cost = exp(a*t^2 + b*t + c)
    VOLL_A = -0.0000206
    VOLL_B = 0.0227011
    VOLL_C = 0.3018905
    SIMULATION_STEP_MIN = 60.0  # 시뮬레이션 간격 (분)
    VOLL_UNIT_SCALE = 1000.0 #천원/kWh -> 원/kWh로 단위 변환

    #이동비용(수소 연비), 배터리 열화비용
    TRUCK_FUEL_EFFICIENCY = 0.08  # kg/km (수소 트럭 연비)
    DISTANCE_ONE_WAY = 1.7  # km (편도 거리)
    MOVE_H2_COST = TRUCK_FUEL_EFFICIENCY * DISTANCE_ONE_WAY  # 1회 이동 소모량 (kg)
    BATTERY_WEAR_COST = 50.0  # 원/kWh (예시: kWh당 열화 비용 설정 필요)


# ---------------------------------------------------------
# 2. HB-MPS Agent Class
# ---------------------------------------------------------
class H_MEP_Truck:
    def __init__(self, config):
        self.cfg = config
        self.ess_kwh = config.ESS_CAPACITY * config.INIT_ESS_SOC
        self.h2_kg = config.MAX_H2_KG * config.INIT_HFC_LOH
        self.history = []

    def get_soc(self):
        return self.ess_kwh / self.cfg.ESS_CAPACITY

    def get_loh(self):
        return self.h2_kg / self.cfg.MAX_H2_KG

    #정전피해비용 단가 계산 함수
    def calculate_voll_unit_cost(self, duration_minutes):
        # VOLL = e^(a*t^2 + b*t + c)
        exponent = (self.cfg.VOLL_A * (duration_minutes ** 2) +
                    self.cfg.VOLL_B * duration_minutes +
                    self.cfg.VOLL_C)
        # 결과값은 단위 전력당 피해비용 (예: 천원/kW 또는 만원/kW 등 데이터 출처 단위 따름)
        return np.exp(exponent) * self.cfg.VOLL_UNIT_SCALE

    def run_step(self, timestamp, load_a, load_b, LCOE, SMP, solar, h2_cost, b_load_mean, LCOE_high_threshold,
                 SMP_low_threshold):
        mode = "STANDBY"
        action = "WAIT"
        power_output = 0.0
        revenue = 0.0
        op_cost = 0.0
        n_trucks = 1  # 기본 1대

        # 1. Base Case Penalty Calculation (VOLL 적용)
        spike_threshold = b_load_mean * self.cfg.PHASE2_MULTIPLIER
        excess_load_base = max(0, load_b - spike_threshold)  # Base Case의 정전 규모

        # VOLL 단가 계산 (60분 기준)
        voll_unit_price = 0.0
        if excess_load_base > 0:
            voll_unit_price = self.calculate_voll_unit_cost(self.cfg.SIMULATION_STEP_MIN)

        # Base Case 총 정전비용
        base_penalty_cost = excess_load_base * voll_unit_price

        # HB-MPS Penalty 초기값 (방어 성공 시 0원이 됨)
        hmep_penalty_cost = base_penalty_cost
        excess_load_hmep = excess_load_base

        surplus_solar = solar - (load_a + load_b)

        # -------------------------------------------------------
        # Priority 1: Emergency Response (Phase 2 with Multi-Trucks)
        # -------------------------------------------------------
        if load_b >= spike_threshold:
            mode = "PHASE 2"
            required_power = excess_load_base

            # 필요한 트럭 수 계산 (올림 처리)
            # 1대당 500kW 커버 가능
            import math
            n_trucks = math.ceil(required_power / self.cfg.HFC_RATED_OUTPUT)

            # 공급량 = 필요량 (다수의 트럭이 커버하므로)
            discharge_kwh = required_power

            if discharge_kwh > 0:
                action = f"HFC_DISCHARGE ({n_trucks} Trucks)"
                # 수소 소모량 계산
                total_h2_consumed = discharge_kwh / self.cfg.KWH_PER_KG_H2

                # 비용 계산 로직
                # 1번 트럭(Main): 내 탱크에 있는거 씀 (이미 산 것). 부족하면 삼.
                # 2~N번 트럭(Aux): 오면서 샀거나 충전된거 가져옴 -> 즉시 운영비용(Op_Cost) 처리.

                # 1번 트럭 분담량
                truck1_capacity = min(discharge_kwh, self.cfg.HFC_RATED_OUTPUT)
                truck1_h2_need = truck1_capacity / self.cfg.KWH_PER_KG_H2

                # 이동 연료 소모량 (편도)
                move_h2_need = self.cfg.MOVE_H2_COST

                # Main 트럭이 필요한 총 수소 = 발전용 + 이동용
                total_main_consumption = truck1_h2_need + move_h2_need

                # 보유량 체크 및 차감
                if self.h2_kg >= total_main_consumption:
                    self.h2_kg -= total_main_consumption  # 보유량에서 전량 차감
                else:
                    # 부족하면 부족한 만큼 구매 (OpEx 처리)
                    shortage = total_main_consumption - self.h2_kg
                    self.h2_kg = 0
                    op_cost += shortage * h2_cost

                # 추가 트럭(N-1) 분담량 처리 (전량 비용 처리)
                if n_trucks > 1:
                    # 추가 트럭들의 발전 연료
                    aux_h2_need = total_h2_consumed - truck1_h2_need
                    # 추가 트럭들의 이동 연료 ( (N-1)대 * 대당 이동비용 )
                    aux_move_need = (n_trucks - 1) * self.cfg.MOVE_H2_COST

                    # 추가 트럭 비용 합산
                    op_cost += (aux_h2_need + aux_move_need) * h2_cost

                # [결과] HB-MPS은 정전을 완벽히 막았으므로 Penalty는 0원
                hmep_penalty_cost = 0.0
                excess_load_hmep = 0.0


        # -------------------------------------------------------
        # Priority 2: External Refueling (Main Truck Maintenance)
        # -------------------------------------------------------
        elif (self.get_loh() < self.cfg.H2_REFUEL_THRESHOLD):
            mode = "H2_MAINTENANCE"
            action = "BUY_EXTERNAL_H2"
            target_kg = self.cfg.MAX_H2_KG * self.cfg.H2_TARGET_LEVEL
            needed_kg = target_kg - self.h2_kg
            if needed_kg > 0:
                self.h2_kg += needed_kg
                op_cost += needed_kg * h2_cost  # 수소 구매 비용 추가

        # -------------------------------------------------------
        # Priority 3: Arbitrage (Phase 1) - Only Main Truck
        # -------------------------------------------------------
        elif (LCOE >= LCOE_high_threshold) and (self.get_soc() >= self.cfg.PHASE1_SOC_LIMIT):
            mode = "PHASE 1"
            discharge_cap = 700.0
            energy_avail = self.ess_kwh - (self.cfg.ESS_CAPACITY * self.cfg.ESS_MIN_SOC)
            discharge_kwh = min(discharge_cap, energy_avail)
            #이동 연료 소모
            self.h2_kg -= self.cfg.MOVE_H2_COST
            # (만약 수소 부족하면 op_cost에 추가하는 로직 혹은 LOH 체크 필요)
            op_cost += self.cfg.MOVE_H2_COST * h2_cost  # 편의상 비용으로 바로 환산

            if discharge_kwh > 0:
                action = "ESS_DISCHARGE"
                self.ess_kwh -= discharge_kwh
                power_output = discharge_kwh * self.cfg.ESS_EFFICIENCY
                revenue = power_output * LCOE
                deg_cost = discharge_kwh * self.cfg.BATTERY_WEAR_COST
                op_cost += deg_cost  # 운영 비용에 열화 비용 추가

        # -------------------------------------------------------
        # Priority 4: Active Charging & P2G
        # -------------------------------------------------------
        else:
            # 4-1. Solar Charge
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

            # 4-2. Grid Charge (SMP)
            elif (SMP <= SMP_low_threshold) and (self.get_soc() < 0.9):
                charge_cap = 300.0
                space = (self.cfg.ESS_CAPACITY * 0.9) - self.ess_kwh
                charge_kwh = min(charge_cap, space)

                if charge_kwh > 0.1:
                    mode = "GRID_CHARGE"
                    action = "GRID_BUY"
                    self.ess_kwh += charge_kwh * self.cfg.ESS_EFFICIENCY
                    op_cost += (charge_kwh * SMP) + (charge_kwh * self.cfg.BATTERY_WEAR_COST)

        # [수정] Penalty Calculation with VOLL
        # HB-MPS Penalty (방어하고도 남은게 있다면 VOLL 적용)
        hmep_penalty_cost = excess_load_hmep * voll_unit_price

        # Record Data
        self.history.append({
            'timestamp': timestamp,
            'Load_B': load_b,
            'LCOE': LCOE,
            'SMP': SMP,
            'Mode': mode,
            'Action': action,
            'ESS_SOC': self.get_soc() * 100,
            'H2_LOH': self.get_loh() * 100,
            'Revenue': revenue,
            'Op_Cost': op_cost,
            'Net_Step_Profit': revenue - op_cost,
            'Base_Penalty': base_penalty_cost,  # Base Case의 거대한 정전 비용
            'HMEP_Penalty': hmep_penalty_cost,  # HB-MPS의 정전 비용 (Phase 2 발동 시 0원)
            'Avoided_Penalty': base_penalty_cost - hmep_penalty_cost,  # HB-MPS이 아낀 돈
            'Active_Trucks': n_trucks
        })


# ---------------------------------------------------------
# 3. Execution (Visualization Logic)
# ---------------------------------------------------------
def run_final_simulation():
    try:
        df = pd.read_csv(Config.FILE_PATH)
    except FileNotFoundError:
        print("Data file not found.")
        return

    col_map = {
        '주택용 전력사용량(kWh)': 'load_A', '산업용 전력사용량(kWh)': 'load_B',
        'LCOE=SMP+REC(원/kWh)': 'LCOE', 'E: 태양광 발전량(kWh)': 'solar', 'SMP(원/kWh)': 'SMP',
        '수소 외부계통 충전 비용(원/kg)': 'h2_cost',
        '날짜': 'date', '시간': 'hour'
    }
    df = df.rename(columns=col_map)

    # Preprocessing
    df['date'] = pd.to_numeric(df['date'], errors='coerce')
    df['hour'] = pd.to_numeric(df['hour'], errors='coerce')
    df = df.dropna(subset=['date', 'hour'])

    try:
        base_dates = pd.to_datetime(df['date'].astype(int).astype(str), format='%Y%m%d', errors='coerce')
        time_deltas = pd.to_timedelta(df['hour'] - 1, unit='h')
        df['timestamp_dt'] = base_dates + time_deltas
        df = df.dropna(subset=['timestamp_dt'])
        df = df.sort_values('timestamp_dt')
    except Exception as e:
        print(f"Datetime conversion error: {e}")
        return

    # Fill NaNs
    for c in ['load_A', 'load_B', 'LCOE', 'SMP', 'solar', 'h2_cost']:
        if c not in df.columns:
            df[c] = 0.0
        else:
            df[c] = df[c].fillna(0.0)

    # Thresholds
    b_load_mean = df['load_B'].mean()
    LCOE_high_threshold = df['LCOE'].quantile(Config.PHASE1_LCOE_PERCENTILE)
    SMP_low_threshold = df['SMP'].quantile(Config.CHARGE_SMP_PERCENTILE)

    print(f"--- Thresholds ---")
    print(f"Phase 1 Sell Trigger (LCOE Top 40%): {LCOE_high_threshold:.2f}")
    print(f"Grid Charge Trigger (SMP Bottom 25%): {SMP_low_threshold:.2f}")

    truck = H_MEP_Truck(Config)

    print(f"--- Simulation Start ---")

    for idx, row in df.iterrows():
        truck.run_step(
            timestamp=row['timestamp_dt'],
            load_a=row['load_A'],
            load_b=row['load_B'],
            LCOE=row['LCOE'],
            SMP=row['SMP'],
            solar=row['solar'],
            h2_cost=row['h2_cost'],
            b_load_mean=b_load_mean,
            LCOE_high_threshold=LCOE_high_threshold,
            SMP_low_threshold=SMP_low_threshold
        )

    res = pd.DataFrame(truck.history)

    # 결과 요약 로그 출력 (Console Log)
    max_trucks = res['Active_Trucks'].max()
    phase2_count = res[res['Mode'] == 'PHASE 2'].shape[0]
    avg_trucks_p2 = res[res['Mode'] == 'PHASE 2']['Active_Trucks'].mean() if phase2_count > 0 else 0

    print("\n" + "=" * 40)
    print(f"  [Simulation Result Summary]")
    print(f"  - Maximum Trucks Deployed: {max_trucks} 대")
    print(f"  - Phase 2 Activation: {phase2_count} 회")
    print(f"  - Avg Trucks per Phase 2: {avg_trucks_p2:.1f} 대")
    print("=" * 40 + "\n")

    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import MaxNLocator

    # ==========================================
    # 1. 그래프 그리기 함수 정의 (로직 분리)
    # ==========================================

    def draw_grid_resilience(ax, res, b_load_mean, config_phase2_multiplier, max_trucks):
        """1. Grid Resilience & Fleet Deployment 그래프 그리기"""
        # 왼쪽 축: 부하 (Load)
        ax.plot(res['timestamp'], res['Load_B'], color='gray', alpha=0.4, label='Industrial Load (kW)')
        ax.axhline(b_load_mean * config_phase2_multiplier, color='red', linestyle='--', label='Phase 2 Trigger')
        ax.set_ylabel('Load (kW)', fontsize=10)

        # Phase 2 발생 지점 빨간 점
        p2_mask = res['Mode'] == 'PHASE 2'
        if p2_mask.any():
            ax.scatter(res[p2_mask]['timestamp'], res[p2_mask]['Load_B'], color='red', s=30, zorder=5,
                       label='Phase 2 Active')

        # 오른쪽 축: 추가 트럭 대수
        ax_right = ax.twinx()
        additional_mask = (res['Mode'] == 'PHASE 2') & (res['Active_Trucks'] > 1)
        additional_indices = res[additional_mask].index

        if not additional_indices.empty:
            x_vals = res.loc[additional_indices, 'timestamp']
            y_vals = res.loc[additional_indices, 'Active_Trucks'] - 1
            ax_right.bar(x_vals, y_vals, width=0.04, color='royalblue', alpha=0.6, label='Additional Trucks (Backup)')

        ax_right.set_ylabel('Number of Additional Trucks', color='royalblue', fontsize=10)
        ax_right.tick_params(axis='y', labelcolor='royalblue')

        max_additional = max(0, max_trucks - 1)
        ax_right.set_ylim(0, max_additional + 1.5)
        ax_right.yaxis.set_major_locator(MaxNLocator(integer=True))

        ax.set_title("1. Grid Resilience & HB-MPS Fleet Deployment", fontsize=12, fontweight='bold')

        # 범례 합치기
        lines_1, labels_1 = ax.get_legend_handles_labels()
        lines_2, labels_2 = ax_right.get_legend_handles_labels()
        ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H'))

    def draw_asset_status(ax, res):
        """2. Asset Status 그래프 그리기"""
        ax.plot(res['timestamp'], res['ESS_SOC'], label='Battery SOC (%)', color='green')
        ax.plot(res['timestamp'], res['H2_LOH'], label='Hydrogen LOH (%)', color='orange')

        buy_mask = res['Action'] == "BUY_EXTERNAL_H2"
        if buy_mask.any():
            ax.scatter(res[buy_mask]['timestamp'], res[buy_mask]['H2_LOH'], color='blue', marker='^', s=60,
                       label='External Buy (Refill)')

        grid_mask = res['Mode'] == 'GRID_CHARGE'
        if grid_mask.any():
            ax.scatter(res[grid_mask]['timestamp'], res[grid_mask]['ESS_SOC'], color='mediumseagreen', s=15,
                       label='Grid Charge')

        ax.set_title("2. Asset Status(Main truck)", fontsize=12, fontweight='bold')
        ax.legend(loc='lower left')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    def draw_financial_flow(ax, res):
        """3. Financial Flow 그래프 그리기"""
        cum_profit = res['Net_Step_Profit'].cumsum()
        ax.plot(res['timestamp'], res['Revenue'].cumsum(), label='Revenue', color='gold')
        ax.plot(res['timestamp'], -res['Op_Cost'].cumsum(), label='Total Op Cost (H2+Grid)', color='red',
                linestyle='--')
        ax.plot(res['timestamp'], cum_profit, label='Net Profit', color='blue', linewidth=2)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_title("3. Financial Flow", fontsize=12, fontweight='bold')
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    def draw_economic_value(ax, res):
        """4. Total Economic Value 그래프 그리기"""
        total_base_penalty = res['Base_Penalty'].sum()
        total_avoided = res['Avoided_Penalty'].sum()
        total_profit = res['Net_Step_Profit'].sum()
        hmep_value = - (total_base_penalty - total_avoided) + total_profit
        values = [-total_base_penalty, hmep_value]

        bars = ax.bar(['Base Case\n(Risk Cost)', 'HB-MPS\n(Net Value)'], values, color=['gray', 'royalblue'], width=0.5)
        ax.axhline(0, color='black')
        ax.set_title("4. Total Economic Value", fontsize=12, fontweight='bold')

        for rect in bars:
            height = rect.get_height()
            ax.text(rect.get_x() + rect.get_width() / 2., height, f'{int(height):,}', ha='center',
                    va='bottom' if height > 0 else 'top')

    def draw_mode_distribution(ax, res):
        """5. Operational Mode Distribution 그래프 그리기"""
        mode_counts = res['Mode'].value_counts()
        colors = {
            'STANDBY': 'lightgray',
            'PHASE 1': 'gold',
            'PHASE 2': 'red',
            'SOLAR_CHARGE': 'cyan',
            'GRID_CHARGE': 'mediumseagreen',
            'H2_MAINTENANCE': 'orange'
        }
        pie_colors = []
        for m in mode_counts.index:
            c = 'gray'
            for k, v in colors.items():
                if k in m: c = v
            pie_colors.append(c)

        ax.pie(mode_counts, labels=mode_counts.index, autopct='%1.1f%%', colors=pie_colors, startangle=90)
        ax.set_title("5. Operational Mode Distribution", fontsize=12, fontweight='bold')

    # ==========================================
    # 2. 통합 대시보드 그리기 (기존 방식)
    # ==========================================
    fig = plt.figure(figsize=(15, 12))
    gs = fig.add_gridspec(3, 2)

    # Subplots 생성
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])
    ax4 = fig.add_subplot(gs[2, 0])
    ax5 = fig.add_subplot(gs[2, 1])

    # 함수 호출하여 그래프 그리기
    draw_grid_resilience(ax1, res, b_load_mean, Config.PHASE2_MULTIPLIER, max_trucks)
    draw_asset_status(ax2, res)
    draw_financial_flow(ax3, res)
    draw_economic_value(ax4, res)
    draw_mode_distribution(ax5, res)

    plt.tight_layout()
    plt.show()  # 통합 그래프 출력

    # ==========================================
    # 3. 개별 그래프 따로 띄우기 (새로운 창)
    # ==========================================
    # 논문용 고해상도 설정을 위해 dpi 추가 (보통 300dpi 권장)
    PAPER_DPI = 300
    # 3-1. Grid Resilience (시계열은 가로로 아주 길어야 함)
    # 변경: (10, 6) -> (12, 3.5)
    fig1, ax_single1 = plt.subplots(figsize=(12, 3.5), dpi=PAPER_DPI)
    draw_grid_resilience(ax_single1, res, b_load_mean, Config.PHASE2_MULTIPLIER, max_trucks)
    plt.tight_layout()
    plt.show()

    # 3-2. Asset Status (SOC/LOH 그래프도 가로로 길어야 겹치지 않음)
    # 변경: (8, 5) -> (10, 3.5)
    fig2, ax_single2 = plt.subplots(figsize=(10, 3.5), dpi=PAPER_DPI)
    draw_asset_status(ax_single2, res)
    plt.tight_layout()
    plt.show()

    # 3-3. Financial Flow (수익 그래프)
    # 변경: (8, 5) -> (10, 3.5)
    fig3, ax_single3 = plt.subplots(figsize=(10, 3.5), dpi=PAPER_DPI)
    draw_financial_flow(ax_single3, res)
    plt.tight_layout()
    plt.show()

    # 3-4. Economic Value (막대 그래프는 너무 길 필요는 없지만 납작하게)
    # 변경: (6, 5) -> (8, 3.0)
    # 높이를 3.0으로 확 줄여서 컴팩트하게 만듦
    fig4, ax_single4 = plt.subplots(figsize=(8, 3.0), dpi=PAPER_DPI)
    draw_economic_value(ax_single4, res)
    plt.tight_layout()
    plt.show()

    # 3-5. Mode Distribution (파이 차트)
    # 변경: (6, 5) -> (7, 4.0)
    # 파이 차트는 원형이라 너무 납작하면 여백이 생기므로 적당히 조절
    fig5, ax_single5 = plt.subplots(figsize=(7, 4.0), dpi=PAPER_DPI)
    draw_mode_distribution(ax_single5, res)
    plt.tight_layout()
    plt.show()



if __name__ == "__main__":
    run_final_simulation()