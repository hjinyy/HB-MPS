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
from paper_figure_style import (
    TICK_SIZE,
    apply_paper_typography,
    normalize_figure_text,
    scale_figure_text,
)

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
    apply_paper_typography()
    plt.rcParams.update({
        "mathtext.fontset": "custom",
        "mathtext.rm": "Times New Roman",
        "mathtext.it": "Times New Roman:italic",
        "mathtext.bf": "Times New Roman:bold",
    })
    fig, axes = plt.subplots(1, 2, figsize=(24, 10), dpi=220)
    for ax, values, colorbar_label, cmap in zip(
        axes,
        (unserved, operating),
        (r"$E_{\mathrm{unserved}}$ (MWh)", r"$\Pi_{\mathrm{op}}$ (M KRW)"),
        ("YlOrRd", "YlOrRd"),
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
            ax.text(
                x, y, f"{values[y, x]:.2f}", ha="center", va="center",
                color=ink, fontsize=TICK_SIZE,
            )
        ax.set_xticks(range(3), ("0.4", "0.6", "0.8"))
        ax.set_yticks(range(3), ("0.2", "0.3", "0.5"))
        ax.set_xlabel(r"$q^{\mathrm{dis}}$" + f"\n({'a' if ax is axes[0] else 'b'})")
        ax.set_ylabel(r"$\mathrm{SOC}^{\mathrm{dis}}$ (%)")
        ax.set_xticks(np.arange(-0.5, 3, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 3, 1), minor=True)
        ax.grid(which="minor", color="black", linewidth=1.0)
        ax.tick_params(which="minor", bottom=False, left=False)
        fig.colorbar(image, ax=ax, label=colorbar_label, shrink=0.75)
    scale_figure_text(fig, 1.2)
    fig.tight_layout(w_pad=4.5)
    normalize_figure_text(fig)
    for suffix in ("png", "pdf"):
        fig.savefig(
            OUT / f"fig10_sensitivity_of_residual_unserved_energy_and_operating_net_benefit.{suffix}",
            bbox_inches="tight",
        )
    plt.close(fig)
    print(f"Unserved range: {unserved.min():.3f}–{unserved.max():.3f} MWh")
    print(
        f"Operating net range: {operating.min():.3f}–{operating.max():.3f} M KRW"
    )


if __name__ == "__main__":
    main()
