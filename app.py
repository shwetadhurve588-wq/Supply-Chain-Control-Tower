from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import (
    delivery_kpis,
    delivery_segments,
    estimate_delivery_impact,
    inventory_analysis,
    validate_inventory,
    validate_orders,
)
from sample_data import make_sample_data


st.set_page_config(
    page_title="Supply Chain | Delivery & Inventory",
    page_icon="📦",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    .stApp {background: #ffffff; color: #172033;}
    [data-testid="stSidebar"] {background: #f1f5f9;}
    [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {
        color: #263445 !important;
    }
    [data-testid="stMetric"] {
        background: #e8f0fa; border: 1px solid #aebfd3;
        padding: 1rem 1.2rem; border-radius: 12px;
    }
    [data-testid="stMetricLabel"] {color: #334155 !important;}
    [data-testid="stMetricValue"] {color: #102a43 !important;}
    [data-testid="stMetricDelta"] {
        background: #eef3f8 !important;
        border: 1px solid #c1cedb;
        border-radius: 999px;
        padding: 2px 8px;
        color: #1f2937 !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricDelta"] p {color: #1f2937 !important;}
    [data-testid="stMetricDelta"] svg {width: 1rem; height: 1rem;}
    [data-testid="stMetricDeltaIcon-Down"] {color: #b42318 !important;}
    [data-testid="stMetricDeltaIcon-Up"] {color: #137547 !important;}
    [data-testid="stDataFrame"] {color: #172033;}
    [data-testid="stAlert"] {
        background-color: #dceaf7 !important;
        border: 1px solid #8eabc8 !important;
        border-left: 5px solid #176b87 !important;
        border-radius: 8px;
    }
    [data-testid="stAlertContainer"] {
        background-color: #dceaf7 !important;
        color: #17324d !important;
    }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
        color: #17324d !important;
    }
    [data-testid="stAlertContainer"] svg {color: #176b87 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Supply Chain Control Tower")
st.caption("Find delivery bottlenecks, prioritize high-value inventory, and size the opportunity.")

with st.sidebar:
    st.header("Data")
    use_demo = st.toggle("Use built-in demo data", value=True)
    order_file = inventory_file = None
    if not use_demo:
        order_file = st.file_uploader("Orders / shipments CSV", type="csv", key="orders")
        inventory_file = st.file_uploader("Inventory CSV", type="csv", key="inventory")
        st.caption("Upload both files, or leave either empty to use its demo dataset.")
    st.divider()
    st.header("Planning assumptions")
    target_otd = st.slider("Target on-time delivery", 50, 100, 75, format="%d%%") / 100
    assumed_issue_rate = st.slider(
        "Issues per late shipment (when not supplied in CSV)",
        0, 100, 20, format="%d%%",
    ) / 100
    safety_uplift = st.slider("Extra reorder-point buffer for A items", 0, 100, 25, format="%d%%") / 100


demo_orders, demo_inventory = make_sample_data()

try:
    raw_orders = pd.read_csv(order_file) if order_file is not None else demo_orders
    raw_inventory = pd.read_csv(inventory_file) if inventory_file is not None else demo_inventory
    orders = validate_orders(raw_orders)
    inventory = validate_inventory(raw_inventory)
except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as error:
    st.error(f"Could not load the supplied data: {error}")
    st.stop()

inventory_view = inventory_analysis(inventory, safety_uplift)
delivery = delivery_kpis(orders)
impact = estimate_delivery_impact(orders, target_otd, assumed_issue_rate)

with st.container():
    st.subheader("Executive snapshot")
    metrics = st.columns(5)
    otd_delta_pp = (delivery["on_time_rate"] - target_otd) * 100
    metrics[0].metric(
        "On-time delivery",
        f"{delivery['on_time_rate']:.1%}",
        f"{otd_delta_pp:+.1f} pp vs target",
        delta_color="normal",
    )
    metrics[1].metric(
        "Late shipments",
        f"{delivery['late_shipments']:,}",
        help=f"Out of {delivery['shipments']:,} total shipments.",
    )
    metrics[2].metric("Average late by", f"{delivery['average_late_days']:.1f} days")
    sku_stockout_rate = float(inventory_view["on_hand"].le(0).mean())
    metrics[3].metric(
        f"SKUs out ({int(inventory_view['on_hand'].le(0).sum())}/{len(inventory_view)})",
        f"{sku_stockout_rate:.1%}",
    )
    metrics[4].metric("Inventory at cost", f"${inventory_view['inventory_value'].sum():,.0f}")

delivery_tab, inventory_tab, impact_tab, data_tab = st.tabs(
    ["Delivery performance", "Inventory & ABC", "Impact scenario", "Data guide"]
)

with delivery_tab:
    st.subheader("Where deliveries run late")
    left, right = st.columns(2)
    carrier_perf = delivery_segments(orders, ["carrier"])
    mode_perf = delivery_segments(orders, ["shipping_mode"])
    with left:
        st.markdown("**Carrier on-time rate**")
        st.plotly_chart(
            px.bar(
                carrier_perf.sort_values("on_time_rate"),
                x="on_time_rate", y="carrier", orientation="h",
                color="on_time_rate", color_continuous_scale="RdYlGn",
                range_color=(0, 1), labels={"on_time_rate": "On-time rate", "carrier": "Carrier"},
                template="plotly_white",
            ).update_layout(coloraxis_showscale=False, xaxis_tickformat=".0%"),
            width="stretch",
        )
    with right:
        st.markdown("**Shipping mode: speed vs reliability**")
        mode_perf = mode_perf.merge(
            orders.groupby("shipping_mode")
            .apply(lambda group: (group["promised_delivery_date"] - group["order_date"]).dt.days.mean(), include_groups=False)
            .rename("promised_transit_days"),
            on="shipping_mode",
        )
        st.plotly_chart(
            px.scatter(
                mode_perf, x="promised_transit_days", y="on_time_rate",
                size="shipments", color="shipping_mode", hover_name="shipping_mode",
                labels={
                    "promised_transit_days": "Average promised transit (days)",
                    "on_time_rate": "On-time rate",
                    "shipments": "Shipments",
                },
                template="plotly_white",
            ).update_layout(yaxis_tickformat=".0%"),
            width="stretch",
        )

    st.markdown("**Lowest-performing region and shipping-mode combinations**")
    route_perf = delivery_segments(orders, ["region", "shipping_mode"])
    st.dataframe(
        route_perf.rename(
            columns={
                "region": "Region",
                "shipping_mode": "Shipping mode",
                "shipments": "Shipments",
                "on_time_rate": "On-time rate",
                "average_late_days": "Avg. late days",
            }
        ).style.format({"On-time rate": "{:.1%}", "Avg. late days": "{:.1f}"}),
        width="stretch",
        hide_index=True,
    )

    st.markdown("**Carrier detail**")
    st.dataframe(
        carrier_perf.rename(
            columns={
                "carrier": "Carrier",
                "shipments": "Shipments",
                "on_time_rate": "On-time rate",
                "average_late_days": "Avg. late days",
            }
        ).style.format({"On-time rate": "{:.1%}", "Avg. late days": "{:.1f}"}),
        width="stretch",
        hide_index=True,
    )

with inventory_tab:
    st.subheader("Protect availability without overbuying")
    abc_summary = (
        inventory_view.groupby("abc_class", as_index=False)
        .agg(
            products=("product_id", "size"),
            annual_sales=("annual_sales", "sum"),
            inventory_value=("inventory_value", "sum"),
        )
    )
    abc_summary["sales_share"] = abc_summary["annual_sales"] / max(inventory_view["annual_sales"].sum(), 1)
    abc_left, abc_right = st.columns([1, 1.5])
    with abc_left:
        st.markdown("**ABC share of annual sales**")
        st.plotly_chart(
            px.bar(
                abc_summary, x="abc_class", y="sales_share", color="abc_class",
                labels={"abc_class": "ABC class", "sales_share": "Share of annual sales"},
                color_discrete_map={"A": "#176B87", "B": "#64A6BD", "C": "#B8CBD3"},
                template="plotly_white",
            ).update_layout(yaxis_tickformat=".0%", showlegend=False),
            width="stretch",
        )
    with abc_right:
        st.markdown("**Stock cover vs annual sales**")
        chart_inventory = inventory_view.copy()
        chart_inventory["chart_days_cover"] = chart_inventory["days_of_inventory"].clip(upper=365)
        st.plotly_chart(
            px.scatter(
                chart_inventory, x="annual_sales", y="chart_days_cover",
                color="abc_class", size="on_hand", hover_name="product_name",
                hover_data=["on_hand", "reorder_point", "suggested_reorder_qty"],
                labels={
                    "annual_sales": "Annual sales value ($)",
                    "chart_days_cover": "On-hand days (capped at 365)",
                    "abc_class": "ABC class",
                    "on_hand": "Units on hand",
                },
                color_discrete_map={"A": "#176B87", "B": "#64A6BD", "C": "#B8CBD3"},
                template="plotly_white",
            ),
            width="stretch",
        )
    total_slow_value = inventory_view.loc[inventory_view["slow_moving"], "inventory_value"].sum()
    stock_metrics = st.columns(3)
    stock_metrics[0].metric("A-class products", int(inventory_view["abc_class"].eq("A").sum()))
    stock_metrics[1].metric("At/below reorder point", int(inventory_view["at_or_below_reorder_point"].sum()))
    stock_metrics[2].metric("Slow-moving stock at cost", f"${total_slow_value:,.0f}")

    urgent = inventory_view[
        inventory_view["at_or_below_reorder_point"] | inventory_view["slow_moving"]
    ].copy()
    urgent["priority"] = urgent.apply(
        lambda row: "Reorder" if row["at_or_below_reorder_point"] else "Review / reduce",
        axis=1,
    )
    st.markdown("**Reorder and slow-moving review list**")
    st.dataframe(
        urgent[
            [
                "product_id", "product_name", "abc_class", "priority",
                "units_sold_12m", "on_hand", "reorder_point",
                "days_of_inventory", "suggested_reorder_qty", "inventory_value",
            ]
        ].rename(
            columns={
                "product_id": "SKU",
                "product_name": "Product",
                "abc_class": "ABC",
                "units_sold_12m": "Units sold (12m)",
                "on_hand": "On hand",
                "reorder_point": "Reorder point",
                "days_of_inventory": "Days of inventory",
                "suggested_reorder_qty": "Suggested reorder qty",
                "inventory_value": "Stock value ($)",
            }
        ).style.format(
            {
                "Days of inventory": lambda value: "No sales" if value == float("inf") else f"{value:.0f}",
                "Stock value ($)": "${:,.2f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Suggested reorder quantity is a planning heuristic: it tops up A-class items "
        "to the reorder point plus the selected buffer. Validate against supplier lead times."
    )

with impact_tab:
    st.subheader("What could improving on-time delivery change?")
    st.caption(
        "This scenario applies the target to the current shipment volume. It is an estimate, "
        "not a causal forecast or a guaranteed savings figure."
    )
    impact_cols = st.columns(3)
    impact_cols[0].metric("Current on-time rate", f"{impact['current_on_time_rate']:.1%}")
    impact_cols[1].metric("Target on-time rate", f"{impact['target_on_time_rate']:.1%}")
    impact_cols[2].metric("Potential late shipments avoided", f"{impact['avoided_late_shipments']:,}")
    issue_label = (
        f"observed late-shipment rate ({impact['late_issue_rate']:.1%})"
        if impact["issue_rate_source"] == "observed late-shipment data"
        else f"assumed issue rate ({impact['late_issue_rate']:.1%})"
    )
    st.success(
        f"At the selected target, an estimated **{impact['avoided_complaints_or_refunds']:,} "
        f"complaints/refunds** could be avoided across this shipment volume, using the {issue_label}."
    )
    st.info(
        f"Formula: max(target OTD − current OTD, 0) × {delivery['shipments']:,} shipments "
        f"= {impact['avoided_late_shipments']:,} fewer late shipments; multiplied by the "
        f"late-shipment complaint/refund rate = {impact['avoided_complaints_or_refunds']:,} estimated issues avoided."
    )
    if impact["issue_rate_source"] == "user assumption":
        st.warning(
            "No complaint_or_refund column was supplied, so the estimate uses the adjustable "
            "sidebar assumption. Add that column for a rate based on observed data."
        )

with data_tab:
    st.subheader("CSV input guide")
    st.write("The app accepts two independent CSV files. Each orders row must represent one shipment.")
    st.markdown("**Orders / shipments required columns**")
    st.code(
        "order_id, order_date, promised_delivery_date, actual_delivery_date, "
        "region, carrier, shipping_mode\n"
        "Optional: complaint_or_refund (true/false, yes/no, or 1/0)",
        language="text",
    )
    st.markdown("**Inventory required columns**")
    st.code(
        "product_id, product_name, units_sold_12m, on_hand, reorder_point, "
        "unit_cost, avg_selling_price",
        language="text",
    )
    st.markdown(
        "- On-time means actual delivery date is on or before the promised date.\n"
        "- Stock-out rate is the share of listed SKUs with zero units on hand.\n"
        "- ABC uses annual sales value: A covers the first 80%, B the next 15%, and C the remainder.\n"
        "- Slow-moving means over 180 days of stock cover or no sales in the supplied 12-month period.\n"
        "- The inventory buffer and impact rate are planning assumptions, not statistical forecasts."
    )

st.caption("Use the sidebar to adjust targets and assumptions, or upload your own data.")
