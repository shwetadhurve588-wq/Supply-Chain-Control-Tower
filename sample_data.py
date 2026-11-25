"""Deterministic demo data for first-run exploration."""

import numpy as np
import pandas as pd


def make_sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    count = 1400

    regions = np.array(["North", "South", "East", "West", "Central"])
    carriers = np.array(["SwiftShip", "ParcelPro", "Northstar", "BudgetFreight"])
    modes = np.array(["Express", "Standard", "Economy"])
    region = rng.choice(regions, count, p=[0.22, 0.20, 0.18, 0.20, 0.20])
    carrier = rng.choice(carriers, count, p=[0.27, 0.29, 0.24, 0.20])
    mode = rng.choice(modes, count, p=[0.20, 0.55, 0.25])

    order_dates = pd.Timestamp("2025-01-01") + pd.to_timedelta(
        rng.integers(0, 330, count), unit="D"
    )
    transit_days = np.select(
        [mode == "Express", mode == "Standard"],
        [rng.integers(2, 5, count), rng.integers(4, 9, count)],
        default=rng.integers(7, 15, count),
    )
    promised_dates = order_dates + pd.to_timedelta(transit_days, unit="D")

    carrier_risk = np.select(
        [carrier == "BudgetFreight", carrier == "ParcelPro", carrier == "Northstar"],
        [0.20, 0.08, 0.03],
        default=-0.04,
    )
    mode_risk = np.select(
        [mode == "Express", mode == "Economy"],
        [0.10, -0.02],
        default=0.0,
    )
    region_risk = np.where(np.isin(region, ["South", "West"]), 0.05, 0.0)
    late_probability = np.clip(0.30 + carrier_risk + mode_risk + region_risk, 0.08, 0.8)
    is_late = rng.random(count) < late_probability
    late_days = np.where(is_late, rng.integers(1, 8, count), -rng.integers(0, 3, count))
    actual_dates = promised_dates + pd.to_timedelta(late_days, unit="D")
    actual_late = (actual_dates > promised_dates)
    issue_probability = np.where(actual_late, 0.24, 0.025)
    complaints = rng.random(count) < issue_probability

    orders = pd.DataFrame(
        {
            "order_id": [f"ORD-{index:05d}" for index in range(1, count + 1)],
            "order_date": order_dates,
            "promised_delivery_date": promised_dates,
            "actual_delivery_date": actual_dates,
            "region": region,
            "carrier": carrier,
            "shipping_mode": mode,
            "complaint_or_refund": complaints,
        }
    )

    product_count = 90
    product_ids = np.arange(1, product_count + 1)
    annual_units = np.maximum(0, (rng.pareto(1.7, product_count) * 55).astype(int))
    annual_units[:8] += rng.integers(300, 900, 8)
    prices = np.round(rng.lognormal(mean=3.0, sigma=0.8, size=product_count), 2)
    monthly_demand = annual_units / 12
    on_hand = np.maximum(
        0,
        (monthly_demand * rng.uniform(0.15, 5.0, product_count)).astype(int)
    )
    on_hand[rng.choice(product_count, 9, replace=False)] = 0
    reorder_point = np.maximum(1, np.ceil(monthly_demand * rng.uniform(0.6, 1.8, product_count))).astype(int)
    inventory = pd.DataFrame(
        {
            "product_id": [f"SKU-{index:04d}" for index in product_ids],
            "product_name": [f"Product {index:02d}" for index in product_ids],
            "units_sold_12m": annual_units,
            "on_hand": on_hand,
            "reorder_point": reorder_point,
            "unit_cost": np.round(prices * rng.uniform(0.35, 0.75, product_count), 2),
            "avg_selling_price": prices,
        }
    )
    return orders, inventory
