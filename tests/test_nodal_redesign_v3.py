"""Checks for PV scale, AC surplus and revised nodal figure artifacts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from powerflow_validation import INPUT_PATH, PV_COLUMN, load_profiles

RESULTS = Path(__file__).resolve().parents[1] / "results" / "nodal_redesign_v3"
VOLTAGE_CEILING = 1.05


def test_pv_potential_and_ac_curtailment_balance() -> None:
    source = load_profiles(INPUT_PATH)
    pv = pd.read_csv(RESULTS / "pv_hourly.csv")
    metrics = pd.read_csv(RESULTS / "case_metrics.csv")
    scale = float(metrics.hb_mps_scale_pct.iloc[0]) / 100_000
    assert len(pv) == 168
    assert np.allclose(pv.pv_potential_mw, source[PV_COLUMN].to_numpy() * scale)
    assert np.allclose(pv.pv_potential_mw,
                       pv.pv_dispatch_mw + pv.pv_curtailed_mw)
    assert (pv.pv_dispatch_mw >= 0).all()
    assert pv.pv_curtailed_mw.gt(1e-6).any()
    assert pv.baseline_vmax_pu.max() <= VOLTAGE_CEILING + 1e-6
    assert pv.uncurtailed_vmax_pu.max() > VOLTAGE_CEILING
    assert np.allclose(pv.ac_export_surplus_mw,
                       np.maximum(-pv.baseline_slack_import_mw, 0.0))
    assert np.allclose(pv.baseline_slack_import_mw,
                       pv.total_load_mw - pv.pv_dispatch_mw
                       + pv.baseline_line_loss_mw, atol=1e-6)


@pytest.mark.parametrize("alpha", (1.3, 1.5))
def test_saved_pv_dispatch_and_hbmps_use_are_network_balanced(alpha: float) -> None:
    directory = RESULTS / f"alpha_{str(alpha).replace('.', '_')}"
    pv = pd.read_csv(RESULTS / "pv_hourly.csv")
    hourly = pd.read_csv(directory / "hourly.csv")
    buses = pd.read_csv(directory / "bus_hourly.csv")
    trucks = pd.read_csv(directory / "trucks.csv")
    metrics = pd.read_csv(RESULTS / "case_metrics.csv")
    scale = float(metrics.loc[metrics.alpha.eq(alpha), "hb_mps_scale_pct"].iloc[0]) / 100_000
    assert len(hourly) == 168
    assert len(buses) == 168 * 33
    assert len(trucks) == 168 * 5
    assert np.allclose(hourly.pv_generation_mw, pv.pv_dispatch_mw)
    assert np.allclose(hourly.network_pv_surplus_mw, pv.ac_export_surplus_mw,
                       atol=1e-6)
    assert np.allclose(hourly.pv_use_mw,
                       (hourly.pv_ess_charge_kwh + hourly.pv_p2g_kwh) * scale)
    assert (hourly.pv_use_mw <= hourly.network_pv_surplus_mw + 1e-7).all()
    assert np.allclose(hourly.bus_excess_mw,
                       hourly.emergency_supply_mw + hourly.residual_excess_mw)
    assert np.allclose(hourly.fleet_h2_end_kg,
                       hourly.fleet_h2_start_kg + hourly.h2_refilled_kg
                       + hourly.pv_p2g_kwh / 55.0 - hourly.h2_consumed_kg)
    for figure in (13, 14):
        stem = ("operation_and_nodal_deployment" if figure == 13
                else "nodal_voltage_analysis")
        for extension in ("png", "pdf"):
            assert (directory / f"fig{figure}_{stem}.{extension}").is_file()


def test_nodal_load_and_hbmps_scales_remain_c3() -> None:
    current = pd.read_csv(RESULTS / "case_metrics.csv")
    previous = pd.read_csv(RESULTS.parent / "nodal_redesign_v2" / "case_metrics.csv")
    previous = previous.loc[previous.case_id.eq("C3")]
    for row in current.itertuples(index=False):
        baseline = previous.loc[previous.alpha.eq(row.alpha)].iloc[0]
        assert row.industrial_bus_count == 19
        assert row.residential_bus_count == 13
        assert np.isclose(row.hb_mps_scale_pct, baseline.hb_mps_scale_pct)
        assert np.isclose(row.industrial_rating_mw, baseline.industrial_rating_mw)
        assert np.isclose(row.residential_rating_mw, baseline.residential_rating_mw)
        assert np.isclose(row.total_grid_load_peak_mw, baseline.total_grid_load_peak_mw)
