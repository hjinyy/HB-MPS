"""Typed scenario and result records for the emergency experiment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Strategy(StrEnum):
    """Emergency ESS rule; Mode 1 is shared by every strategy."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


@dataclass(frozen=True, slots=True)
class Scenario:
    alpha: float
    trucks: int
    strategy: Strategy
    reserve_soc: float | None = None

    def __post_init__(self) -> None:
        if self.alpha not in (1.3, 1.5) or self.trucks not in (1, 2, 5):
            raise InvalidScenario(self)
        if self.strategy is Strategy.P2:
            if self.reserve_soc not in (0.2, 0.3, 0.4, 0.5):
                raise InvalidScenario(self)
        elif self.reserve_soc is not None:
            raise InvalidScenario(self)


@dataclass(frozen=True, slots=True)
class InvalidScenario(Exception):
    scenario: Scenario

    def __str__(self) -> str:
        return f"Unsupported emergency scenario: {self.scenario}"


@dataclass(slots=True)
class State:
    """Mutable onboard inventories, updated once per hourly transition."""

    ess_kwh: float
    h2_kg: list[float]


@dataclass(frozen=True, slots=True)
class Step:
    timestamp: str
    lcoe_krw_per_kwh: float
    smp_krw_per_kwh: float
    h2_price_krw_per_kg: float
    mode2: bool
    demand_kwh: float
    hfc_kwh: float
    ess_emergency_kwh: float
    unserved_kwh: float
    phase1_ess_kwh: float
    pv_ess_charge_kwh: float
    grid_ess_charge_kwh: float
    pv_p2g_kwh: float
    external_h2_kg: float
    consumed_h2_kg: float
    hfc_trucks_dispatched: int
    soc_start: float
    soc_end: float
    h2_start_kg: float
    h2_end_kg: float
    h2_min_truck_kg: float
    h2_max_truck_kg: float
    revenue_krw: float
    h2_purchase_krw: float
    grid_purchase_krw: float
    ess_wear_krw: float
    avoided_interruption_krw: float

    @property
    def operating_net_krw(self) -> float:
        return (
            self.revenue_krw
            - self.h2_purchase_krw
            - self.grid_purchase_krw
            - self.ess_wear_krw
        )


@dataclass(frozen=True, slots=True)
class Run:
    scenario: Scenario
    steps: tuple[Step, ...]
    terminal_soc: float
    terminal_h2_kg: float
    terminal_inventory_change_krw: float
    initial_inventory_krw: float
    terminal_inventory_krw: float

    def total(self, field: str) -> float:
        return sum(float(getattr(step, field)) for step in self.steps)
