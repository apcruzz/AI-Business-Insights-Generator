import assert from 'node:assert/strict';
import {test} from 'node:test';
import {chartVariantData, renderChartVariant} from '../src/chart-variants.js';

const meta = {business: 'Cafe', currency: 'USD', capabilities: {Quantity: true}};
const render = (id, rows, type, layout) => renderChartVariant(id, rows, meta, '#5489ff', value => `$${value}`, type, layout);

test('Recommended and unknown choices delegate to the existing specialized renderers', () => {
  assert.equal(render('category', [], 'auto'), null);
  assert.equal(render('category', [], 'unknown'), null);
});
test('Chart variants retain quantities and weighted margins instead of silently using sales', () => {
  const rows = [{Product_Name: 'Tea', Quantity: 3, Net_Sales: 10, Gross_Profit: 5},
    {Product_Name: 'Tea', Quantity: 1, Net_Sales: 90, Gross_Profit: 9}];
  assert.deepEqual(chartVariantData('products', rows, meta).items, [['Tea', 4]]);
  const data = chartVariantData('profitability', rows, meta);
  assert.equal(data.unit, 'percent');
  assert.ok(Math.abs(data.items[0][1] - 14) < .001);
  assert.match(render('profitability', rows, 'pie'), /do not represent shares of total sales/);
});
test('Stacked and heatmap variants disclose aggregation and retain event deduplication', () => {
  const delivery = {Delivery_ID: 'D1', Delivery_Outcome: 'On time', Date: '2026-01-05'};
  const data = chartVariantData('delivery', [delivery, delivery, {...delivery, Delivery_ID: 'D2', Delivery_Outcome: 'Late'}], meta);
  assert.deepEqual(data.items, [['2026-01', 2]]);
  assert.match(data.note, /Stacked series are combined/);
  const booking = {Appointment_ID: 'A1', Appointment_Start: '2026-01-05T09:00:00', Appointment_Day: '2026-01-05', Appointment_Hour: 9};
  const bookings = chartVariantData('bookings', [booking, booking, {...booking, Appointment_ID: 'A2', Appointment_Status: 'Cancelled'}], meta);
  assert.deepEqual(bookings.items[0], ['Mon', 1]);
  assert.equal(bookings.items.reduce((n, row) => n + row[1], 0), 1);
  assert.match(bookings.note, /Hours are combined into weekday totals/);
});
test('Single-group pie and doughnut render a complete circle; zero totals explain the empty chart', () => {
  const rows = [{Category: 'Only category', Net_Sales: 10}];
  assert.match(render('category', rows, 'pie'), /<circle cx="130" cy="130" r="120"/);
  assert.match(render('category', rows, 'doughnut'), /r="66" fill="white"/);
  assert.match(render('category', [{Category: 'Zero', Net_Sales: 0}], 'pie'), /no positive values/);
});
test('Negative groups invalidate share charts even when outside the first twelve', () => {
  const rows = Array.from({length: 13}, (_, i) => ({Category: `Category ${i}`, Net_Sales: i === 12 ? -1 : 10}));
  assert.match(render('category', rows, 'pie'), /need nonnegative values/);
  assert.match(render('category', rows, 'doughnut'), /need nonnegative values/);
  assert.match(render('category', rows, 'bar'), /Showing the first 12 of 13/);
});
test('Bounded charts disclose omitted groups and preserve date caveats', () => {
  const rows = Array.from({length: 13}, (_, i) => ({Date: `2026-01-${String(i + 1).padStart(2, '0')}`, Net_Sales: 10}));
  for (const type of ['bar', 'line', 'pie', 'doughnut']) {
    const html = render('trend', rows, type);
    assert.match(html, /first 12 of 13/);
    assert.match(html, /gaps do not mean zero sales/);
  }
  assert.match(render('trend', rows, 'pie'), /Shares use the displayed groups/);
});
test('Uploaded labels are escaped in SVG tooltips, accessibility labels, and legends', () => {
  for (const type of ['bar', 'line', 'pie', 'doughnut']) {
    const html = render('category', [{Category: '<img src=x onerror=bad>', Net_Sales: 10}], type);
    assert.ok(!html.includes('<img'));
    assert.match(html, /&lt;img/);
  }
});
test('Bar and line variants use the responsive renderer and retain negative amounts', () => {
  const rows = [{Category: 'Refund', Net_Sales: -50}, {Category: 'Sales', Net_Sales: 100}];
  for (const type of ['bar', 'line']) {
    const html = render('category', rows, type, {width: 300, height: 230, fontSize: 12});
    assert.match(html, /viewBox="0 0 300 230"/);
    assert.match(html, /Refund: \$-50/);
    assert.ok(!/NaN|Infinity/.test(html));
  }
});
