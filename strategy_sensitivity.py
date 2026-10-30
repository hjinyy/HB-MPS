"""Dual-mode policy sensitivity with the original hybrid asset ratings.

This compares operating rules, not vehicle mobility or node-level service.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from asset_ablation import CONFIGURATIONS, INPUT, Policy, load_hours, run_configuration

OUT: Final = Path(__file__).resolve().parent / "results"
SOC_THRESHOLDS: Final = (0.2, 0.3, 0.5)
LCOE_QUANTILES: Final = (0.4, 0.6, 0.8)


def main() -> None:
    """Cross operating thresholds and visualize reliability/economic outcomes."""
    hours = load_hours(INPUT)
    hybrid = CONFIGURATIONS[2]
    records: list[dict[str, float]] = []
    for soc_threshold in SOC_THRESHOLDS:
        for lcoe_quantile in LCOE_QUANTILES:
            _, summary = run_configuration(
                hours, hybrid, Policy(soc_threshold, lcoe_quantile)
            )
            records.append(
                {
                    "phase1_soc_threshold": soc_threshold,
                    "phase1_lcoe_quantile": lcoe_quantile,
                    "unserved_mwh": float(summary["unserved_kwh"]) / 1000,
                    "operating_net_million_krw": float(summary["operating_net_krw"])
                    / 1e6,
                    "avoided_outage_million_krw": float(summary["avoided_outage_krw"])
                    / 1e6,
                }
            )

    OUT.mkdir(exist_ok=True)
    with (OUT / "dual_mode_policy_sensitivity.csv").open(
        "w", newline="", encoding="utf-8"
    ) as target:
        writer = csv.DictWriter(
            target, fieldnames=list(records[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(records)

    unserved = np.array([row["unserved_mwh"] for row in records]).reshape(3, 3)
    operating = np.array([row["operating_net_million_krw"] for row in records]).reshape(
        3, 3
    )
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 13})
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), dpi=220)
    for ax, values, title, units, cmap in zip(
        axes,
        (unserved, operating),
        ("Residual unserved energy", "Operating net"),
        ("MWh", "million KRW"),
        ("YlOrRd", "BrBG"),
        strict=True,
    ):
        image = ax.imshow(values, origin="lower", cmap=cmap, aspect="equal")
        for y, x in np.ndindex(values.shape):
            red, green, blue, _ = image.cmap(image.norm(values[y, x]))
            ink = (
                "white"
                if 0.299 * red + 0.587 * green + 0.114 * blue < 0.45
                else "black"
            )
            ax.text(x, y, f"{values[y, x]:.2f}", ha="center", va="center", color=ink)
        ax.set_xticks(range(3), ("0.4", "0.6", "0.8"))
        ax.set_yticks(range(3), ("0.2", "0.3", "0.5"))
        ax.set_xlabel("Phase 1 LCOE quantile")
        ax.set_ylabel("Phase 1 ESS SOC threshold")
        ax.set_title(title)
        fig.colorbar(image, ax=ax, label=units, shrink=0.75)
    fig.suptitle("Dual-mode policy sensitivity (α=1.3, 1.5 + 1.5 MWh)")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(
            OUT / f"figure_12_dual_mode_policy_sensitivity.{suffix}",
            bbox_inches="tight",
        )
    plt.close(fig)
    print(f"Unserved range: {unserved.min():.3f}–{unserved.max():.3f} MWh")
    print(
        f"Operating net range: {operating.min():.3f}–{operating.max():.3f} million KRW"
    )


if __name__ == "__main__":
    main()
