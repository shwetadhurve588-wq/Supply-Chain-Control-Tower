import unittest

import pandas as pd

from analytics import (
    delivery_kpis,
    estimate_delivery_impact,
    inventory_analysis,
    validate_inventory,
    validate_orders,
)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.orders = pd.DataFrame(
            {
                "order_id": ["1", "2", "3", "4"],
                "order_date": ["2025-01-01"] * 4,
                "promised_delivery_date": ["2025-01-03"] * 4,
                "actual_delivery_date": ["2025-01-03", "2025-01-04", "2025-01-02", "2025-01-05"],
                "region": ["North"] * 4,
                "carrier": ["A"] * 4,
                "shipping_mode": ["Standard"] * 4,
                "complaint_or_refund": [False, True, False, False],
            }
        )
        self.inventory = pd.DataFrame(
            {
                "product_id": ["A", "B", "C"],
                "product_name": ["Alpha", "Beta", "Gamma"],
                "units_sold_12m": [800, 150, 0],
                "on_hand": [5, 90, 12],
                "reorder_point": [20, 15, 10],
                "unit_cost": [10, 5, 4],
                "avg_selling_price": [20, 10, 8],
            }
        )

    def test_delivery_kpis_and_impact_use_actual_observed_issue_rate(self):
        orders = validate_orders(self.orders)
        kpis = delivery_kpis(orders)
        impact = estimate_delivery_impact(orders, 0.75)
        self.assertEqual(kpis["late_shipments"], 2)
        self.assertEqual(kpis["on_time_rate"], 0.5)
        self.assertEqual(impact["avoided_late_shipments"], 1)
        self.assertEqual(impact["avoided_complaints_or_refunds"], 1)
        self.assertEqual(impact["issue_rate_source"], "observed late-shipment data")

    def test_inventory_analysis_flags_stockout_slow_mover_and_a_reorder(self):
        inventory = inventory_analysis(validate_inventory(self.inventory), 0.25)
        alpha = inventory.set_index("product_id").loc["A"]
        gamma = inventory.set_index("product_id").loc["C"]
        self.assertEqual(alpha["abc_class"], "A")
        self.assertEqual(alpha["suggested_reorder_qty"], 20)
        self.assertTrue(gamma["slow_moving"])
        self.assertEqual(gamma["days_of_inventory"], float("inf"))

    def test_duplicate_order_ids_are_rejected(self):
        orders = self.orders.copy()
        orders.loc[1, "order_id"] = "1"
        with self.assertRaisesRegex(ValueError, "must be unique"):
            validate_orders(orders)

    def test_negative_inventory_values_are_rejected(self):
        inventory = self.inventory.copy()
        inventory.loc[0, "on_hand"] = -1
        with self.assertRaisesRegex(ValueError, "cannot contain negative"):
            validate_inventory(inventory)

    def test_impact_uses_assumption_when_issue_data_is_unavailable(self):
        orders = validate_orders(self.orders.drop(columns="complaint_or_refund"))
        impact = estimate_delivery_impact(orders, 0.75, assumed_late_issue_rate=0.25)
        self.assertEqual(impact["late_issue_rate"], 0.25)
        self.assertEqual(impact["issue_rate_source"], "user assumption")


if __name__ == "__main__":
    unittest.main()
