"""Create the README charts from the warehouse (run after `python -m src.pipeline`).

    python -m src.make_charts
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import DOCS_IMG_DIR  # noqa: E402
from src.db import get_engine  # noqa: E402
from src.kpis import run_kpi  # noqa: E402

COLOR = "#2f6db5"
ACCENT = "#d9822b"


def _style(ax, title: str, ylabel: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def main() -> None:
    engine = get_engine()
    DOCS_IMG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Revenue by category
    cat = run_kpi(engine, "revenue_by_category").sort_values("revenue")
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.barh(cat["category"], cat["revenue"] / 1e6, color=COLOR)
    for y, (rev, share) in enumerate(zip(cat["revenue"] / 1e6, cat["revenue_share_pct"])):
        ax.text(rev, y, f"  {rev:.1f}M ({share:.1f}%)", va="center", fontsize=9)
    ax.set_xlim(0, cat["revenue"].max() / 1e6 * 1.3)
    _style(ax, "Revenue by category (millions)")
    ax.grid(axis="y", alpha=0)
    fig.tight_layout()
    fig.savefig(DOCS_IMG_DIR / "revenue_by_category.png", dpi=150)
    plt.close(fig)

    # 2. Monthly revenue trend
    m = run_kpi(engine, "monthly_revenue_growth")
    labels = [f"{y}-{mo:02d}" for y, mo in zip(m["year"], m["month"])]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(labels, m["revenue"] / 1e6, marker="o", color=COLOR)
    ax.set_xticks(range(0, len(labels), 2))
    ax.set_xticklabels(labels[::2], rotation=45, ha="right", fontsize=8)
    _style(ax, "Monthly revenue (millions)")
    fig.tight_layout()
    fig.savefig(DOCS_IMG_DIR / "monthly_revenue.png", dpi=150)
    plt.close(fig)

    # 3. Pareto / ABC curve
    abc = run_kpi(engine, "abc_analysis")
    x = [(i + 1) / len(abc) * 100 for i in range(len(abc))]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(x, abc["cumulative_revenue_pct"], color=COLOR, linewidth=2)
    ax.axhline(80, color=ACCENT, linestyle="--", linewidth=1)
    ax.axhline(95, color=ACCENT, linestyle=":", linewidth=1)
    ax.set_xlabel("Share of products (ranked by revenue, %)")
    _style(ax, "ABC analysis: cumulative revenue (%)")
    ax.set_ylim(0, 102)
    fig.tight_layout()
    fig.savefig(DOCS_IMG_DIR / "abc_curve.png", dpi=150)
    plt.close(fig)
    print(f"Charts written to {DOCS_IMG_DIR}")


if __name__ == "__main__":
    main()
