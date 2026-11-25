# Supply Chain Control Tower

A Streamlit dashboard for finding delivery bottlenecks and prioritizing inventory actions. It includes reproducible demo data and supports CSV uploads.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Data inputs

Upload one row per shipment in the orders CSV and one row per SKU in the inventory CSV. The dashboard validates required columns and reports input errors rather than silently dropping invalid rows. The **Data guide** tab lists the exact CSV fields and metric definitions.

Orders must include `order_id`, `order_date`, `promised_delivery_date`, `actual_delivery_date`, `region`, `carrier`, and `shipping_mode`. Optional `complaint_or_refund` values are used to estimate issues avoided; otherwise the adjustable sidebar assumption is used.

Inventory must include `product_id`, `product_name`, `units_sold_12m`, `on_hand`, `reorder_point`, `unit_cost`, and `avg_selling_price`.

The suggested reorder quantity is a simple planning heuristic based on the entered reorder point and selected A-class buffer. It is not a substitute for lead-time and demand-variability-based safety-stock calculations.
