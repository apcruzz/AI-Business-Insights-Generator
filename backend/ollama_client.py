# Local model transport: explain rewrites existing facts; chat supports the row-query analyst.
"""Plain-language Ollama integration for dashboard insight explanations."""
from __future__ import annotations

import json
import re
import urllib.request

from backend.config import OLLAMA_URL

# Bypass system proxies for requests to the local Ollama service.
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def local_models():
    """List downloaded local Ollama models only."""
    with LOCAL_HTTP.open(OLLAMA_URL + "/api/tags", timeout=3) as response:
        models = json.load(response).get("models", [])
    # Cloud-linked models are excluded; this app never signs in or downloads models.
    return [
        model["name"]
        for model in models
        if not model.get("remote_host")
        and not model.get("remote_model")
        and ":cloud" not in model["name"]
        and "cloud" not in model.get("details", {}).get("families", [])
    ]


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
    # Append optional summaries only when the frontend supplied the corresponding facts.
    trend = facts.get("trendComparison")
    if isinstance(trend, dict):
        lines.append(f"Trend: second-half sales were {trend.get('secondVsFirstPercent')}% versus the first half.")
    order_stats = facts.get("orderStats")
    if isinstance(order_stats, dict):
        lines.append(
            f"Order facts: average order value {compact_money(order_stats.get('averageOrderValue'), currency)}; "
            f"median order value {compact_money(order_stats.get('medianOrderValue'), currency)}; "
            f"top 3 orders contribute {order_stats.get('percentRevenueTop3Orders') if order_stats.get('percentRevenueTop3Orders') is not None else 'not available'}%; "
            f"average lines per order {order_stats.get('averageLinesPerOrder') if order_stats.get('averageLinesPerOrder') is not None else 'not available'}."
        )
    if facts.get("topOrders"):
        orders = "; ".join(
            f"{compact_money(order.get('netSales'), currency)} across {order.get('lines')} lines"
            for order in facts["topOrders"][:3]
        )
        lines.append(f"Largest matching orders: {orders}.")
    if facts.get("productPairs"):
        pairs = "; ".join(f"{pair.get('name')}: {pair.get('orders')} orders" for pair in facts["productPairs"][:3])
        lines.append(f"Common product combinations: {pairs}.")
    # Describe date coverage and time rankings without treating absent days as zero sales.
    date_summary = facts.get("dateSummary")
    if isinstance(date_summary, dict):
        lines.append(
            f"Date coverage: {date_summary.get('earliestDate')} to {date_summary.get('latestDate')}; "
            f"{date_summary.get('monthsCovered')} recorded months; "
            f"average recorded business-day revenue {compact_money(date_summary.get('averageBusinessDayRevenue'), currency)}; "
            f"daily variation {date_summary.get('dailySalesVariationPercent') if date_summary.get('dailySalesVariationPercent') is not None else 'not available'}%."
        )
    if facts.get("topDays"):
        days = "; ".join(f"{day.get('date')}: {compact_money(day.get('netSales'), currency)}" for day in facts["topDays"][:3])
        lines.append(f"Highest recorded days: {days}.")
    if facts.get("bottomDays"):
        days = "; ".join(f"{day.get('date')}: {compact_money(day.get('netSales'), currency)}" for day in facts["bottomDays"][:3])
        lines.append(f"Lowest recorded days: {days}.")
    if facts.get("topWeeks"):
        weeks = "; ".join(f"{week.get('week')}: {compact_money(week.get('netSales'), currency)}" for week in facts["topWeeks"][:3])
        lines.append(f"Highest weeks: {weeks}.")
    if facts.get("topMonths"):
        months = "; ".join(f"{month.get('month')}: {compact_money(month.get('netSales'), currency)}" for month in facts["topMonths"][:3])
        lines.append(f"Highest months: {months}.")
    if facts.get("weekdays"):
        weekdays = "; ".join(f"{weekday.get('weekday')}: {compact_money(weekday.get('netSales'), currency)}" for weekday in facts["weekdays"][:7])
        lines.append(f"Weekday sales: {weekdays}.")
    if facts.get("periods"):
        periods = "; ".join(f"{period.get('name')}: {compact_money(period.get('netSales'), currency)}" for period in facts["periods"])
        lines.append(f"Time-of-day sales: {periods}.")
    if facts.get("topHours"):
        hours = "; ".join(f"{hour.get('hour')}:00: {compact_money(hour.get('netSales'), currency)}" for hour in facts["topHours"][:5])
        lines.append(f"Top hours by revenue: {hours}.")
    hour_summary = facts.get("hourSummary")
    if isinstance(hour_summary, dict):
        lines.append(
            f"Hour facts: revenue per recorded sales hour {compact_money(hour_summary.get('revenuePerRecordedOperatingHour'), currency)}; "
            f"units per recorded sales hour {hour_summary.get('unitsPerRecordedOperatingHour') if hour_summary.get('unitsPerRecordedOperatingHour') is not None else 'not available'}; "
            f"typical first sale hour {hour_summary.get('typicalFirstSaleHour') if hour_summary.get('typicalFirstSaleHour') is not None else 'not available'}; "
            f"typical last sale hour {hour_summary.get('typicalLastSaleHour') if hour_summary.get('typicalLastSaleHour') is not None else 'not available'}."
        )
    if facts.get("weather"):
        weather = "; ".join(
            f"{weather_row.get('name')}: {compact_money(weather_row.get('averageDailyNetSales'), currency)} average per recorded day"
            for weather_row in facts["weather"][:3]
        )
        lines.append(f"Weather comparison: {weather}.")
    # Add discount and product-change context, then preserve data-quality warnings.
    discount = facts.get("discountSummary")
    if isinstance(discount, dict):
        lines.append(
            f"Discounted revenue: {compact_money(discount.get('discountedRevenue'), currency)}; "
            f"undiscounted revenue: {compact_money(discount.get('undiscountedRevenue'), currency)}; "
            f"discounted order share: {discount.get('discountedOrderPercent') if discount.get('discountedOrderPercent') is not None else 'not available'}%."
        )
    if facts.get("productGrowth"):
        growth = "; ".join(f"{item.get('name')}: {compact_money(item.get('change'), currency)}" for item in facts["productGrowth"][:3])
        lines.append(f"Products with strongest recent increase: {growth}.")
    if facts.get("productDeclines"):
        decline = "; ".join(f"{item.get('name')}: {compact_money(item.get('change'), currency)}" for item in facts["productDeclines"][:3])
        lines.append(f"Products with largest recent decline: {decline}.")
    warnings = facts.get("limitations") or []
    if warnings:
        lines.append("Important data limits: " + " ".join(str(warning) for warning in warnings[:4]))
    return "\n".join(lines)


def answer_mentions_internals(answer):
    """Detect when a small local model leaks implementation wording."""
    return bool(
        re.search(
            r"\b(json|array|arrays|key|keys|field|fields|object|code|sort|sorting|bottomProducts|topProducts|calculated_facts|deterministic_dashboard_answer)\b",
            answer,
            re.I,
        )
    )


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
    system = (
        "You are a plain-language business insights assistant for a local sales dashboard. "
        "Speak to a small business owner, not a programmer. Answer the question directly in normal business language. "
        "Use only the supplied dashboard answer and business summary. Treat the dashboard answer as the primary answer when it is present; "
        "you may make it clearer, but do not contradict it. Never mention JSON, arrays, keys, fields, sorting, code, data structures, "
        "or implementation details. Never tell the user to inspect anything technical. Do not invent figures, causes, forecasts, or missing metrics. "
        "For business health or success questions, give a cautious judgment based on sales, margin, trend, orders, discounts, and data limits, "
        "and say what outside information is still needed. For next-step questions, give 2-4 practical actions. Keep the answer concise and readable."
    )
    user_content = (
        f"Question: {question}\n\n"
        f"Dashboard answer to use first:\n{calculated_answer or 'No deterministic answer available.'}\n\n"
        f"Business summary:\n{summary}"
    )
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 360, "num_ctx": 8192},
    }
    if model.lower().startswith("qwen3"):
        body["think"] = False
    request = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with LOCAL_HTTP.open(request, timeout=120) as response:
        # Ollama returns a chat-style response; the message content is the answer text.
        answer = json.load(response).get("message", {}).get("content", "").strip()
    if not answer:
        raise ValueError("The local model returned no answer. Try a different downloaded model.")
    if calculated_answer and answer_mentions_internals(answer):
        # If the model talks like a programmer, fall back to the app's deterministic answer.
        answer = calculated_answer
    return {"answer": answer, "mode": "Local AI", "model": model}


def chat(model, messages, *, format=None, timeout=60, num_predict=650):
    """Shared local chat transport; callers validate the downloaded model first."""
    # Build a non-streaming request so callers receive one complete model action.
    body = {'model': model, 'messages': messages, 'stream': False,
            'options': {'temperature': 0, 'num_predict': num_predict, 'num_ctx': 8192}}
    # The analyst supplies a JSON schema here so model actions can be parsed and dispatched.
    if format is not None:
        body['format'] = format
    if model.lower().startswith('qwen3'):
        body['think'] = False
    request = urllib.request.Request(OLLAMA_URL + '/api/chat', data=json.dumps(body, allow_nan=False).encode(),
                                     headers={'Content-Type':'application/json'})
    # Wait within the caller deadline and extract the assistant message from Ollama JSON.
    with LOCAL_HTTP.open(request, timeout=timeout) as response:
        answer = json.load(response).get('message', {}).get('content', '').strip()
    if not answer:
        raise ValueError('The local model returned no answer.')
    return answer
