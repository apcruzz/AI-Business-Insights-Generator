// PR #12's presentation choices over the same validated metrics as the current dashboards.
import {businessChartData, renderChartData} from './business-charts.js';
import {chartTitle} from './business-config.js';
import {esc, group, sum} from './dashboard-utils.js';

export const CHART_TYPES = ['auto', 'bar', 'line', 'pie', 'doughnut'];
export const chartTypeLabel = type => type === 'auto' ? 'Recommended' : type[0].toUpperCase() + type.slice(1);

export function chartVariantData(id, rows, meta) {
  const data = businessChartData(id, rows, meta.capabilities);
  if (data) {
    // A single-series variant must disclose the dimension collapsed from a stacked chart or heatmap.
    if (data.type === 'heatmap') {
      const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return {...data, items: days.map((day, index) => [day, data.items.filter(item => item[0] === index).reduce((total, item) => total + item[2], 0)]),
        note: data.note + ' Hours are combined into weekday totals for this chart type.'};
    }
    if (data.type === 'stacked') return {...data,
      items: data.items.map(item => [item[0], item.slice(1).reduce((total, value) => total + value, 0)]),
      note: (data.note ? data.note + ' ' : '') + 'Stacked series are combined into totals for this chart type.'};
    return data;
  }
  let items = [];
  let note = '';
  if (id === 'category') items = group(rows, 'Category').map(([name, items]) => [name, sum(items, 'Net_Sales')]).sort((a,b) => b[1]-a[1]);
  if (id === 'weekday') items = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((name, day) => [name,
    sum(rows.filter(row => (new Date(row.Date + 'T12:00:00Z').getUTCDay()+6)%7 === day), 'Net_Sales')]);
  if (id === 'weather') {
    items = group(rows, 'Weather').map(([name, items]) => [name, sum(items, 'Net_Sales') / new Set(items.map(row => row.Date)).size]);
    note = 'Average per recorded day; coverage and other factors can affect this comparison.';
  }
  if (id === 'staff') items = group(rows, 'Employee_Name').map(([name, items]) => [name, sum(items, 'Net_Sales')]).sort((a,b) => b[1]-a[1]);
  return {type: 'bars', items, unit: 'money', note};
}

export function renderChartVariant(id, rows, meta, color, money, type, layout = null) {
  // Null delegates Recommended to the existing specialized chart, including all preview styling.
  if (!CHART_TYPES.includes(type) || type === 'auto') return null;
  const data = chartVariantData(id, rows, meta);
  if (!data.items.length) return '<p class="chartNote">This chart type has no matching values.</p>';
  if (type === 'bar' || type === 'line') {
    const count = data.items.length;
    // Match the bounded comparison in PR #12 while explicitly describing omitted groups.
    const limited = count > 12 ? {items: data.items.slice(0, 12), note: `Showing the first 12 of ${count} groups. ${data.note}`} : data;
    return renderChartData({...data, ...limited, type: type === 'bar' ? 'bars' : 'line'}, chartTitle(id,meta.business), color, money, meta.currency, layout);
  }
  // Check every group before limiting the display; an omitted refund still makes a share chart invalid.
  if (data.items.some(([, value]) => value < 0)) return '<p class="chartNote">Pie and doughnut charts need nonnegative values. Choose a bar or line chart.</p>';
  const items = data.items.slice(0, 12), total = items.reduce((total, item) => total + item[1], 0);
  if (!total) return '<p class="chartNote">This chart has no positive values to show as a share.</p>';
  const format = value => data.unit === 'money' ? money(value) : `${Number(value.toFixed(1)).toLocaleString()}${data.unit === 'percent' ? '%' : ' ' + data.unit}`;
  const palette = [color, '#cb6b42', '#5689b1', '#a77ab0', '#b69b3c', '#708477', '#438dcc', '#d17c9a', '#6c8b45', '#a47c48', '#6171a8', '#7e858b'];
  let angle = -Math.PI/2;
  const slices = items.map(([name, value], index) => {
    if (!value) return '';
    const share = value/total, next = angle + share*Math.PI*2;
    const title = `<title>${esc(name)}: ${esc(format(value))} (${(share*100).toFixed(1)}%)</title>`;
    // A full circle cannot be represented by one SVG arc whose start and end points coincide.
    const shape = share > .999999
      ? `<circle cx="130" cy="130" r="120" fill="${palette[index]}">${title}</circle>`
      : `<path d="M130 130 L${130+120*Math.cos(angle)} ${130+120*Math.sin(angle)} A120 120 0 ${share>.5?1:0} 1 ${130+120*Math.cos(next)} ${130+120*Math.sin(next)} Z" fill="${palette[index]}" stroke="white" stroke-width="1">${title}</path>`;
    angle = next;
    return shape;
  }).join('');
  const notes = [data.note];
  if (data.items.length > 12) notes.push(`Showing the first 12 of ${data.items.length} groups. Shares use the displayed groups.`);
  if (['percent', 'hours'].includes(data.unit) || id === 'weather') notes.push('Shares compare the displayed metric values; they do not represent shares of total sales.');
  return `<svg viewBox="0 0 260 260" role="img" aria-label="${esc(chartTitle(id,meta.business))} ${type} chart"><title>${esc(chartTitle(id,meta.business))}</title>${slices}${type==='doughnut'?'<circle cx="130" cy="130" r="66" fill="white"/>':''}</svg>` +
    `<div class="chartVariantLegend" tabindex="0" role="region" aria-label="Chart values">${items.map(([name,value],index) => `<span><i style="background:${palette[index]}"></i>${esc(name)} · ${esc(format(value))}</span>`).join('')}</div>` +
    notes.filter(Boolean).map(note => `<p class="chartNote">${esc(note)}</p>`).join('');
}
