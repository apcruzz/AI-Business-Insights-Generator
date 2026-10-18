# Converts uploaded column names/types to the common row format used by charts and the analyst.
"""Validate mapped sales columns and normalize them for the dashboard."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time

import pandas as pd
from dateutil import parser as date_parser

from backend.fields import FIELDS
from backend.revenue import resolve_revenue
from backend.business_data import NUMERIC_FIELDS, enrich_business_data


def suggest_mapping(columns):
    """Guess which source columns match the dashboard's expected fields."""
    result = {}
    for field, aliases in FIELDS.items():
        # Compare simplified names so "Product Name" can match "productname".
        matches = [c for c in columns if re.sub(r"[^a-z0-9]", "", c.lower()) in aliases]
        result[field] = matches[0] if len(matches) == 1 else ""
    return result


def numeric(series, field, decimal):
    """Parse currency/number text safely and report the first bad row."""
    text = series.astype(str).str.strip()
    # Accept common spreadsheet formats like ($12.34), $12.34, and 1,234.56.
    text = text.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    text = text.str.replace(r"[$€£¥\s]", "", regex=True)
    text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False) if decimal == "comma" else text.str.replace(",", "", regex=False)
    values = pd.to_numeric(text, errors="coerce")
    invalid = values.isna() | ~values.map(lambda v: math.isfinite(float(v)))
    if invalid.any():
        row = int(invalid[invalid].index[0]) + 2
        raise ValueError(f"{field} has a blank or nonnumeric value on data row {row}. Correct the file or leave that optional field unmapped.")
    return values.astype(float)


def parse_date_value(value, dayfirst):
    """Parse one date value without pandas datetime inference."""
    # Keep this small and explicit because Python 3.14 and pandas date inference can conflict.
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    try:
        return date_parser.parse(text, dayfirst=dayfirst, fuzzy=False)
    except (TypeError, ValueError, OverflowError):
        return None


def normalize(frame, mapping, business, currency="USD", date_order="month", decimal="dot", line_total_basis=None, modifier_basis="line"):
    """Validate mapped source columns and build the normalized sales dataset."""
    if not isinstance(mapping, dict):
        raise ValueError("Confirm the column mapping first.")
    # Ignore blank/unrecognized mappings and reject missing or reused source columns.
    mapped = {k: v for k, v in mapping.items() if k in FIELDS and v}
    if any(v not in frame.columns for v in mapped.values()):
        raise ValueError("A mapped column is missing from this worksheet.")
    if len(set(mapped.values())) != len(mapped):
        raise ValueError("Map a source column to one field only.")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Enter a three-letter currency code, for example USD.")
    result = pd.DataFrame(index=frame.index)
    warnings = []
    numeric_fields = {"Quantity", "Unit_Price", "Gross_Sales", "Discount_Amount", "Net_Sales", "Unit_COGS", "Total_COGS", "Gross_Profit", "Hour", "Modifier_Amount", "Line_Total"}
    numeric_fields |= NUMERIC_FIELDS
    # Copy mapped columns into normalized names, converting numeric fields first.
    for key, column in mapped.items():
        if key in numeric_fields:
            source = frame[column]
            # Empty add-on cells mean no charge; nonempty text still fails numeric validation.
            if key == "Modifier_Amount":
                source = source.fillna(0).replace(r"^\s*$", "0", regex=True)
            result.loc[:, key] = numeric(source, key, decimal)
        elif key != "Date":
            result.loc[:, key] = frame[column].fillna("").astype(str).str.strip()
    if "Date" in mapped:
        source = frame[mapped["Date"]]
        if pd.api.types.is_numeric_dtype(source) or source.map(lambda v: isinstance(v, (int, float))).all():
            raise ValueError("Format the date column as dates, rather than raw spreadsheet serial numbers.")
        # Keep parsed dates as plain Python values to avoid Python 3.14/pandas crashes.
        dates = [parse_date_value(value, date_order == "day") for value in source.tolist()]
        if any(value is None for value in dates):
            raise ValueError("The mapped date column contains blank or invalid dates. Choose the date order or correct the file.")
        result.loc[:, "Date"] = [value.strftime("%Y-%m-%d") for value in dates]
        hours = [value.hour for value in dates]
        if "Hour" not in result and any(hour != 0 for hour in hours):
            result.loc[:, "Hour"] = hours
    if "Hour" not in result and "Time" in result:
        # Convert time strings or spreadsheet time fractions into 0-23 hour values.
        def time_hour(value):
            """Turn one mapped time value into an hour number from 0 to 23."""
            try:
                number = float(value)
                if 0 <= number < 1:
                    return math.floor(number * 24)
            except ValueError:
                pass
            match = re.match(r"^(\d{1,2}):", value)
            if match:
                hour = int(match.group(1))
                ampm = re.search(r"\b(AM|PM)\b", value, re.I)
                if ampm:
                    if not 1 <= hour <= 12:
                        return None
                    hour = hour % 12 + (12 if ampm.group(1).upper() == "PM" else 0)
                return hour
            return None
        result.loc[:, "Hour"] = result["Time"].map(time_hour)
    if "Hour" in result:
        hours = pd.to_numeric(result["Hour"], errors="coerce")
        if hours.isna().any() or ((hours < 0) | (hours > 23) | (hours % 1 != 0)).any():
            raise ValueError("Hour values must be whole numbers from 0 to 23, and Time values must use 24-hour notation.")
        result.loc[:, "Hour"] = hours.astype(int)
    # Resolve explicit totals first; otherwise calculate base revenue plus add-ons.
    resolve_revenue(result, warnings, line_total_basis, modifier_basis)
    if "Total_COGS" not in result and {"Unit_COGS", "Quantity"} <= set(result):
        result.loc[:, "Total_COGS"] = (result["Unit_COGS"] * result["Quantity"]).round(2)
    if "Total_COGS" in result:
        # Gross profit can be supplied or calculated from net sales minus product costs.
        profit = (result["Net_Sales"]-result["Total_COGS"]).round(2)
        if "Gross_Profit" in result and ((result["Gross_Profit"]-profit).abs() > .011).any():
            raise ValueError("Mapped gross profit does not match net sales minus product costs.")
        result.loc[:, "Gross_Profit"] = profit
    # Fill display labels for missing dimensions; capability flags still identify absent source data.
    for field, default in {"Product_Name":"All sales", "Category":"Uncategorized", "Employee_Name":"Not provided", "Weather":"Not provided"}.items():
        if field not in result:
            result.loc[:, field] = default
        result.loc[:, field] = result[field].replace("", default)
    # Clean uploaded weather labels locally; this does not fetch weather from a service.
    if "Weather" in mapped:
        result.loc[:, "Weather"] = result["Weather"].str.replace(r"\s+\d.*$", "", regex=True)
    orders_valid = "Transaction_ID" in result and not result["Transaction_ID"].eq("").any()
    if orders_valid:
        # Order IDs are trusted only if each ID has one date/time/payment grouping.
        store_location = result["Store_Location"] if "Store_Location" in result else pd.Series("", index=result.index)
        result.loc[:, "Order_Key"] = result["Transaction_ID"] + "|" + store_location
        for field in ("Date", "Time", "Payment_Method"):
            if field in result and (result.groupby("Order_Key")[field].nunique() > 1).any():
                orders_valid = False
        if not orders_valid:
            warnings.append("Some order IDs span different dates, times, or payment methods. Order count and average order value are disabled until grouping is verified.")
    # Keep source records intact while reporting duplicates, returns, and missing costs.
    if frame.duplicated().any():
        warnings.append(f"{int(frame.duplicated().sum())} exact duplicate source rows were found. They are retained; verify whether they represent distinct sales.")
    if (result["Net_Sales"] < 0).any():
        warnings.append("Negative sales are included in totals. Pie charts are replaced with a contribution list when category totals are negative.")
    if "Gross_Profit" not in result:
        warnings.append("Cost and gross profit were not supplied: profit and margin metrics are unavailable.")
    warnings.append("Totals describe recorded data. Verify coverage before inferring demand, staffing needs, or causes. Gross profit excludes operating expenses.")
    # Tell the frontend which metrics and charts the validated columns can support.
    capabilities = {key: key in result for key in ("Date", "Hour", "Quantity", "Gross_Profit", "Gross_Sales", "Discount_Amount")}
    capabilities.update({"orders": orders_valid, "product": "Product_Name" in mapped, "category": "Category" in mapped, "employee": "Employee_Name" in mapped, "weather": "Weather" in mapped})
    capabilities.update(enrich_business_data(result, mapped, parse_date_value, date_order == "day", warnings))
    # The browser receives records plus capability flags so it can hide unsupported views.
    return {"rows": json.loads(result.to_json(orient="records")), "capabilities": capabilities, "warnings": warnings, "business": str(business)[:60], "currency": currency, "sourceRows": len(frame), "dateMin": result["Date"].min() if "Date" in result else None, "dateMax": result["Date"].max() if "Date" in result else None}
