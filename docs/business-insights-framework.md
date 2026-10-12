# Business Insights Framework

This framework connects dashboard signals to plain-language insights and practical next actions. It is designed for sales/order dashboards where the available data may include revenue, discounts, products, categories, dates, hours, employees, payment methods, locations, costs, and gross profit.

Use this pattern:

1. **Signal:** What changed or stands out in the data.
2. **Insight:** What the signal may mean for the business.
3. **Confidence:** Whether the dashboard has enough data to support the interpretation.
4. **Action:** What the owner or manager should check next.
5. **Missing data:** What would make the answer stronger.

## Core Rules

- Treat dashboard answers as evidence, not proof of cause.
- State the observed fact first, then the likely business meaning.
- Avoid making forecasts or guarantees unless targets and historical patterns are available.
- Separate sales performance from profitability. High revenue does not always mean high profit.
- Explain missing data plainly. For example: inventory decisions need stock-on-hand; net profit needs operating expenses.
- When data is filtered, say the answer applies only to the selected records.

## Common Scenarios

### 1. Declining Sales

**Signals**
- Second-half sales are lower than first-half sales.
- Recent weeks or months show lower revenue.
- Top products or categories have negative sales change.
- Fewer matching orders, lower average order value, or fewer units sold.

**Possible Insights**
- Demand may be softening.
- A key product or category may be losing momentum.
- The business may be affected by seasonality, stockouts, pricing, marketing, or operating hours.

**Potential Actions**
- Compare the decline by product, category, day, and hour.
- Check whether top products were in stock during the decline.
- Review recent discounts, promotions, prices, and menu/product changes.
- Compare order count versus average order value to see whether fewer customers or smaller baskets caused the drop.

**Missing Data That Helps**
- Inventory levels, marketing calendar, operating hours, customer traffic, local events, weather, and targets.

### 2. Customer Retention Issues

**Signals**
- Repeat-customer data is unavailable or declining.
- Order count drops while average order value stays stable.
- Sales depend heavily on new promotions or discounts.

**Possible Insights**
- The business may be attracting one-time buyers but not enough repeat customers.
- Discounts may be driving purchases without building loyalty.

**Potential Actions**
- Add customer ID or customer type to future data exports.
- Compare new versus repeat customers if customer data becomes available.
- Review loyalty offers, follow-up marketing, and product satisfaction.

**Missing Data That Helps**
- Customer IDs, first purchase date, repeat purchase count, acquisition source, loyalty membership, and customer feedback.

### 3. Product Concentration

**Signals**
- One product or the top five products represent a large share of revenue.
- A single category dominates sales.
- Top product revenue is high but margin is weak.

**Possible Insights**
- The business may rely heavily on a small number of products.
- Best sellers may be supporting the business, but they can also create risk if demand changes or supply is interrupted.

**Potential Actions**
- Protect stock availability for top products.
- Check margins on top products before promoting them further.
- Look for related products that can be bundled or featured.
- Investigate whether lower-selling products should be repositioned, repriced, or removed.

**Missing Data That Helps**
- Inventory, supplier lead times, spoilage, product availability, product views, and customer preferences.

### 4. Growth Opportunities

**Signals**
- Products with high margin and moderate or growing sales.
- Categories with strong revenue and healthy gross margin.
- Specific days or hours with strong demand.
- Products growing compared with the earlier period.

**Possible Insights**
- The business may have products worth promoting more heavily.
- Staffing, inventory, or marketing may be better aligned around high-demand times.

**Potential Actions**
- Feature high-margin products with proven demand.
- Ensure staffing and stock coverage during the best days and hours.
- Test bundles or upsells around top products.
- Use low-risk promotions on products with strong margin, not just high revenue.

**Missing Data That Helps**
- Marketing spend, inventory, customer segments, channel performance, and operating capacity.

### 5. Discount Dependency

**Signals**
- Discount rate is high.
- Discounted revenue is large compared with undiscounted revenue.
- Discounted sales have weaker gross margin.
- A large percentage of orders include discounts.

**Possible Insights**
- Sales may be relying too heavily on discounts.
- Discounts may be reducing profit even if revenue looks strong.

**Potential Actions**
- Compare discounted versus undiscounted margins.
- Identify products and categories receiving the most discounts.
- Reduce discounts on products that already sell well.
- Use discounts selectively on products with enough margin.

**Missing Data That Helps**
- Promotion calendar, coupon codes, campaign goals, customer acquisition cost, and repeat purchase behavior.

### 6. Low-Selling Products

**Signals**
- Product has the fewest units sold.
- Product has the lowest revenue.
- Product has low sales but high margin.
- Product has low sales and low margin.

**Possible Insights**
- Low sales may reflect low demand, poor placement, stockouts, price issues, or intentionally niche products.
- Low sales with high margin may be an opportunity.
- Low sales with low margin may be a removal or redesign candidate.

**Potential Actions**
- Check stock availability first.
- Review price, placement, description, and category fit.
- Compare margin before deciding to discount.
- Test a small promotion only if margin can support it.

**Missing Data That Helps**
- Inventory, product views, stockout history, customer feedback, and shelf/menu placement.

### 7. Profitability Concerns

**Signals**
- Gross margin is low.
- High-revenue products have low margin.
- Discounts are concentrated in low-margin products.
- Gross profit is unavailable because costs are missing.

**Possible Insights**
- Revenue may look healthy while profit is weak.
- Product cost or discounting may be limiting profitability.

**Potential Actions**
- Map product costs or gross profit if missing.
- Review pricing for high-revenue low-margin products.
- Reduce discounts on weak-margin items.
- Prioritize products with both demand and margin.

**Missing Data That Helps**
- Unit cost, total product cost, operating expenses, payroll, rent, utilities, and fees.

### 8. Timing and Staffing Opportunities

**Signals**
- Certain hours, weekdays, weeks, or months generate much higher sales.
- Average order value varies by hour or day.
- Morning, afternoon, or evening sales differ sharply.

**Possible Insights**
- Demand may be concentrated in specific operating windows.
- Staffing or inventory may be misaligned with demand.

**Potential Actions**
- Align staffing with high-demand hours.
- Prepare inventory before peak periods.
- Test offers during slower periods.
- Avoid reducing staff solely from sales totals without labor-hour data.

**Missing Data That Helps**
- Labor schedules, operating hours, foot traffic, wait times, and service capacity.

### 9. Location or Employee Differences

**Signals**
- One location leads revenue or margin.
- One employee handles more revenue or orders.
- Employee sales differ widely.

**Possible Insights**
- Store location performance may differ because of traffic, local demand, staffing, or inventory.
- Employee totals may reflect shift assignments, not productivity.

**Potential Actions**
- Compare locations by revenue, margin, and product mix.
- Do not judge employee productivity without hours worked and assigned shifts.
- Look for practices from high-performing locations that can transfer elsewhere.

**Missing Data That Helps**
- Labor hours, shift schedules, foot traffic, location size, and local marketing.

### 10. Data Quality and Reliability

**Signals**
- Duplicate rows exist.
- Missing costs or gross profit.
- Order IDs conflict across dates, times, or payment methods.
- Negative sales appear.
- Date or hour coverage may be incomplete.

**Possible Insights**
- Some metrics may be unreliable until data quality is fixed.
- Negative sales may be returns, refunds, corrections, or errors.

**Potential Actions**
- Review duplicate rows before trusting totals.
- Confirm order IDs represent real receipts/orders.
- Map missing cost, date, quantity, and product fields where possible.
- Investigate negative values and partial coverage.

**Missing Data That Helps**
- Clean source exports, consistent order IDs, complete date/time fields, and clear refund markers.

## Plain-Language Answer Template

Use this structure for AI responses:

```text
The main signal is [observed fact].

This may mean [business interpretation], but [important limitation].

Next, I would check:
1. [action tied to data]
2. [action tied to data]
3. [action tied to missing data or validation]
```

## Examples

**Declining Sales**

The main signal is that sales are lower in the second half of the selected period. This may mean demand is softening, but the dashboard cannot prove the cause by itself. Check which products declined most, whether top items were in stock, and whether promotions or operating hours changed.

**Product Concentration**

The top product contributes a large share of revenue. That product is important to protect, but relying on one item can be risky. Check its margin, stock availability, and whether related products can be bundled or promoted.

**Growth Opportunity**

The strongest opportunity is a product or category with both healthy sales and healthy margin. Promote that area carefully, make sure it stays in stock, and avoid discounting it unless the margin can support the promotion.

**Missing Data**

The dashboard cannot answer this reliably because the needed data is not mapped. Add the missing field, such as inventory, customer ID, sales target, labor hours, or operating expenses, then rerun the dashboard.
