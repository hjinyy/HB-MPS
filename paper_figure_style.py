"""Typography shared by the post-main paper figures."""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.text import Text

TITLE_SIZE = 33
LABEL_SIZE = 32
TICK_SIZE = 33
LEGEND_SIZE = 22
ANNOTATION_SIZE = 25


def apply_paper_typography(
    *, text_scale: float = 1.0, legend_scale: float = 1.0,
    y_tick_scale: float | None = None,
) -> None:
    """Match the Times New Roman sizes and weights of the main figures."""
    if y_tick_scale is None:
        y_tick_scale = text_scale
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": TICK_SIZE * text_scale,
            "font.weight": "bold",
            "axes.titlesize": TITLE_SIZE * text_scale,
            "axes.titleweight": "bold",
            "axes.labelsize": LABEL_SIZE * text_scale,
            "axes.labelweight": "bold",
            "xtick.labelsize": TICK_SIZE * text_scale,
            "ytick.labelsize": TICK_SIZE * y_tick_scale,
            "legend.fontsize": LEGEND_SIZE * legend_scale,
        }
    )


def bold_figure_text(fig: plt.Figure) -> None:
    """Apply the paper face to ticks, annotations, legends, and colorbars."""
    for item in fig.findobj(match=Text):
        item.set_fontfamily("Times New Roman")
        item.set_fontweight("bold")
