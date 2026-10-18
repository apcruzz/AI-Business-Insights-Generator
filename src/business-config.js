// Declarative business profiles: labels, colors, and ranked chart preferences.
// The chart registry checks backend capabilities before any recommendation is shown.
const profile = (label, title, item, color, tint, recommended, fallback) => ({label, title, item, color, tint, recommended, fallback});
export const BUSINESSES = {
  Cafe: profile('Café / coffee shop', 'Your café at a glance', 'Menu item', '#78513a', '#faf3eb', ['trend','category','weather'], ['products','hour','profitability','weekday','staff']),
  Restaurant: profile('Restaurant / food truck', 'Your kitchen, in numbers', 'Dish', '#b34b31', '#fff3eb', ['profitability','category','hour'], ['products','trend','weekday','staff','weather']),
  'Retail store': profile('Retail / clothing store', 'Your store at a glance', 'Product', '#7a4788', '#f7f0fa', ['category','products','profitability'], ['trend','weekday','hour','staff']),
  'Tech store': profile('Tech / electronics store', 'Your tech store performance', 'Device / accessory', '#245fa5', '#edf5ff', ['categoryBar','products','profitability'], ['trend','channel','orderValue','weekday']),
  'Furniture shop': profile('Furniture store', 'Your furniture showroom', 'Furniture item', '#5d7050', '#f2f5ee', ['categoryBar','productProfit','delivery'], ['products','trend','profitability','orderValue','staff']),
  Bakery: profile('Bakery', 'Fresh insights from your bakery', 'Baked product', '#a36325', '#fff7e8', ['unitsHour','waste','trend'], ['products','category','profitability','hour','weekday']),
  'Online shop': profile('Online shop', 'Your online shop performance', 'Product', '#276b75', '#eef9fa', ['channel','products','orderValue'], ['trend','category','profitability','weekday']),
  'Salon / barbershop': profile('Salon / barbershop', 'Your salon at a glance', 'Service', '#a24670', '#fff0f5', ['service','bookings','utilization'], ['trend','staff','category','weekday','profitability']),
  'Repair / service shop': profile('Repair / service shop', 'Your service desk at a glance', 'Service type', '#44647a', '#f0f5f8', ['service','turnaround','jobStatus'], ['trend','staff','category','profitability','weekday']),
  'Other business': profile('Other business', 'Your business at a glance', 'Product / service', '#008473', '#edf8f5', ['trend','category','products'], ['profitability','weekday','hour','staff','orderValue']),
};
export const businessProfile = name => BUSINESSES[name] || BUSINESSES['Other business'];

// Required capabilities are validated server-side. Missing fields remain visible as
// explanations in the chooser, while only supported charts can be selected.
export const CHARTS = {
  trend: {title:'Net sales trend', kind:'Line chart', needs:['Date'], requires:'Date and net sales', family:'trend'},
  category: {title:'Sales by category', kind:'Pie chart', needs:['category'], requires:'Category and net sales', family:'category'},
  categoryBar: {title:'Revenue by category', kind:'Bar chart', needs:['category'], requires:'Category and net sales', family:'category'},
  products: {title:'Best-selling products', kind:'Horizontal bar chart', needs:['product'], requires:'Product and net sales; quantity when available', family:'products'},
  profitability: {title:'Product gross margin', kind:'Horizontal bar chart', needs:['product','Gross_Profit'], requires:'Product and gross profit or costs', family:'margin'},
  productProfit: {title:'Gross profit by product', kind:'Horizontal bar chart', needs:['product','Gross_Profit'], requires:'Product and gross profit or costs', family:'profit'},
  hour: {title:'Sales by hour', kind:'Stacked columns by product', needs:['Hour','product'], requires:'Hour / time, product and net sales', family:'hour'},
  unitsHour: {title:'Products sold by hour', kind:'Stacked columns by product', needs:['Hour','Quantity','product'], requires:'Hour / time, product and quantity', family:'hour'},
  weekday: {title:'Sales by day of week', kind:'Bar chart', needs:['Date'], requires:'Date and net sales', family:'weekday'},
  weather: {title:'Weather versus sales', kind:'Bar chart', needs:['Date','weather'], requires:'Uploaded weather, date and net sales', family:'weather'},
  staff: {title:'Staff sales comparison', kind:'Horizontal bar chart', needs:['employee'], requires:'Employee and net sales', family:'staff'},
  channel: {title:'Revenue by sales channel', kind:'Bar chart', needs:['channel'], requires:'Sales channel and net sales', family:'channel'},
  orderValue: {title:'Order value distribution', kind:'Histogram', needs:['orders'], requires:'Validated order IDs and net sales', family:'orders'},
  delivery: {title:'Delivery performance', kind:'Stacked columns: on time / late', needs:['delivery'], requires:'Delivery ID and on-time/late status, or promised and actual delivery dates', family:'delivery'},
  waste: {title:'Waste cost by product', kind:'Horizontal bar chart', needs:['waste'], requires:'Product and nonnegative waste cost per row', family:'waste'},
  service: {title:'Revenue by service', kind:'Bar chart', needs:['product'], requires:'Service name / type mapped as product, and net sales', family:'products'},
  bookings: {title:'Bookings by day and hour', kind:'Heatmap', needs:['bookings'], requires:'Appointment ID and appointment start timestamp', family:'bookings'},
  utilization: {title:'Staff appointment utilization', kind:'Horizontal bar chart', needs:['utilization'], requires:'Appointment ID/start/minutes, employee and daily available minutes', family:'utilization'},
  turnaround: {title:'Average job turnaround time', kind:'Horizontal bar chart', needs:['turnaround'], requires:'Job ID, service type, opened and completed timestamps', family:'turnaround'},
  jobStatus: {title:'Jobs by status', kind:'Bar chart', needs:['jobStatus'], requires:'Job ID and job status', family:'jobs'},
};
export const BUSINESS_FIELDS = {
  Sales_Channel:'Sales channel', Waste_Cost:'Waste cost (per source row)', Delivery_ID:'Delivery / shipment ID',
  Delivery_Status:'Delivery outcome (on time / late)', Delivery_Due:'Promised delivery date / time', Delivered_At:'Actual delivery date / time',
  Appointment_ID:'Appointment / booking ID', Appointment_Start:'Appointment start (date and time)', Appointment_Status:'Appointment status',
  Appointment_Minutes:'Booked duration (minutes per appointment)', Available_Minutes:'Available minutes (per employee per day)',
  Job_ID:'Job / repair ID', Job_Status:'Job status', Job_Opened:'Job opened (date and time)', Job_Completed:'Job completed (date and time)',
};
export function chartTitle(id, business) {
  const p = businessProfile(business);
  if (id === 'products') return business === 'Tech store' ? 'Best-selling devices and accessories' : `Best-selling ${p.item === 'Dish' ? 'dishes' : p.item === 'Service' ? 'services' : 'products'}`;
  if (id === 'profitability' && business === 'Restaurant') return 'Dish profitability';
  if (id === 'categoryBar' && business === 'Furniture shop') return 'Revenue by furniture category';
  if (id === 'trend' && business === 'Bakery') return 'Daily sales trend';
  if (id === 'service' && business === 'Repair / service shop') return 'Revenue by service type';
  return CHARTS[id].title;
}
export function chartPlan(business, capabilities = {}) {
  const p = businessProfile(business);
  const order = [...new Set([...p.recommended, ...p.fallback, 'trend','category','products','profitability','weekday','hour','staff','orderValue'])];
  const available = order.filter(id => CHARTS[id].needs.every(key => capabilities[key]));
  const families = new Set();
  const recommended = available.filter(id => {
    if (families.has(CHARTS[id].family)) return false;
    families.add(CHARTS[id].family); return true;
  }).slice(0,3);
  return {available, recommended, missing:p.recommended.filter(id => !available.includes(id))};
}
