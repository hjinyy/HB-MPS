"""Execute and persist the isolated C1/C2/C3 × α nodal experiment."""

from __future__ import annotations

import pandas as pd

from powerflow_validation import INPUT_PATH, load_profiles

from .experiment import ALPHAS, CASES, OUTPUT_DIR, simulate
from .metrics import (
    bus_voltage_summary,
    summarize,
    truck_deployment_summary,
    validate_run,
)
from .plots import save_figures
from .report import write_report


def main() -> None:
    frame = load_profiles(INPUT_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = []
    for case in CASES:
        for alpha in ALPHAS:
            run = simulate(case, alpha, frame)
            validate_run(run)
            directory = OUTPUT_DIR / f"{case.name}_alpha_{str(alpha).replace('.', '_')}"
            directory.mkdir(parents=True, exist_ok=True)
            run.result.hourly.to_csv(directory / "hourly.csv", index=False)
            run.result.buses.to_csv(directory / "bus_hourly.csv", index=False)
            run.result.trucks.to_csv(directory / "trucks.csv", index=False)
            save_figures(run, directory)
            runs.append(run)
            print(f"Validated and saved {case.name}, α={alpha}: {directory}", flush=True)

    metrics = pd.DataFrame([summarize(run, frame) for run in runs])
    metrics.to_csv(OUTPUT_DIR / "case_metrics.csv", index=False)
    pd.concat([bus_voltage_summary(run) for run in runs], ignore_index=True).to_csv(
        OUTPUT_DIR / "bus_voltage_summary.csv", index=False
    )
    pd.concat([truck_deployment_summary(run) for run in runs], ignore_index=True).to_csv(
        OUTPUT_DIR / "truck_deployment_summary.csv", index=False
    )
    write_report(runs, metrics, frame, OUTPUT_DIR / "ANALYSIS_REPORT.md")


if __name__ == "__main__":
    main()
