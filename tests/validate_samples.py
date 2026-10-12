"""Verify sample totals and missing-data behavior: python -m tests.validate_samples"""
import pandas as pd
from backend.app import frame_from_payload, normalize, suggest_mapping

expected = {
    "Cafe.csv": (1000, 8125.23, 5999.23, False),
    "Furniture_Shop_Synthetic.csv": (1537, 715653.55, 354582.55, True),
    "Restaurant_Synthetic.csv": (6263, 73426.54, 52064.14, True),
    "Retail_Store_Synthetic.csv": (3235, 136398.05, 77254.05, True),
}
for name, (count, sales, profit, valid_orders) in expected.items():
    frame, _, _ = frame_from_payload({"sample": name})
    result = normalize(frame, suggest_mapping(frame.columns), name)
    assert len(result["rows"]) == count
    assert abs(sum(r["Net_Sales"] for r in result["rows"]) - sales) < .001
    assert abs(sum(r.get("Gross_Profit", 0) for r in result["rows"]) - profit) < .001
    assert result["capabilities"]["orders"] == valid_orders
    print("Verified", name)

frame = pd.DataFrame({"Revenue": [100, 200]})
result = normalize(frame, {"Net_Sales": "Revenue"}, "Other business")
assert sum(r["Net_Sales"] for r in result["rows"]) == 300
assert not result["capabilities"]["Gross_Profit"]
assert not result["capabilities"]["Quantity"]
assert not result["capabilities"]["orders"]
assert suggest_mapping(["Amount"])["Net_Sales"] == ""

frame = pd.DataFrame({"Date": ["31/08/2026"], "Revenue": ["1.234,56"], "Time": ["9:00 PM"]})
result = normalize(frame, {"Date":"Date", "Net_Sales":"Revenue", "Time":"Time"}, "Other business", date_order="day", decimal="comma")
assert result["rows"][0]["Net_Sales"] == 1234.56
assert result["rows"][0]["Hour"] == 21

try:
    normalize(pd.DataFrame({"Revenue":["bad"]}), {"Net_Sales":"Revenue"}, "Other business")
except ValueError:
    pass
else:
    raise AssertionError("Nonnumeric revenue must be rejected.")
print("All checks passed.")
