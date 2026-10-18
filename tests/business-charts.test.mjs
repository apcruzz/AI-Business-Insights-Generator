import assert from 'node:assert/strict';
import {test} from 'node:test';
import {BUSINESSES, CHARTS, chartPlan} from '../src/business-config.js';
import {businessChartData,renderBusinessChart} from '../src/business-charts.js';
const all=Object.fromEntries(Object.values(CHARTS).flatMap(c=>c.needs).map(k=>[k,true]));
const expected={Cafe:['trend','category','weather'],Restaurant:['profitability','category','hour'],'Retail store':['category','products','profitability'],'Tech store':['categoryBar','products','profitability'],'Furniture shop':['categoryBar','productProfit','delivery'],Bakery:['unitsHour','waste','trend'],'Online shop':['channel','products','orderValue'],'Salon / barbershop':['service','bookings','utilization'],'Repair / service shop':['service','turnaround','jobStatus']};
test('Every business follows the requested three charts when data supports them',()=>{
  for(const [business,charts] of Object.entries(expected))assert.deepEqual(chartPlan(business,all).recommended,charts);
});
test('Fallbacks require actual capabilities and avoid duplicate metrics',()=>{
  for(const business of Object.keys(BUSINESSES)){
    const plan=chartPlan(business,{Date:true,product:true,category:true});
    assert.equal(plan.recommended.length,3);
    assert.equal(new Set(plan.recommended.map(id=>CHARTS[id].family)).size,3);
    assert.deepEqual(chartPlan(business,{}).recommended,[]);
  }
  assert.deepEqual(chartPlan('Furniture shop',{category:true,product:true,Gross_Profit:true}).recommended,['categoryBar','productProfit','products']);
});
test('Revenue, quantity, weighted margin, negative profit and waste retain their distinct meanings',()=>{
  const rows=[{Product_Name:'Tea',Net_Sales:10,Gross_Profit:5,Quantity:2,Waste_Cost:1},{Product_Name:'Tea',Net_Sales:90,Gross_Profit:9,Quantity:1,Waste_Cost:2},{Product_Name:'Coffee',Net_Sales:30,Gross_Profit:-2,Quantity:5,Waste_Cost:0}];
  assert.deepEqual(businessChartData('products',rows,{Quantity:true}).items,[['Coffee',5],['Tea',3]]);
  assert.deepEqual(businessChartData('profitability',rows).items[0],['Tea',14.000000000000002]);
  assert.deepEqual(businessChartData('productProfit',rows).items,[['Tea',14],['Coffee',-2]]);
  assert.deepEqual(businessChartData('waste',rows).items,[['Tea',3],['Coffee',0]]);
});
test('Order histogram counts each order once, including refunds and equal values',()=>{
  const rows=[{Order_Key:'a',Net_Sales:5},{Order_Key:'a',Net_Sales:5},{Order_Key:'b',Net_Sales:10},{Order_Key:'c',Net_Sales:-2}];
  assert.equal(businessChartData('orderValue',rows).items.reduce((n,r)=>n+r[1],0),3);
  assert.deepEqual(businessChartData('orderValue',rows.slice(0,3)).items,[['10.00–10.00',2]]);
});
test('Delivery, jobs and bookings deduplicate line items; capacity is counted once per staff-day',()=>{
  const one={Delivery_ID:'D1',Delivery_Outcome:'On time',Date:'2026-01-05',Job_ID:'J1',Job_Status:'Done',Turnaround_Hours:24,Product_Name:'Repair',Appointment_ID:'A1',Appointment_Start:'2026-01-05T09:00:00',Appointment_Day:'2026-01-05',Appointment_Hour:9,Appointment_Minutes:60,Employee_Name:'Ana',Available_Minutes:480};
  const second={...one,Delivery_ID:'D2',Delivery_Outcome:'Late',Job_ID:'J2',Turnaround_Hours:48,Appointment_ID:'A2',Appointment_Hour:10,Appointment_Minutes:120};
  const rows=[one,one,second];
  assert.deepEqual(businessChartData('delivery',rows).items,[['2026-01',1,1]]);
  assert.deepEqual(businessChartData('jobStatus',rows).items,[['Done',2]]);
  assert.deepEqual(businessChartData('turnaround',rows).items,[['Repair',36]]);
  assert.equal(businessChartData('bookings',rows).items.reduce((n,r)=>n+r[2],0),2);
  assert.deepEqual(businessChartData('utilization',rows).items,[['Ana',37.5]]);
  second.Appointment_Status='Cancelled';
  assert.equal(businessChartData('bookings',rows).items.reduce((n,r)=>n+r[2],0),1);
});
test('SVGs use actual line/heatmap/histogram renderers and escape uploaded labels',()=>{
  const meta={business:'Bakery',currency:'USD',capabilities:all};
  assert.match(renderBusinessChart('trend',[{Date:'2026-01-01',Net_Sales:10}],meta,'#78513a',String),/<polyline/);
  const html=renderBusinessChart('service',[{Product_Name:'<img onerror=bad>',Net_Sales:10}],meta,'#78513a',String);
  assert.ok(!html.includes('<img'));
  assert.match(renderBusinessChart('service',[],meta,'#78513a',String),/No matching records/);
});
