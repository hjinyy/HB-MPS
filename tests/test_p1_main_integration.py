"""Integration checks for main figures, ablation, fleet and P1 power flow."""

from __future__ import annotations

import hashlib
import math
import runpy
import struct
import tarfile
from pathlib import Path

import pandapower.networks as nw
import pandas as pd

from asset_ablation import CONFIGURATIONS, Policy, run_configuration
from emergency_dispatch import run_scenario
from emergency_dispatch_model import Scenario, Strategy
from emergency_validation import validate_run
from hb_inputs import INPUT, load_hours
from main_p1_adapter import simulate_main_p1
from powerflow_validation import INDUSTRIAL_BUS_NUMBERS

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def test_main_p1_matches_five_truck_physical_path() -> None:
    # Given the exact original main-loader frame and the common hourly input.
    legacy_module = runpy.run_path(str(ROOT / "HB-MPS main simulation.py"))
    frame = legacy_module["load_input_data"]()
    hours = load_hours(INPUT)

    # When the official main adapter and the shared P1 engine run α=1.3.
    result, summary = simulate_main_p1(frame, 1.3, 5)
    run = run_scenario(hours, Scenario(1.3, 5, Strategy.P1))

    # Then plotted and tabulated quantities trace the same bounded dispatch.
    assert len(result) == 168
    assert math.isclose(result["HFC_Supply"].sum(), run.total("hfc_kwh"))
    assert math.isclose(result["ESS_Emergency_Supply"].sum(), run.total("ess_emergency_kwh"))
    assert math.isclose(result["Unserved_Energy"].sum(), run.total("unserved_kwh"))
    assert math.isclose(result["Net_Step_Profit"].sum(), sum(step.operating_net_krw for step in run.steps))
    assert math.isclose(summary["terminal_soc"], run.terminal_soc)
    assert result["Active_Trucks"].max() <= 5
    assert (result["HFC_Supply"] + result["ESS_Emergency_Supply"] + result["Unserved_Energy"] - result["Base_Penalty"] / 4902.75111695046).abs().max() < 1e-5
    validate_run(run)


def test_hybrid_ablation_uses_one_truck_p1_core() -> None:
    # Given the original component configuration and full measured week.
    hours = load_hours(INPUT)

    # When the retained Figure 10–11 wrapper and P1 engine run.
    _, summary = run_configuration(hours, CONFIGURATIONS[2], Policy())
    run = run_scenario(hours, Scenario(1.3, 1, Strategy.P1))

    # Then all key physical and economic quantities are identical.
    assert math.isclose(float(summary["ess_supply_kwh"]), run.total("ess_emergency_kwh"))
    assert math.isclose(float(summary["hfc_supply_kwh"]), run.total("hfc_kwh"))
    assert math.isclose(float(summary["unserved_kwh"]), run.total("unserved_kwh"))
    assert math.isclose(float(summary["operating_net_krw"]), sum(step.operating_net_krw for step in run.steps))


def test_powerflow_csv_uses_normalized_actual_p1_supply() -> None:
    # Given the same IEEE 33-bus industrial group and original load peak.
    hours = load_hours(INPUT)
    peak = max(hour.industrial for hour in hours)
    network = nw.case33bw()
    industrial_rating = float(network.load.loc[network.load.bus.isin({bus - 1 for bus in INDUSTRIAL_BUS_NUMBERS}), "p_mw"].sum())
    records = pd.read_csv(RESULTS / "pf_results.csv")

    # When the saved power-flow injection is checked against P1 supplied kWh.
    for alpha in (1.3, 1.5, 1.8):
        run = run_scenario(hours, Scenario(alpha, 5, Strategy.P1))
        rows = records.loc[records.alpha.eq(alpha)].sort_values("t")

        # Then every hourly MW injection follows the original normalization.
        expected = [(step.hfc_kwh + step.ess_emergency_kwh) / peak * industrial_rating for step in run.steps]
        assert len(rows) == 168
        assert all(math.isclose(actual, value, abs_tol=1e-9) for actual, value in zip(rows.hbmps_mw, expected, strict=True))
        assert all(math.isclose(raw, step.unserved_kwh, abs_tol=1e-7) for raw, step in zip(rows.unserved_kwh, run.steps, strict=True))


def test_figure_5_to_13_png_dimensions_match_archived_design() -> None:
    # Given the exact pre-P1 archive of all prior result files.
    with tarfile.open(RESULTS / "legacy_pre_p1.tar.gz") as archive:
        names = [member.name for member in archive.getmembers() if member.name.startswith("figure_") and member.name.endswith(".png")]

        # When regenerated files are compared to their originals.
        for name in names:
            original = archive.extractfile(name).read()
            updated = (RESULTS / name).read_bytes()

            # Then canvas pixel dimensions are unchanged; Figure 5 is byte-identical.
            assert struct.unpack(">II", original[16:24]) == struct.unpack(">II", updated[16:24]), name
            if name == "figure_5_energy_supply_demand_mismatch.png":
                assert hashlib.sha256(original).digest() == hashlib.sha256(updated).digest()
