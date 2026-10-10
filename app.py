"""Free local business dashboard. Run: python app.py"""
from __future__ import annotations

import base64
import io
import json
import math
import re
import secrets
import threading
import urllib.error
import urllib.request
import webbrowser
from collections import defaultdict
from datetime import date, datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
LIMIT = 20 * 1024 * 1024
TOKEN = secrets.token_urlsafe(32)
OLLAMA = "http://127.0.0.1:11434"
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Canonical dashboard fields and simple aliases used to suggest column mappings.
FIELDS = {
    "Date": ["date", "orderdate", "saledate", "transactiondate", "datetime", "timestamp"],
    "Time": ["time", "ordertime", "transactiontime"],
    "Hour": ["hour", "hourofday"],
    "Product_Name": ["productname", "product", "itemname", "item", "dish", "sku"],
    "Category": ["category", "productcategory", "department"],
    "Quantity": ["quantity", "qty", "unitssold"],
    "Unit_Price": ["unitprice", "price", "sellingprice"],
    "Gross_Sales": ["grosssales", "grossrevenue"],
    "Discount_Amount": ["discountamount", "discounts", "discountvalue"],
    "Net_Sales": ["netsales", "netrevenue", "salesrevenue", "revenue"],
    "Unit_COGS": ["unitcogs", "unitcost", "costperunit"],
    "Total_COGS": ["totalcogs", "cogs", "totalcost", "costofgoodssold"],
    "Gross_Profit": ["grossprofit"],
    "Transaction_ID": ["transactionid", "orderid", "receiptid", "invoicenumber", "invoiceid"],
    "Employee_Name": ["employeename", "employee", "cashier", "salesperson", "server"],
    "Payment_Method": ["paymentmethod", "paymenttype"],
    "Weather": ["weather", "weathersignal"],
    "Store_Location": ["storelocation", "store", "location"],
}


def frame_from_payload(payload):
    """Load a sample/uploaded CSV or spreadsheet into a pandas DataFrame."""
    name = str(payload.get("filename", ""))
    if payload.get("sample"):
        # Samples are read from the local samples folder by filename only.
        allowed = {p.name: p for p in (ROOT / "samples").glob("*.csv")}
        if payload["sample"] not in allowed:
            raise ValueError("Unknown sample dataset.")
        source = allowed[payload["sample"]]
        raw, name = source.read_bytes(), source.name
    else:
        try:
            raw = base64.b64decode(payload.get("file", ""), validate=True)
        except Exception:
            raise ValueError("The upload could not be read.") from None
    if not raw or len(raw) > LIMIT:
        raise ValueError("Choose a nonempty file smaller than 20 MB.")
    suffix = Path(name).suffix.lower()
    sheets = []
    # Excel files can contain several sheets, so the UI lets the user choose one.
    if suffix in {".xlsx", ".xls"}:
        book = pd.ExcelFile(io.BytesIO(raw))
        sheets = book.sheet_names
        sheet = payload.get("sheet") or sheets[0]
        if sheet not in sheets:
            raise ValueError("Choose a worksheet from this workbook.")
        frame = book.parse(sheet, dtype=object)
    elif suffix == ".csv":
        # Try common encodings and let pandas infer the delimiter.
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                frame = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=None, engine="python", dtype=object)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Save the CSV with UTF-8 encoding and try again.")
    else:
        raise ValueError("Upload a CSV, XLSX, or XLS file.")
    frame = frame.dropna(how="all").reset_index(drop=True)
    frame.columns = [str(c).strip() for c in frame.columns]
    if not len(frame) or len(frame) > 100000 or len(frame.columns) > 200:
        raise ValueError("Use a data table with 1–100,000 rows and at most 200 columns.")
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("Column names must be unique.")
    return frame, name, sheets


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


def normalize(frame, mapping, business, currency="USD", date_order="month", decimal="dot"):
    """Validate mapped source columns and build the normalized sales dataset."""
    if not isinstance(mapping, dict):
        raise ValueError("Confirm the column mapping first.")
    mapped = {k: v for k, v in mapping.items() if k in FIELDS and v}
    if any(v not in frame.columns for v in mapped.values()):
        raise ValueError("A mapped column is missing from this worksheet.")
    if len(set(mapped.values())) != len(mapped):
        raise ValueError("Map a source column to one field only.")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Enter a three-letter currency code, for example USD.")
    result = pd.DataFrame(index=frame.index)
    warnings = []
    numeric_fields = {"Quantity", "Unit_Price", "Gross_Sales", "Discount_Amount", "Net_Sales", "Unit_COGS", "Total_COGS", "Gross_Profit", "Hour"}
    # Copy mapped columns into normalized names, converting numeric fields first.
    for key, column in mapped.items():
        if key in numeric_fields:
            result[key] = numeric(frame[column], key, decimal)
        elif key != "Date":
            result[key] = frame[column].fillna("").astype(str).str.strip()
    if "Date" in mapped:
        source = frame[mapped["Date"]]
        if pd.api.types.is_numeric_dtype(source) or source.map(lambda v: isinstance(v, (int, float))).all():
            raise ValueError("Format the date column as dates, rather than raw spreadsheet serial numbers.")
        # Keep parsed dates as plain Python values to avoid Python 3.14/pandas crashes.
        dates = [parse_date_value(value, date_order == "day") for value in source.tolist()]
        if any(value is None for value in dates):
            raise ValueError("The mapped date column contains blank or invalid dates. Choose the date order or correct the file.")
        result["Date"] = [value.strftime("%Y-%m-%d") for value in dates]
        hours = [value.hour for value in dates]
        if "Hour" not in result and any(hour != 0 for hour in hours):
            result["Hour"] = hours
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
        result["Hour"] = result["Time"].map(time_hour)
    if "Hour" in result:
        hours = pd.to_numeric(result["Hour"], errors="coerce")
        if hours.isna().any() or ((hours < 0) | (hours > 23) | (hours % 1 != 0)).any():
            raise ValueError("Hour values must be whole numbers from 0 to 23, and Time values must use 24-hour notation.")
        result["Hour"] = hours.astype(int)
    if "Gross_Sales" not in result and {"Unit_Price", "Quantity"} <= set(result):
        result["Gross_Sales"] = (result.Quantity * result.Unit_Price).round(2)
    if "Net_Sales" not in result:
        # Net sales is required; derive it only when the source provides enough data.
        if "Gross_Sales" not in result:
            raise ValueError("Map net sales, gross sales, or both quantity and unit price.")
        result["Net_Sales"] = (result.Gross_Sales - result.get("Discount_Amount", 0)).round(2)
        if "Discount_Amount" not in result:
            warnings.append("No discounts column was provided: net sales is treated as gross sales. Returns and tax treatment depend on your source.")
    if {"Gross_Sales", "Discount_Amount"} <= set(result) and ((result.Gross_Sales-result.Discount_Amount-result.Net_Sales).abs() > .011).any():
        raise ValueError("Gross sales minus discounts does not match net sales. Confirm that discounts are line amounts, and revenue excludes tax and tips.")
    if "Total_COGS" not in result and {"Unit_COGS", "Quantity"} <= set(result):
        result["Total_COGS"] = (result.Unit_COGS * result.Quantity).round(2)
    if "Total_COGS" in result:
        # Gross profit can be supplied or calculated from net sales minus product costs.
        profit = (result.Net_Sales-result.Total_COGS).round(2)
        if "Gross_Profit" in result and ((result.Gross_Profit-profit).abs() > .011).any():
            raise ValueError("Mapped gross profit does not match net sales minus product costs.")
        result["Gross_Profit"] = profit
    for field, default in {"Product_Name":"All sales", "Category":"Uncategorized", "Employee_Name":"Not provided", "Weather":"Not provided"}.items():
        if field not in result:
            result[field] = default
        result[field] = result[field].replace("", default)
    if "Weather" in mapped:
        result["Weather"] = result.Weather.str.replace(r"\s+\d.*$", "", regex=True)
    orders_valid = "Transaction_ID" in result and not result.Transaction_ID.eq("").any()
    if orders_valid:
        # Order IDs are trusted only if each ID has one date/time/payment grouping.
        result["Order_Key"] = result.Transaction_ID + "|" + result.get("Store_Location", pd.Series("", index=result.index))
        for field in ("Date", "Time", "Payment_Method"):
            if field in result and (result.groupby("Order_Key")[field].nunique() > 1).any():
                orders_valid = False
        if not orders_valid:
            warnings.append("Some order IDs span different dates, times, or payment methods. Order count and average order value are disabled until grouping is verified.")
    if frame.duplicated().any():
        warnings.append(f"{int(frame.duplicated().sum())} exact duplicate source rows were found. They are retained; verify whether they represent distinct sales.")
    if (result.Net_Sales < 0).any():
        warnings.append("Negative sales are included in totals. Pie charts are replaced with a contribution list when category totals are negative.")
    if "Gross_Profit" not in result:
        warnings.append("Cost and gross profit were not supplied: profit and margin metrics are unavailable.")
    warnings.append("Totals describe recorded data. Verify coverage before inferring demand, staffing needs, or causes. Gross profit excludes operating expenses.")
    capabilities = {key: key in result for key in ("Date", "Hour", "Quantity", "Gross_Profit", "Gross_Sales", "Discount_Amount")}
    capabilities.update({"orders": orders_valid, "product": "Product_Name" in mapped, "category": "Category" in mapped, "employee": "Employee_Name" in mapped, "weather": "Weather" in mapped})
    # The browser receives records plus capability flags so it can hide unsupported views.
    return {"rows": json.loads(result.to_json(orient="records")), "capabilities": capabilities, "warnings": warnings, "business": str(business)[:60], "currency": currency, "sourceRows": len(frame), "dateMin": result.Date.min() if "Date" in result else None, "dateMax": result.Date.max() if "Date" in result else None}


def local_models():
    """List downloaded local Ollama models only."""
    with LOCAL_HTTP.open(OLLAMA + "/api/tags", timeout=3) as response:
        models = json.load(response).get("models", [])
    # Cloud-linked models are excluded; this app never signs in or downloads models.
    return [m["name"] for m in models if not m.get("remote_host") and not m.get("remote_model") and ":cloud" not in m["name"] and "cloud" not in m.get("details", {}).get("families", [])]


def compact_money(value, currency):
    """Format money for the plain-English AI summary."""
    if value is None:
        # Say "not available" instead of giving the model a fake zero.
        return "not available"
    return f"{currency} {float(value):,.2f}"


def item_list(items, currency, metric="netSales", limit=5):
    """Summarize ranked products/categories for Ollama without exposing JSON."""
    if not items:
        return "not available"
    parts = []
    for item in items[:limit]:
        name = str(item.get("name", "Unnamed"))
        value = item.get(metric)
        units = item.get("units")
        text = f"{name}: {compact_money(value, currency)}"
        if units is not None:
            text += f", {units:g} units"
        margin = item.get("grossMarginPercent")
        if margin is not None:
            text += f", {margin:g}% margin"
        parts.append(text)
    return "; ".join(parts)


def business_summary(facts):
    """Turn calculated dashboard facts into a plain-English model prompt."""
    currency = facts.get("currency", "USD")
    # This summary gives Ollama readable business facts instead of raw JSON.
    lines = [
        f"Business type: {facts.get('business', 'business')}.",
        f"Current filters: {facts.get('filters', {})}.",
        f"Selected data: {facts.get('selectedRows', 0):,} rows from {facts.get('daysCovered') or 'unknown'} recorded days.",
        f"Net sales: {compact_money(facts.get('netSales'), currency)}.",
        f"Gross profit: {compact_money(facts.get('grossProfit'), currency)}; gross margin: {facts.get('grossMarginPercent') if facts.get('grossMarginPercent') is not None else 'not available'}%.",
        f"Units sold: {facts.get('units') if facts.get('units') is not None else 'not available'}.",
        f"Average daily net sales: {compact_money(facts.get('averageDailyNetSales'), currency)}.",
        f"Discount rate: {facts.get('discountRatePercent') if facts.get('discountRatePercent') is not None else 'not available'}%.",
        f"Matching orders: {facts.get('matchingOrders') if facts.get('matchingOrders') is not None else 'not available'}; selected revenue per matching order: {compact_money(facts.get('selectedRevenuePerMatchingOrder'), currency)}.",
        f"Top products by revenue: {item_list(facts.get('topProducts', []), currency)}.",
        f"Top products by units: {item_list(facts.get('topProductsByUnits', []), currency)}.",
        f"Top products by gross profit: {item_list(facts.get('topProductsByGrossProfit', []), currency, metric='grossProfit')}.",
        f"Highest-margin products: {item_list(facts.get('topProductsByMargin', []), currency)}.",
        f"Lowest-margin products: {item_list(facts.get('bottomProductsByMargin', []), currency)}.",
        f"Lowest products by revenue: {item_list(facts.get('bottomProductsByRevenue', []), currency)}.",
        f"Lowest products by units: {item_list(facts.get('bottomProductsByUnits', []), currency, metric='netSales')}.",
        f"Top categories by revenue: {item_list(facts.get('topCategories', []), currency)}.",
        f"Top categories by units: {item_list(facts.get('topCategoriesByUnits', []), currency)}.",
        f"Highest-margin categories: {item_list(facts.get('topCategoriesByMargin', []), currency)}.",
        f"Lowest categories by revenue: {item_list(facts.get('bottomCategoriesByRevenue', []), currency)}.",
        f"Payment methods by revenue: {item_list(facts.get('topPayments', []), currency)}.",
        f"Store locations by revenue: {item_list(facts.get('topLocations', []), currency)}.",
        f"Employees by handled revenue: {item_list(facts.get('topEmployees', []), currency)}.",
    ]
    trend = facts.get("trendComparison")
    if isinstance(trend, dict):
        lines.append(f"Trend: second-half sales were {trend.get('secondVsFirstPercent')}% versus the first half.")
    if facts.get("topDays"):
        days = "; ".join(f"{d.get('date')}: {compact_money(d.get('netSales'), currency)}" for d in facts["topDays"][:3])
        lines.append(f"Highest recorded days: {days}.")
    if facts.get("bottomDays"):
        days = "; ".join(f"{d.get('date')}: {compact_money(d.get('netSales'), currency)}" for d in facts["bottomDays"][:3])
        lines.append(f"Lowest recorded days: {days}.")
    if facts.get("topWeeks"):
        weeks = "; ".join(f"{d.get('week')}: {compact_money(d.get('netSales'), currency)}" for d in facts["topWeeks"][:3])
        lines.append(f"Highest weeks: {weeks}.")
    if facts.get("topMonths"):
        months = "; ".join(f"{d.get('month')}: {compact_money(d.get('netSales'), currency)}" for d in facts["topMonths"][:3])
        lines.append(f"Highest months: {months}.")
    if facts.get("weekdays"):
        weekdays = "; ".join(f"{d.get('weekday')}: {compact_money(d.get('netSales'), currency)}" for d in facts["weekdays"][:7])
        lines.append(f"Weekday sales: {weekdays}.")
    if facts.get("periods"):
        periods = "; ".join(f"{d.get('name')}: {compact_money(d.get('netSales'), currency)}" for d in facts["periods"])
        lines.append(f"Time-of-day sales: {periods}.")
    if facts.get("topHours"):
        hours = "; ".join(f"{d.get('hour')}:00: {compact_money(d.get('netSales'), currency)}" for d in facts["topHours"][:5])
        lines.append(f"Top hours by revenue: {hours}.")
    discount = facts.get("discountSummary")
    if isinstance(discount, dict):
        lines.append(f"Discounted revenue: {compact_money(discount.get('discountedRevenue'), currency)}; undiscounted revenue: {compact_money(discount.get('undiscountedRevenue'), currency)}; discounted order share: {discount.get('discountedOrderPercent') if discount.get('discountedOrderPercent') is not None else 'not available'}%.")
    if facts.get("productGrowth"):
        growth = "; ".join(f"{d.get('name')}: {compact_money(d.get('change'), currency)}" for d in facts["productGrowth"][:3])
        lines.append(f"Products with strongest recent increase: {growth}.")
    if facts.get("productDeclines"):
        decline = "; ".join(f"{d.get('name')}: {compact_money(d.get('change'), currency)}" for d in facts["productDeclines"][:3])
        lines.append(f"Products with largest recent decline: {decline}.")
    warnings = facts.get("limitations") or []
    if warnings:
        lines.append("Important data limits: " + " ".join(str(w) for w in warnings[:4]))
    return "\n".join(lines)


def answer_mentions_internals(answer):
    """Detect when a small local model leaks implementation wording."""
    return bool(re.search(r"\b(json|array|arrays|key|keys|field|fields|object|code|sort|sorting|bottomProducts|topProducts|calculated_facts|deterministic_dashboard_answer)\b", answer, re.I))


def explain(payload):
    """Ask Ollama to rewrite calculated facts as a plain business explanation."""
    model = payload.get("model", "")
    if model not in local_models():
        raise ValueError("Choose a downloaded local model. Cloud models are not supported in this free app.")
    question = str(payload.get("question", ""))[:1500]
    facts = payload.get("facts", {})
    calculated_answer = str(payload.get("calculatedAnswer", ""))[:2500]
    if not isinstance(facts, dict) or len(json.dumps(facts)) > 48000:
        raise ValueError("The selected data summary is too large.")
    # Ollama gets business language, not raw dashboard JSON, to avoid technical replies.
    summary = business_summary(facts)
    system = "You are a plain-language business insights assistant for a local sales dashboard. Speak to a small business owner, not a programmer. Answer the question directly in normal business language. Use only the supplied dashboard answer and business summary. Treat the dashboard answer as the primary answer when it is present; you may make it clearer, but do not contradict it. Never mention JSON, arrays, keys, fields, sorting, code, data structures, or implementation details. Never tell the user to inspect anything technical. Do not invent figures, causes, forecasts, or missing metrics. For business health or success questions, give a cautious judgment based on sales, margin, trend, orders, discounts, and data limits, and say what outside information is still needed. For next-step questions, give 2-4 practical actions. Keep the answer concise and readable."
    user_content = f"Question: {question}\n\nDashboard answer to use first:\n{calculated_answer or 'No deterministic answer available.'}\n\nBusiness summary:\n{summary}"
    body = {"model": model, "messages": [{"role":"system", "content":system}, {"role":"user", "content":user_content}], "stream": False, "options":{"temperature":.1, "num_predict":360, "num_ctx":8192}}
    if model.lower().startswith("qwen3"):
        body["think"] = False
    request = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    with LOCAL_HTTP.open(request, timeout=120) as response:
        # Ollama returns a chat-style response; the message content is the answer text.
        answer = json.load(response).get("message", {}).get("content", "").strip()
    if not answer:
        raise ValueError("The local model returned no answer. Try a different downloaded model.")
    if calculated_answer and answer_mentions_internals(answer):
        # If the model talks like a programmer, fall back to the app's deterministic answer.
        answer = calculated_answer
    return {"answer": answer, "mode":"Local AI", "model":model}


class Handler(BaseHTTPRequestHandler):
    """Small local HTTP API for the browser UI."""

    def send_json(self, result, status=200):
        """Send one JSON response back to the browser."""
        body = json.dumps(result, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Serve dashboard files and small read-only API endpoints."""
        # Serve the static dashboard files and lightweight local API endpoints.
        if self.path == "/api/session":
            self.send_json({"token":TOKEN})
        elif self.path == "/api/models":
            try:
                self.send_json({"models":local_models()})
            except Exception:
                self.send_json({"models":[], "message":"Ollama is not running. Calculated insights still work."})
        elif self.path.split("?")[0] == "/" or self.path.split("?")[0] == "/index.html":
            # In production, serve the Vite build. Before building, fall back to the source index.
            source = DIST / "index.html" if (DIST / "index.html").exists() else ROOT / "index.html"
            raw = source.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.split("?")[0].startswith("/assets/") and DIST.exists():
            # Built JavaScript and CSS files live under dist/assets.
            asset = (DIST / self.path.split("?")[0].lstrip("/")).resolve()
            if DIST.resolve() not in asset.parents or not asset.exists():
                self.send_json({"error":"Not found"}, 404)
                return
            raw = asset.read_bytes()
            suffix = asset.suffix.lower()
            content_type = "text/javascript" if suffix == ".js" else "text/css" if suffix == ".css" else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_json({"error":"Not found"}, 404)

    def do_POST(self):
        """Handle uploaded data, dashboard analysis, and AI explanations."""
        # All POST actions require the per-process token from /api/session.
        try:
            if self.headers.get("X-Dashboard-Token") != TOKEN:
                raise ValueError("Reload this local dashboard before uploading.")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > LIMIT * 1.5:
                raise ValueError("Upload size exceeds the 20 MB file limit.")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/profile":
                # Inspect columns and suggest mappings before analysis.
                frame, name, sheets = frame_from_payload(payload)
                self.send_json({"filename":name,"rows":len(frame),"columns":frame.columns.tolist(),"sheets":sheets,"mapping":suggest_mapping(frame.columns),"preview":json.loads(frame.head(5).to_json(orient="records"))})
            elif self.path == "/api/analyze":
                # Normalize the selected sheet/file into dashboard-ready records.
                frame, name, _ = frame_from_payload(payload)
                result = normalize(frame, payload.get("mapping"), payload.get("business", "Other business"), payload.get("currency", "USD"), payload.get("dateOrder", "month"), payload.get("decimal", "dot"))
                result["filename"] = name
                self.send_json(result)
            elif self.path == "/api/explain":
                # Optional local AI explanation through Ollama.
                self.send_json(explain(payload))
            else:
                self.send_json({"error":"Not found"}, 404)
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else "The file or local model could not be read. Check the file format, selected worksheet, and local model setup."
            self.send_json({"error":message}, 400)

    def log_message(self, format, *args):
        """Silence default request logging for privacy and cleaner terminal output."""
        # Do not log uploaded data or questions.
        pass


if __name__ == "__main__":
    # Start the dashboard as a local-only website on this computer.
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Free Business Dashboard: http://127.0.0.1:{args.port}\nNo paid APIs. Uploads stay in memory on this computer. Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
