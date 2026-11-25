"""Validation and analysis helpers for the supply-chain dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd


ORDER_COLUMNS = (
    "order_id",
    "order_date",
    "promised_delivery_date",
    "actual_delivery_date",
    "region",
    "carrier",
    "shipping_mode",
)
INVENTORY_COLUMNS = (
    "product_id",
    "product_name",
    "units_sold_12m",
    "on_hand",
    "reorder_point",
    "unit_cost",
    "avg_selling_price",
)


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], label: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} data is missing required columns: {', '.join(missing)}.")
    if frame.empty:
        raise ValueError(f"{label} data has no rows.")


def validate_orders(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a clean copy of shipment-level order data or raise a useful error."""
    _require_columns(frame, ORDER_COLUMNS, "Orders")
    result = frame.copy()

    for column in ("order_id", "region", "carrier", "shipping_mode"):
        result[column] = result[column].astype("string").str.strip()
        if result[column].isna().any() or result[column].eq("").any():
            raise ValueError(f"Orders column '{column}' cannot contain blank values.")
    if result["order_id"].duplicated().any():
        raise ValueError("Orders must contain one row per shipment; 'order_id' values must be unique.")

    for column in ("order_date", "promised_delivery_date", "actual_delivery_date"):
        result[column] = pd.to_datetime(result[column], errors="coerce")
        if result[column].isna().any():
            raise ValueError(f"Orders column '{column}' contains a missing or invalid date.")
    if (result["promised_delivery_date"] < result["order_date"]).any():
        raise ValueError("Promised delivery dates cannot be earlier than order dates.")

    if "complaint_or_refund" in result.columns:
        true_values = {"true", "1", "yes", "y"}
        false_values = {"false", "0", "no", "n", ""}

        def parse_issue(value: object) -> bool:
            if pd.isna(value):
                return False
            if isinstance(value, (bool, np.bool_)):
                return bool(value)
            normalized = str(value).strip().lower()
            if normalized in true_values:
                return True
            if normalized in false_values:
                return False
            raise ValueError(
                "Orders column 'complaint_or_refund' must contain true/false, yes/no, or 1/0."
            )

        result["complaint_or_refund"] = result["complaint_or_refund"].map(parse_issue)

    result["late_days"] = (
        result["actual_delivery_date"] - result["promised_delivery_date"]
    ).dt.days.clip(lower=0)
    result["is_late"] = result["late_days"] > 0
    return result


def validate_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    """Return validated product-level inventory data."""
    _require_columns(frame, INVENTORY_COLUMNS, "Inventory")
    result = frame.copy()
    for column in ("product_id", "product_name"):
        result[column] = result[column].astype("string").str.strip()
        if result[column].isna().any() or result[column].eq("").any():
            raise ValueError(f"Inventory column '{column}' cannot contain blank values.")
    if result["product_id"].duplicated().any():
        raise ValueError("Inventory must contain one row per product; 'product_id' values must be unique.")

    numeric_columns = (
        "units_sold_12m",
        "on_hand",
        "reorder_point",
        "unit_cost",
        "avg_selling_price",
    )
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].isna().any() or not np.isfinite(result[column]).all():
            raise ValueError(f"Inventory column '{column}' must contain finite numeric values.")
        if (result[column] < 0).any():
            raise ValueError(f"Inventory column '{column}' cannot contain negative values.")
    return result


def delivery_kpis(orders: pd.DataFrame) -> dict[str, float | int]:
    late = orders["is_late"]
    return {
        "shipments": int(len(orders)),
        "on_time_rate": float((~late).mean()),
        "late_shipments": int(late.sum()),
        "average_late_days": float(orders.loc[late, "late_days"].mean()) if late.any() else 0.0,
    }


def delivery_segments(orders: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Summarize on-time performance and delays for one or more dimensions."""
    result = (
        orders.groupby(dimensions, dropna=False)
        .agg(
            shipments=("order_id", "size"),
            on_time_rate=("is_late", lambda values: float((~values).mean())),
            average_late_days=("late_days", lambda values: float(values[values > 0].mean()) if (values > 0).any() else 0.0),
        )
        .reset_index()
    )
    return result.sort_values(["on_time_rate", "shipments"], ascending=[True, False])


def inventory_analysis(frame: pd.DataFrame, safety_stock_uplift: float = 0.25) -> pd.DataFrame:
    """Add ABC class, stock cover and a reorder-point-based planning heuristic."""
    if not 0 <= safety_stock_uplift <= 2:
        raise ValueError("Safety-stock uplift must be between 0% and 200%.")
    result = frame.copy()
    result["annual_sales"] = result["units_sold_12m"] * result["avg_selling_price"]
    result = result.sort_values("annual_sales", ascending=False).reset_index(drop=True)
    total_sales = float(result["annual_sales"].sum())

    if total_sales == 0:
        result["abc_class"] = "C"
    else:
        cumulative_before = (result["annual_sales"].cumsum() - result["annual_sales"]) / total_sales
        result["abc_class"] = np.select(
            [cumulative_before < 0.80, cumulative_before < 0.95],
            ["A", "B"],
            default="C",
        )

    result["days_of_inventory"] = np.where(
        result["units_sold_12m"] > 0,
        result["on_hand"] / result["units_sold_12m"] * 365,
        np.inf,
    )
    result["slow_moving"] = (result["days_of_inventory"] > 180) | (result["units_sold_12m"] == 0)
    result["at_or_below_reorder_point"] = result["on_hand"] <= result["reorder_point"]
    uplift = np.where(result["abc_class"].eq("A"), safety_stock_uplift, 0.0)
    target_stock = result["reorder_point"] * (1 + uplift)
    result["suggested_reorder_qty"] = np.ceil((target_stock - result["on_hand"]).clip(lower=0))
    result["inventory_value"] = result["on_hand"] * result["unit_cost"]
    return result


def estimate_delivery_impact(
    orders: pd.DataFrame,
    target_on_time_rate: float,
    assumed_late_issue_rate: float = 0.20,
) -> dict[str, float | int | str]:
    """Estimate avoided late deliveries and associated issues under an OTD target."""
    if not 0 <= target_on_time_rate <= 1:
        raise ValueError("Target on-time rate must be between 0% and 100%.")
    if not 0 <= assumed_late_issue_rate <= 1:
        raise ValueError("Assumed late-delivery complaint/refund rate must be between 0% and 100%.")

    current_rate = float((~orders["is_late"]).mean())
    improvement = max(target_on_time_rate - current_rate, 0.0)
    avoided_late = int(round(len(orders) * improvement))

    issue_rate = assumed_late_issue_rate
    source = "user assumption"
    if "complaint_or_refund" in orders.columns:
        late_orders = orders.loc[orders["is_late"]]
        if not late_orders.empty:
            issue_rate = float(late_orders["complaint_or_refund"].mean())
            source = "observed late-shipment data"

    return {
        "current_on_time_rate": current_rate,
        "target_on_time_rate": target_on_time_rate,
        "avoided_late_shipments": avoided_late,
        "avoided_complaints_or_refunds": int(np.floor(avoided_late * issue_rate + 0.5)),
        "late_issue_rate": issue_rate,
        "issue_rate_source": source,
    }
