"""Finite-truck rule-based emergency dispatch without modifying the paper model.

Run with ``uv run --with numpy --with matplotlib emergency_dispatch_experiment.py``.
Hydrogen is expensed when externally replenished, never again when consumed.
"""

from __future__ import annotations

import math
from typing import Final, assert_never

import numpy as np

from emergency_dispatch_model import Run, Scenario, State, Step, Strategy
from hb_inputs import Hour

ESS_CAPACITY: Final = 1500.0
HFC_CAPACITY_KWH: Final = 1500.0
HFC_OUTPUT_KWH: Final = 500.0
ESS_WITHDRAWAL_KWH: Final = 700.0
ESS_CHARGE_KWH: Final = 300.0
ESS_EFFICIENCY: Final = 0.95
ESS_MIN_SOC: Final = 0.1
ESS_MAX_SOC: Final = 0.9
ESS_INITIAL_SOC: Final = 0.4
H2_INITIAL_LOH: Final = 0.8
H2_REFUEL_LOH: Final = 0.6
H2_TARGET_LOH: Final = 0.9
H2_KWH_PER_KG: Final = 16.65
P2G_KWH_PER_KG: Final = 55.0
TRAVEL_H2_KG: Final = 0.08 * 1.7
ESS_WEAR_KRW_PER_KWH: Final = 50.0
PHASE1_SOC_GATE: Final = 0.3
VOLL_KRW_PER_KWH: Final = (
    math.exp(-0.0000206 * 60**2 + 0.0227011 * 60 + 0.3018905) * 1000
)
H2_CAPACITY_KG: Final = HFC_CAPACITY_KWH / H2_KWH_PER_KG


def run_scenario(hours: list[Hour], scenario: Scenario) -> Run:
    """Simulate one path with identical input, initial state, and Mode 1 rules."""
    threshold = scenario.alpha * float(np.mean([hour.industrial for hour in hours]))
    high_lcoe = float(
        np.quantile([hour.lcoe for hour in hours], scenario.phase1_lcoe_quantile)
    )
    low_smp = float(np.quantile([hour.smp for hour in hours], 0.25))
    ess_capacity = scenario.ess_capacity_kwh
    h2_capacity = scenario.hfc_capacity_kwh / H2_KWH_PER_KG
    state = State(
        ESS_INITIAL_SOC * ess_capacity,
        [H2_INITIAL_LOH * h2_capacity] * scenario.trucks,
    )
    steps: list[Step] = []

    for hour in hours:
        soc_start = state.ess_kwh / ess_capacity if ess_capacity else 0.0
        h2_start = sum(state.h2_kg)
        demand = max(hour.industrial - threshold, 0.0)
        required_trucks = math.ceil(demand / HFC_OUTPUT_KWH) if demand > 0 else 0
        mode2 = hour.industrial >= threshold
        hfc = ess_emergency = phase1 = pv_charge = grid_charge = p2g = 0.0
        refilled = consumed = revenue = h2_cost = grid_cost = wear = 0.0
        main_refilled = 0.0
        dispatched = 0

        if mode2:
            remaining = demand
            for index, inventory in enumerate(state.h2_kg):
                if remaining <= 0 or inventory <= TRAVEL_H2_KG:
                    continue
                output = min(
                    remaining,
                    HFC_OUTPUT_KWH,
                    (inventory - TRAVEL_H2_KG) * H2_KWH_PER_KG,
                )
                if output <= 0:
                    continue
                fuel = output / H2_KWH_PER_KG + TRAVEL_H2_KG
                state.h2_kg[index] -= fuel
                consumed += fuel
                dispatched += 1
                hfc += output
                remaining -= output

            match scenario.strategy:
                case Strategy.P0:
                    emergency_floor = None
                case Strategy.P1:
                    emergency_floor = ESS_MIN_SOC
                case Strategy.P2:
                    emergency_floor = max(ESS_MIN_SOC, scenario.reserve_soc or 0.0)
                case unreachable:
                    assert_never(unreachable)
            if remaining > 0 and emergency_floor is not None:
                withdrawal = min(
                    ESS_WITHDRAWAL_KWH,
                    max(state.ess_kwh - emergency_floor * ess_capacity, 0.0),
                    remaining / ESS_EFFICIENCY,
                )
                state.ess_kwh -= withdrawal
                ess_emergency = withdrawal * ESS_EFFICIENCY
                wear += withdrawal * ESS_WEAR_KRW_PER_KWH
                if withdrawal > 0 and h2_capacity == 0:
                    refilled += TRAVEL_H2_KG
                    consumed += TRAVEL_H2_KG
                    h2_cost += TRAVEL_H2_KG * hour.h2_price
        else:
            # Auxiliary HFC vehicles refill independently; the main vehicle
            # retains the original refuel-before-Phase-1 priority.
            for index in range(1, scenario.trucks):
                if h2_capacity > 0 and state.h2_kg[index] / h2_capacity < H2_REFUEL_LOH:
                    purchase = H2_TARGET_LOH * h2_capacity - state.h2_kg[index]
                    state.h2_kg[index] += purchase
                    refilled += purchase
                    h2_cost += purchase * hour.h2_price

            if h2_capacity > 0 and state.h2_kg[0] / h2_capacity < H2_REFUEL_LOH:
                purchase = H2_TARGET_LOH * h2_capacity - state.h2_kg[0]
                state.h2_kg[0] += purchase
                refilled += purchase
                main_refilled += purchase
                h2_cost += purchase * hour.h2_price
            elif (
                ess_capacity > 0
                and hour.lcoe >= high_lcoe
                and soc_start >= scenario.phase1_soc_gate
            ):
                withdrawal = min(
                    ESS_WITHDRAWAL_KWH,
                    max(state.ess_kwh - ESS_MIN_SOC * ess_capacity, 0.0),
                )
                if withdrawal > 0 and (
                    h2_capacity == 0 or state.h2_kg[0] >= TRAVEL_H2_KG
                ):
                    state.ess_kwh -= withdrawal
                    phase1 = withdrawal * ESS_EFFICIENCY
                    revenue += phase1 * hour.lcoe
                    wear += withdrawal * ESS_WEAR_KRW_PER_KWH
                    if h2_capacity > 0:
                        state.h2_kg[0] -= TRAVEL_H2_KG
                    else:
                        refilled += TRAVEL_H2_KG
                        h2_cost += TRAVEL_H2_KG * hour.h2_price
                    consumed += TRAVEL_H2_KG
            else:
                surplus = max(hour.solar - hour.residential - hour.industrial, 0.0)
                if surplus > 0:
                    pv_charge = min(
                        surplus,
                        ESS_CHARGE_KWH,
                        max(ESS_MAX_SOC * ess_capacity - state.ess_kwh, 0.0),
                    )
                    state.ess_kwh += pv_charge * ESS_EFFICIENCY
                    wear += pv_charge * ESS_WEAR_KRW_PER_KWH
                    remainder = surplus - pv_charge
                    p2g = min(
                        remainder,
                        max(h2_capacity - state.h2_kg[0], 0.0) * P2G_KWH_PER_KG,
                    )
                    state.h2_kg[0] += p2g / P2G_KWH_PER_KG
                elif hour.smp <= low_smp:
                    grid_charge = min(
                        ESS_CHARGE_KWH,
                        max(ESS_MAX_SOC * ess_capacity - state.ess_kwh, 0.0),
                    )
                    if grid_charge > 0.1:
                        state.ess_kwh += grid_charge * ESS_EFFICIENCY
                        grid_cost += grid_charge * hour.smp
                        wear += grid_charge * ESS_WEAR_KRW_PER_KWH
                    else:
                        grid_charge = 0.0

        unserved = max(demand - hfc - ess_emergency, 0.0)
        steps.append(
            Step(
                hour.timestamp,
                hour.lcoe,
                hour.smp,
                hour.h2_price,
                mode2,
                demand,
                hfc,
                ess_emergency,
                unserved,
                phase1,
                pv_charge,
                grid_charge,
                p2g,
                refilled,
                consumed,
                main_refilled,
                dispatched,
                required_trucks,
                soc_start,
                state.ess_kwh / ess_capacity if ess_capacity else 0.0,
                h2_start,
                sum(state.h2_kg),
                state.h2_kg[0],
                min(state.h2_kg),
                max(state.h2_kg),
                revenue,
                h2_cost,
                grid_cost,
                wear,
                (hfc + ess_emergency) * VOLL_KRW_PER_KWH,
            )
        )

    initial_h2 = scenario.trucks * H2_INITIAL_LOH * h2_capacity
    # Hold prices fixed at the last hour to isolate quantity left in inventory.
    initial_value = (
        ESS_INITIAL_SOC * ess_capacity * hours[-1].smp + initial_h2 * hours[-1].h2_price
    )
    terminal_value = (
        state.ess_kwh * hours[-1].smp + sum(state.h2_kg) * hours[-1].h2_price
    )
    return Run(
        scenario,
        tuple(steps),
        state.ess_kwh / ess_capacity if ess_capacity else 0.0,
        sum(state.h2_kg),
        terminal_value - initial_value,
        initial_value,
        terminal_value,
    )
