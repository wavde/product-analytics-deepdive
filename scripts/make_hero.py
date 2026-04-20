"""Generate the hero chart shown in README.md.

Three panels covering the case studies:
  (1) Funnel conversion with drop-off highlighted.
  (2) Weekly retention curve by acquisition channel.
  (3) Engagement segmentation (simulated 2D cluster scatter).

Run:  python scripts/make_hero.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RNG = np.random.default_rng(7)
OUT = Path(__file__).resolve().parents[1] / "docs" / "hero.png"


def panel_funnel(ax: plt.Axes) -> None:
    steps = ["Visit", "Signup", "Activate", "Habitual"]
    counts = [100_000, 42_000, 19_000, 8_500]
    colors = ["#4c72b0", "#4c72b0", "#dd8452", "#55a868"]
    bars = ax.barh(steps[::-1], counts[::-1], color=colors[::-1])
    for bar, c in zip(bars, counts[::-1]):
        pct = c / counts[0] * 100
        ax.text(c + 1500, bar.get_y() + bar.get_height() / 2,
                f"{c:,} ({pct:.0f}%)", va="center", fontsize=9)
    ax.set_xlim(0, max(counts) * 1.25)
    ax.set_xlabel("Users")
    ax.set_title("Acquisition funnel\nBiggest drop: Visit → Signup (58%)")
    ax.grid(True, axis="x", alpha=0.3)


def panel_retention(ax: plt.Axes) -> None:
    weeks = np.arange(0, 13)
    cohorts = {
        "Organic":  np.exp(-0.09 * weeks) * 100,
        "Paid":     np.exp(-0.22 * weeks) * 100,
        "Referral": np.exp(-0.05 * weeks) * 100,
    }
    for name, y in cohorts.items():
        ax.plot(weeks, y, lw=2, marker="o", markersize=4, label=name)
    ax.set_xlabel("Weeks since signup")
    ax.set_ylabel("% still active")
    ax.set_title("Retention by acquisition channel\nReferral retains 2× vs Paid at W12")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 105)


def panel_segments(ax: plt.Axes) -> None:
    centers = [(1, 1), (4, 2), (6, 6), (2, 5)]
    labels = ["Churn risk", "Casual", "Power users", "Explorers"]
    colors = ["#d62728", "#8c8c8c", "#2ca02c", "#1f77b4"]
    sizes = [800, 1500, 400, 600]
    for (cx, cy), lbl, col, n in zip(centers, labels, colors, sizes):
        x = RNG.normal(cx, 0.6, size=n)
        y = RNG.normal(cy, 0.6, size=n)
        ax.scatter(x, y, s=10, alpha=0.45, color=col, label=f"{lbl} (n={n})")
    ax.set_xlabel("Views (28d)")
    ax.set_ylabel("Feature breadth")
    ax.set_title("Engagement segmentation\n4 clusters by view count + breadth")
    ax.legend(loc="upper left", fontsize=8, markerscale=2)
    ax.grid(True, alpha=0.3)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    panel_funnel(axes[0])
    panel_retention(axes[1])
    panel_segments(axes[2])
    fig.suptitle("product-analytics-deepdive — funnel, retention, and segmentation",
                 fontsize=13, y=1.03)
    fig.tight_layout()
    fig.savefig(OUT, dpi=140, bbox_inches="tight")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
