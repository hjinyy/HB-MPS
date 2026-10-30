"""Reconstruct unchanged P1 truck output and assign its AC injection bus.

This module only allocates the already-computed P1 supply. It does not alter
the P1 engine's SOC, LOH, hydrogen purchases, or economic calculation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from emergency_dispatch import (
    H2_CAPACITY_KG,
    H2_INITIAL_LOH,
    H2_KWH_PER_KG,
    H2_REFUEL_LOH,
    H2_TARGET_LOH,
    HFC_OUTPUT_KWH,
    P2G_KWH_PER_KG,
    TRAVEL_H2_KG,
)
from emergency_dispatch_model import Run
from hb_inputs import Hour


@dataclass(frozen=True, slots=True)
class TruckHour:
    alpha: float
    t: int
    truck: int
    bus: int
    hfc_kwh: float
    h2_end_kg: float


@dataclass(frozen=True, slots=True)
class InjectionHour:
    alpha: float
    t: int
    hfc18_kwh: float
    hfc33_kwh: float
    ess18_kwh: float
    total_kwh: float


def allocate_p1_supply(
    hours: list[Hour], run: Run, bus18_industrial_share: float
) -> tuple[tuple[InjectionHour, ...], tuple[TruckHour, ...]]:
    """Replay the original HFC loop, then place whole auxiliary trucks.

    Bus 18 and 33 targets follow their benchmark industrial-load ratings.
    Each active auxiliary truck goes to the node with the larger remaining
    target after main HFC and main ESS at Bus 18. A 10-minute service-area trip
    is represented within the 1-hour bin; no additional trip or fuel is added
    to the unchanged P1 path.
    """
    if not 0 < bus18_industrial_share < 1 or len(hours) != len(run.steps):
        raise ValueError("Invalid node share or misaligned operational hours")
    inventory = [H2_INITIAL_LOH * H2_CAPACITY_KG] * run.scenario.trucks
    truck_buses = [18] * run.scenario.trucks
    injections: list[InjectionHour] = []
    trucks: list[TruckHour] = []

    for t, (hour, step) in enumerate(zip(hours, run.steps, strict=True)):
        outputs = [0.0] * len(inventory)
        refilled = consumed = 0.0
        if step.mode2:
            remaining = step.demand_kwh
            for index, fuel_kg in enumerate(inventory):
                if remaining <= 0 or fuel_kg <= TRAVEL_H2_KG:
                    continue
                output = min(
                    remaining,
                    HFC_OUTPUT_KWH,
                    (fuel_kg - TRAVEL_H2_KG) * H2_KWH_PER_KG,
                )
                if output <= 0:
                    continue
                fuel = output / H2_KWH_PER_KG + TRAVEL_H2_KG
                inventory[index] -= fuel
                outputs[index] = output
                consumed += fuel
                remaining -= output
        else:
            for index in range(1, len(inventory)):
                if inventory[index] / H2_CAPACITY_KG < H2_REFUEL_LOH:
                    purchase = H2_TARGET_LOH * H2_CAPACITY_KG - inventory[index]
                    inventory[index] += purchase
                    refilled += purchase
            if inventory[0] / H2_CAPACITY_KG < H2_REFUEL_LOH:
                purchase = H2_TARGET_LOH * H2_CAPACITY_KG - inventory[0]
                inventory[0] += purchase
                refilled += purchase
            elif step.phase1_ess_kwh > 0:
                inventory[0] -= TRAVEL_H2_KG
                consumed += TRAVEL_H2_KG
            else:
                inventory[0] += step.pv_p2g_kwh / P2G_KWH_PER_KG

        if not math.isclose(sum(outputs), step.hfc_kwh, abs_tol=1e-7):
            raise AssertionError(f"P1 HFC replay differs at t={t}")
        if not math.isclose(refilled, step.external_h2_kg, abs_tol=1e-7):
            raise AssertionError(f"P1 H2 refill differs at t={t}")
        if not math.isclose(consumed, step.consumed_h2_kg, abs_tol=1e-7):
            raise AssertionError(f"P1 H2 consumption differs at t={t}")
        if not math.isclose(sum(inventory), step.h2_end_kg, abs_tol=1e-7):
            raise AssertionError(f"P1 H2 inventory differs at t={t}")
        if not math.isclose(inventory[0], step.main_h2_end_kg, abs_tol=1e-7):
            raise AssertionError(f"P1 main-tank inventory differs at t={t}")
        if sum(output > 0 for output in outputs) != step.hfc_trucks_dispatched:
            raise AssertionError(f"P1 truck count differs at t={t}")

        total = step.hfc_kwh + step.ess_emergency_kwh
        supplied18 = outputs[0] + step.ess_emergency_kwh
        supplied33 = 0.0
        target18 = total * bus18_industrial_share
        target33 = total * (1 - bus18_industrial_share)
        for index, output in enumerate(outputs):
            if index == 0:
                bus = 18
            elif output > 0:
                deficit18 = target18 - supplied18
                deficit33 = target33 - supplied33
                bus = (
                    33
                    if deficit33 > deficit18
                    else 18
                    if deficit18 > deficit33
                    else truck_buses[index]
                )
                if bus == 18:
                    supplied18 += output
                else:
                    supplied33 += output
            else:
                bus = truck_buses[index]
            truck_buses[index] = bus
            trucks.append(
                TruckHour(run.scenario.alpha, t, index, bus, output, inventory[index])
            )
        if not math.isclose(supplied18 + supplied33, total, abs_tol=1e-7):
            raise AssertionError(f"Node supply does not close at t={t}")
        injections.append(
            InjectionHour(
                run.scenario.alpha,
                t,
                supplied18 - step.ess_emergency_kwh,
                supplied33,
                step.ess_emergency_kwh,
                total,
            )
        )
    return tuple(injections), tuple(trucks)
