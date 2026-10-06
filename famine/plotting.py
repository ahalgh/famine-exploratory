"""Shared plot styling: fixed country colors and the standard IPC phase palette."""

import matplotlib as mpl
import matplotlib.pyplot as plt

from .loaders import COUNTRIES

# Categorical slots assigned in fixed order; color follows the country everywhere.
COUNTRY_COLORS = dict(zip(COUNTRIES, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]))

# Official IPC phase colors (domain convention readers already know).
IPC_COLORS = {1: "#cdfacd", 2: "#fae61e", 3: "#e67800", 4: "#c80000", 5: "#640000"}
CHANGE_COLORS = {"improve": "#2a78d6", "worsen": "#e34948", "none": "#c3c2b7"}

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def set_style():
    mpl.rcParams.update({
        "figure.dpi": 110, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "xtick.color": INK2, "ytick.color": INK2, "font.size": 9,
        "lines.linewidth": 1.6, "legend.frameon": False,
    })


def ipc_legend(ax, phases=(1, 2, 3, 4), **kw):
    from matplotlib.patches import Patch
    from .loaders import IPC_PHASES
    ax.legend(handles=[Patch(color=IPC_COLORS[p], label=f"{p} {IPC_PHASES[p]}") for p in phases], **kw)


def facet(n, ncols=2, w=6.2, h=2.6, **kw):
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(w * ncols, h * nrows), squeeze=False, **kw)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    return fig, axes.flat
