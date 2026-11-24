"""Independent five-vehicle P1-style inventory for dynamic AC dispatch.

The main operational simulation remains untouched. These transitions retain
its ratings, efficiencies, fuel use, refill order, and nonemergency Mode 1 rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from emergency_dispatch import (
    ESS_CAPACITY,
    ESS_CHARGE_KWH,
    ESS_EFFICIENCY,
    ESS_INITIAL_SOC,
    ESS_MAX_SOC,
    ESS_MIN_SOC,
    ESS_WEAR_KRW_PER_KWH,
    ESS_WITHDRAWAL_KWH,
    H2_CAPACITY_KG,
    H2_INITIAL_LOH,
    H2_KWH_PER_KG,
    H2_REFUEL_LOH,
    H2_TARGET_LOH,
    HFC_OUTPUT_KWH,
    P2G_KWH_PER_KG,
    TRAVEL_H2_KG,
)
from hb_inputs import Hour

FLEET_SIZE = 5


@dataclass(slots=True)
class FleetState:
    """Mutable hourly inventories for the separate dynamic experiment."""

    ess_kwh: float
    h2_kg: list[float]

    @classmethod
    def initial(cls) -> FleetState:
        return cls(
            ESS_INITIAL_SOC * ESS_CAPACITY,
            [H2_INITIAL_LOH * H2_CAPACITY_KG] * FLEET_SIZE,
        )

    @property
    def soc(self) -> float:
        return self.ess_kwh / ESS_CAPACITY


@dataclass(frozen=True, slots=True)
class IdleOutcome:
    phase1_ess_kwh: float = 0.0
    pv_ess_charge_kwh: float = 0.0
    grid_ess_charge_kwh: float = 0.0
    pv_p2g_kwh: float = 0.0
    external_h2_kg: float = 0.0
    travel_h2_kg: float = 0.0
    ess_wear_krw: float = 0.0


def hfc_capacity_kwh(state: FleetState, truck: int) -> float:
    """Available electrical energy after one fixed service-area trip."""
    return min(
        HFC_OUTPUT_KWH,
        max(0.0, state.h2_kg[truck] - TRAVEL_H2_KG) * H2_KWH_PER_KG,
    )


def supply_hfc(state: FleetState, truck: int, output_kwh: float) -> float:
    """Commit one HFC output and return hydrogen consumed, including travel."""
    if output_kwh < 0 or output_kwh > hfc_capacity_kwh(state, truck) + 1e-8:
        raise AssertionError("HFC output exceeds rating or available hydrogen")
    if output_kwh <= 1e-9:
        return 0.0
    consumed = output_kwh / H2_KWH_PER_KG + TRAVEL_H2_KG
    state.h2_kg[truck] -= consumed
    return consumed


def ess_capacity_kwh(state: FleetState) -> float:
    """Deliverable emergency ESS energy above the existing minimum SOC."""
    withdrawal = min(
        ESS_WITHDRAWAL_KWH,
        max(state.ess_kwh - ESS_MIN_SOC * ESS_CAPACITY, 0.0),
    )
    return withdrawal * ESS_EFFICIENCY


def supply_ess(state: FleetState, delivered_kwh: float) -> float:
    """Commit backup ESS delivery and return withdrawn battery energy."""
    if delivered_kwh < 0 or delivered_kwh > ess_capacity_kwh(state) + 1e-8:
        raise AssertionError("ESS output exceeds rating or reserve")
    withdrawal = delivered_kwh / ESS_EFFICIENCY
    state.ess_kwh -= withdrawal
    return withdrawal


def advance_idle(
    state: FleetState,
    hour: Hour,
    high_lcoe: float,
    low_smp: float,
    phase1_soc_gate: float = 0.3,
) -> IdleOutcome:
    """Apply the unchanged P1 refill-before-Mode-1 and charging order."""
    refilled = 0.0
    for truck in range(1, FLEET_SIZE):
        if state.h2_kg[truck] / H2_CAPACITY_KG < H2_REFUEL_LOH:
            purchase = H2_TARGET_LOH * H2_CAPACITY_KG - state.h2_kg[truck]
            state.h2_kg[truck] += purchase
            refilled += purchase
    if state.h2_kg[0] / H2_CAPACITY_KG < H2_REFUEL_LOH:
        purchase = H2_TARGET_LOH * H2_CAPACITY_KG - state.h2_kg[0]
        state.h2_kg[0] += purchase
        return IdleOutcome(external_h2_kg=refilled + purchase)
    if hour.lcoe >= high_lcoe and state.soc >= phase1_soc_gate:
        withdrawal = min(
            ESS_WITHDRAWAL_KWH,
            max(state.ess_kwh - ESS_MIN_SOC * ESS_CAPACITY, 0.0),
        )
        if withdrawal > 0 and state.h2_kg[0] >= TRAVEL_H2_KG:
            state.ess_kwh -= withdrawal
            state.h2_kg[0] -= TRAVEL_H2_KG
            return IdleOutcome(
                phase1_ess_kwh=withdrawal * ESS_EFFICIENCY,
                external_h2_kg=refilled,
                travel_h2_kg=TRAVEL_H2_KG,
                ess_wear_krw=withdrawal * ESS_WEAR_KRW_PER_KWH,
            )
        return IdleOutcome(external_h2_kg=refilled)
    surplus = max(hour.solar - hour.residential - hour.industrial, 0.0)
    if surplus > 0:
        charge = min(
            surplus,
            ESS_CHARGE_KWH,
            max(ESS_MAX_SOC * ESS_CAPACITY - state.ess_kwh, 0.0),
        )
        state.ess_kwh += charge * ESS_EFFICIENCY
        remainder = surplus - charge
        p2g = min(
            remainder,
            max(H2_CAPACITY_KG - state.h2_kg[0], 0.0) * P2G_KWH_PER_KG,
        )
        state.h2_kg[0] += p2g / P2G_KWH_PER_KG
        return IdleOutcome(
            pv_ess_charge_kwh=charge,
            pv_p2g_kwh=p2g,
            external_h2_kg=refilled,
            ess_wear_krw=charge * ESS_WEAR_KRW_PER_KWH,
        )
    if hour.smp <= low_smp:
        charge = min(
            ESS_CHARGE_KWH,
            max(ESS_MAX_SOC * ESS_CAPACITY - state.ess_kwh, 0.0),
        )
        if charge > 0.1:
            state.ess_kwh += charge * ESS_EFFICIENCY
            return IdleOutcome(
                grid_ess_charge_kwh=charge,
                external_h2_kg=refilled,
                ess_wear_krw=charge * ESS_WEAR_KRW_PER_KWH,
            )
    return IdleOutcome(external_h2_kg=refilled)


def price_quantiles(hours: list[Hour]) -> tuple[float, float]:
    """Use the same fixed nonemergency Mode-1 price gates as P1."""
    return (
        float(np.quantile([hour.lcoe for hour in hours], 0.6)),
        float(np.quantile([hour.smp for hour in hours], 0.25)),
    )
