"""Case-configurable copy of the existing sequential AC/HFC-first dispatch."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandapower as pp

from powerflow_validation import MIN_VOLTAGE_PU, solve_network
from severity_fleet import (
    FLEET_SIZE,
    TRAVEL_H2_KG,
    FleetState,
    ess_capacity_kwh,
    hfc_capacity_kwh,
    supply_ess,
    supply_hfc,
)

DISPATCH_TOLERANCE_MW = 1e-8


@dataclass(frozen=True, slots=True)
class TruckDispatch:
    truck: int
    bus: int | None
    hfc_kwh: float
    ess_kwh: float
    h2_before_kg: float
    h2_after_kg: float


@dataclass(frozen=True, slots=True)
class HourDispatch:
    supported_voltage: np.ndarray
    supported_loss_mw: float
    injections_mw: np.ndarray
    remaining_excess_mw: np.ndarray
    initial_severity: np.ndarray
    trucks: tuple[TruckDispatch, ...]
    hfc_kwh: float
    ess_kwh: float
    ess_withdrawal_kwh: float
    h2_consumed_kg: float
    load_response_mw: float


def severity_scores(
    demand_mw: np.ndarray, voltage: np.ndarray, bus_numbers: tuple[int, ...]
) -> np.ndarray:
    """Normalize industrial-bus excess and 0.95 p.u. deficits separately."""
    demand_peak = float(demand_mw.max())
    demand_term = (
        demand_mw / demand_peak if demand_peak > 0 else np.zeros_like(demand_mw)
    )
    local_deficit = np.where(
        demand_mw > DISPATCH_TOLERANCE_MW,
        np.maximum(MIN_VOLTAGE_PU - voltage[np.array(bus_numbers) - 1], 0.0),
        0.0,
    )
    deficit_peak = float(local_deficit.max())
    voltage_term = (
        local_deficit / deficit_peak if deficit_peak > 0 else np.zeros_like(demand_mw)
    )
    return 0.5 * demand_term + 0.5 * voltage_term


def dispatch_hour(
    net: pp.pandapowerNet,
    baseline_voltage: np.ndarray,
    local_excess_mw: np.ndarray,
    generator_indices: np.ndarray,
    state: FleetState,
    mw_per_raw_kwh: float,
    bus_numbers: tuple[int, ...],
) -> HourDispatch:
    """Choose up to five buses sequentially and re-solve AC after each supply."""
    if len(local_excess_mw) != len(generator_indices) or len(local_excess_mw) != len(bus_numbers):
        raise ValueError("Industrial demand, generators and buses must align")
    current_voltage = baseline_voltage.copy()
    remaining = local_excess_mw.copy()
    injections = np.zeros(len(bus_numbers), dtype=float)
    initial_severity = severity_scores(remaining, current_voltage, bus_numbers)
    h2_before = tuple(state.h2_kg)
    truck_buses: list[int | None] = [None] * FLEET_SIZE
    truck_hfc = [0.0] * FLEET_SIZE
    truck_ess = [0.0] * FLEET_SIZE
    h2_consumed = 0.0
    load_response_mw = 0.0

    def choose_bus() -> int:
        scores = severity_scores(remaining, current_voltage, bus_numbers)
        return min(
            range(len(scores)),
            key=lambda index: (-scores[index], bus_numbers[index]),
        )

    main_choice = choose_bus()
    for truck in range(FLEET_SIZE):
        if not np.any(remaining > DISPATCH_TOLERANCE_MW):
            break
        capacity_kwh = hfc_capacity_kwh(state, truck)
        if capacity_kwh <= 1e-9:
            continue
        chosen = main_choice if truck == 0 else choose_bus()
        output_mw = min(float(remaining[chosen]), capacity_kwh * mw_per_raw_kwh)
        if output_mw <= DISPATCH_TOLERANCE_MW:
            continue
        output_kwh = output_mw / mw_per_raw_kwh
        h2_consumed += supply_hfc(state, truck, output_kwh)
        truck_buses[truck] = bus_numbers[chosen]
        truck_hfc[truck] = output_kwh
        load_response_mw += output_mw
        remaining[chosen] = max(0.0, remaining[chosen] - output_mw)
        injections[chosen] += output_mw
        net.sgen.at[int(generator_indices[chosen]), "p_mw"] += output_mw
        current_voltage, _ = solve_network(net)

    ess_withdrawal = 0.0
    if np.any(remaining > DISPATCH_TOLERANCE_MW):
        capacity_kwh = ess_capacity_kwh(state)
        # An ESS-only main deployment still needs the original travel allowance.
        can_travel = truck_buses[0] is not None or state.h2_kg[0] >= TRAVEL_H2_KG
        if capacity_kwh > 1e-9 and can_travel:
            chosen = main_choice
            output_mw = min(float(remaining[chosen]), capacity_kwh * mw_per_raw_kwh)
            if output_mw > DISPATCH_TOLERANCE_MW:
                delivered_kwh = output_mw / mw_per_raw_kwh
                ess_withdrawal = supply_ess(state, delivered_kwh)
                if truck_buses[0] is None:
                    state.h2_kg[0] -= TRAVEL_H2_KG
                    h2_consumed += TRAVEL_H2_KG
                    truck_buses[0] = bus_numbers[chosen]
                truck_ess[0] = delivered_kwh
                load_response_mw += output_mw
                remaining[chosen] = max(0.0, remaining[chosen] - output_mw)
                injections[chosen] += output_mw
                net.sgen.at[int(generator_indices[chosen]), "p_mw"] += output_mw
                current_voltage, _ = solve_network(net)

    supported_voltage, supported_loss = solve_network(net)
    trucks = tuple(
        TruckDispatch(
            truck=index,
            bus=truck_buses[index],
            hfc_kwh=truck_hfc[index],
            ess_kwh=truck_ess[index],
            h2_before_kg=h2_before[index],
            h2_after_kg=state.h2_kg[index],
        )
        for index in range(FLEET_SIZE)
    )
    if not np.isclose(
        injections.sum(), (sum(truck_hfc) + sum(truck_ess)) * mw_per_raw_kwh
    ):
        raise AssertionError("AC injection and fleet output do not balance")
    return HourDispatch(
        supported_voltage=supported_voltage,
        supported_loss_mw=supported_loss,
        injections_mw=injections,
        remaining_excess_mw=remaining,
        initial_severity=initial_severity,
        trucks=trucks,
        hfc_kwh=sum(truck_hfc),
        ess_kwh=sum(truck_ess),
        ess_withdrawal_kwh=ess_withdrawal,
        h2_consumed_kg=h2_consumed,
        load_response_mw=load_response_mw,
    )
