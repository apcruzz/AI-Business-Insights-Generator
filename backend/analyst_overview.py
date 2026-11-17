"""Backend-owned overview prompt and calculations over the complete filtered dataset."""

OVERVIEW_QUESTION = '''Give the business owner an initial overview and practical recommendations for the current selection.
Use short sections: Business overview; Strengths and concerns; Recommended next steps; Data limitations.
Describe overall net sales and, when available, gross profit and weighted gross margin. Name the leading recorded products or categories and describe the recorded sales pattern without claiming causation or seasonality.
Give specific actions tied to the supplied calculations, explain what to measure, and distinguish suggestions from established facts. Discuss only available evidence. Do not invent targets, percentage changes, inventory, customers, overhead or net profit. Missing costs mean profit is unavailable. Partial periods and absent dates do not establish a trend.
Do not repeat a generic checklist or merely list rankings. Keep the answer concise and useful. All numeric claims must appear in the verified calculations. The supporting calculations will be visible below the answer.'''


def overview_queries(columns):
    """Fixed aggregates using reviewed normalized fields, excluding raw source fields."""
    totals = ['COUNT(*) AS sales_lines', 'ROUND(SUM(Net_Sales),2) AS net_sales']
    if 'Date' in columns:
        totals += ['MIN(Date) AS first_recorded_date', 'MAX(Date) AS last_recorded_date',
                   'COUNT(DISTINCT Date) AS recorded_days']
    if 'Order_Key' in columns:
        totals += ['COUNT(DISTINCT Order_Key) AS orders']
    if 'Gross_Profit' in columns:
        totals += ['CASE WHEN COUNT(Gross_Profit)=COUNT(*) THEN ROUND(SUM(Gross_Profit),2) END AS gross_profit',
                   'CASE WHEN COUNT(Gross_Profit)=COUNT(*) AND SUM(Net_Sales)>0 THEN ROUND(SUM(Gross_Profit)/SUM(Net_Sales)*100,2) END AS gross_margin_percent']
    queries = ['SELECT ' + ', '.join(totals) + ' FROM sales']
    for column in ('Product_Name', 'Category', 'Date'):
        if column not in columns:
            continue
        # At most a dozen recorded calendar months; never pad absent dates with zero.
        dimension = "strftime('%Y-%m',Date)" if column == 'Date' else f'"{column}"'
        order = 'dimension DESC' if column == 'Date' else 'net_sales DESC, dimension'
        queries.append(f'SELECT {dimension} AS dimension, COUNT(*) AS sales_lines, ROUND(SUM(Net_Sales),2) AS net_sales FROM sales GROUP BY {dimension} ORDER BY {order} LIMIT 12')
    return queries
