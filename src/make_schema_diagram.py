"""Draw the star schema as a PNG (docs/img/star_schema.png).
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from src.config import DOCS_IMG_DIR  # noqa: E402

TABLES = {
    "dim_store": (0.5, 5.2, ["store_id (PK)", "city", "state", "address", "postal_code", "opening_date"], "#e8f0fa"),
    "dim_product": (0.5, 1.0, ["product_id (PK)", "product_name", "category", "subcategory", "brand",
                               "list_price", "competitor_list_price"], "#e8f0fa"),
    "dim_date": (11.0, 3.0, ["date_id (PK)", "full_date", "year, quarter, month", "month_name",
                             "iso_year, iso_week", "day_of_month, day_of_week", "day_name",
                             "is_weekend", "is_holiday", "holiday_name"], "#e8f0fa"),
    "fact_inventory": (5.6, 2.6, ["inventory_fact_id (PK)", "date_id (FK)", "store_id (FK)", "product_id (FK)",
                                  "inventory_level", "units_sold", "units_ordered", "demand_forecast",
                                  "unit_price", "competitor_price", "revenue", "is_promotion"], "#fdf0e0"),
}
W = 4.0
LINE_H = 0.42


def draw_box(ax, name, x, y, cols, color):
    h = LINE_H * (len(cols) + 1.4)
    ax.add_patch(FancyBboxPatch((x, y), W, h, boxstyle="round,pad=0.02", fc=color, ec="#333", lw=1.4))
    ax.text(x + W / 2, y + h - LINE_H * 0.7, name, ha="center", va="center", fontsize=12, fontweight="bold")
    ax.plot([x, x + W], [y + h - LINE_H * 1.3] * 2, color="#333", lw=1)
    for i, col in enumerate(cols):
        ax.text(x + 0.2, y + h - LINE_H * (2.0 + i), col, va="center", fontsize=9.5,
                fontweight="bold" if "(PK)" in col or "(FK)" in col else "normal")
    return x, y, W, h


def main() -> None:
    fig, ax = plt.subplots(figsize=(15, 8.5))
    ax.set_xlim(0, 15.5)
    ax.set_ylim(0, 9)
    ax.axis("off")
    boxes = {n: draw_box(ax, n, *v[:2], v[2], v[3]) for n, v in TABLES.items()}

    def link(dim, fact, y_dim, y_fact):
        dx, dy, dw, dh = boxes[dim]
        fx, fy, fw, fh = boxes[fact]
        left_side = dx + dw < fx
        x1 = dx + dw if left_side else dx
        x2 = fx if left_side else fx + fw
        ax.annotate("", xy=(x2, y_fact), xytext=(x1, y_dim),
                    arrowprops=dict(arrowstyle="-|>", color="#555", lw=1.5))
        ax.text((x1 + x2) / 2, (y_dim + y_fact) / 2 + 0.2, "1 : many", fontsize=8.5, color="#555", ha="center")

    fx, fy, fw, fh = boxes["fact_inventory"]
    link("dim_store", "fact_inventory", boxes["dim_store"][1] + 2.2, fy + fh - LINE_H * 4.0)
    link("dim_product", "fact_inventory", boxes["dim_product"][1] + 2.2, fy + fh - LINE_H * 5.0)
    link("dim_date", "fact_inventory", boxes["dim_date"][1] + 2.8, fy + fh - LINE_H * 3.0)

    ax.text(7.75, 8.6, "Inventory star schema  (grain: one row per store x product x day)",
            ha="center", fontsize=13, fontweight="bold")
    DOCS_IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(DOCS_IMG_DIR / "star_schema.png", dpi=140, bbox_inches="tight", facecolor="white")
    print("Wrote", DOCS_IMG_DIR / "star_schema.png")


if __name__ == "__main__":
    main()