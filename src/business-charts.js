// Pure chart calculations and SVG rendering. Both Overview and Detail use this
// module, so business recommendations never introduce a second set of totals.
import {esc, group, sum} from './dashboard-utils.js';
import {chartTitle} from './business-config.js';
const totalBy = (rows, field, metric='Net_Sales') => group(rows,field).map(([name, r])=>[name,sum(r,metric)]).sort((a,b)=>b[1]-a[1]);
const unique = (rows, id) => [...new Map(rows.map(r=>[r[id],r])).values()];
// A booking may appear on several sales lines; cancellations/no-shows do not consume booked capacity here.
const activeBookings = rows => unique(rows,'Appointment_ID').filter(r=>r.Appointment_Start && !['cancelled','canceled','no show','no-show'].includes((r.Appointment_Status || '').toLowerCase().trim()));

export function businessChartData(id, rows, capabilities={}) {
  // A small result object keeps chart math testable without a browser or Ollama.
  const result = {type:'bars', unit:'money', items:[], note:''};
  if (!rows.length) return result;
  switch(id) {
    case 'trend': {
      // Long date ranges use months; absent dates stay absent rather than becoming invented zero-sales days.
      const monthly = new Set(rows.map(r=>r.Date)).size > 90;
      result.type='line';
      result.items=totalBy(rows.map(r=>({...r, period:monthly?r.Date.slice(0,7):r.Date})),'period').sort((a,b)=>a[0].localeCompare(b[0]));
      result.note=monthly?'Grouped by month for readability; only recorded dates are included.':'Only recorded dates are shown; gaps do not mean zero sales.';
      break;
    }
    case 'categoryBar': result.items=totalBy(rows,'Category'); break;
    case 'service': result.items=totalBy(rows,'Product_Name'); break;
    case 'channel': result.items=totalBy(rows,'Sales_Channel'); break;
    case 'products':
      result.type='horizontal'; result.unit=capabilities.Quantity?'units':'money';
      result.items=totalBy(rows,'Product_Name',capabilities.Quantity?'Quantity':'Net_Sales');
      result.note=capabilities.Quantity?'Ranked by net units sold, including recorded returns.':'Quantity was not provided; ranked by net revenue.'; break;
    case 'productProfit': result.type='horizontal'; result.items=totalBy(rows,'Product_Name','Gross_Profit'); break;
    case 'profitability':
      // Weighted margin uses summed profit / summed revenue, not the average of individual line margins.
      result.type='horizontal'; result.unit='percent';
      result.items=group(rows,'Product_Name').filter(([,r])=>sum(r,'Net_Sales')>0).map(([n,r])=>[n,sum(r,'Gross_Profit')/sum(r,'Net_Sales')*100]).sort((a,b)=>b[1]-a[1]);
      result.note='Gross profit ÷ net sales; products with nonpositive net sales are excluded.'; break;
    case 'waste': result.type='horizontal'; result.items=totalBy(rows,'Product_Name','Waste_Cost'); result.note='Waste cost is summed once per source row.'; break;
    case 'jobStatus': result.unit='jobs'; result.items=group(unique(rows,'Job_ID'),'Job_Status').map(([n,r])=>[n,r.length]); break;
    case 'turnaround':
      result.type='horizontal';result.unit='hours';
      result.items=group(unique(rows,'Job_ID').filter(r=>r.Turnaround_Hours!==null && r.Turnaround_Hours!==undefined),'Product_Name').map(([n,r])=>[n,sum(r,'Turnaround_Hours')/r.length]).sort((a,b)=>b[1]-a[1]);
      result.note='Average elapsed hours per completed job; incomplete or invalid timestamps are excluded.'; break;
    case 'orderValue': {
      // First combine all selected lines of each order, then count those order totals into value ranges.
      result.type='histogram';result.unit='orders';
      const values=group(rows,'Order_Key').map(([,r])=>sum(r,'Net_Sales'));
      const min=Math.min(...values), max=Math.max(...values), bins=min===max?1:Math.min(8,Math.ceil(Math.sqrt(values.length))), width=(max-min)/bins;
      result.ranges=Array.from({length:bins},(_,i)=>[min+i*width,min+(i+1)*width]);
      result.items=result.ranges.map((range,i)=>[`${range[0].toFixed(2)}–${range[1].toFixed(2)}`,0]);
      values.forEach(v=>result.items[width?Math.min(bins-1,Math.floor((v-min)/width)):0][1]++);
      result.note='Each matching order counts once. Values sum only selected sales lines; product filters may show partial orders. Bins include their lower boundary; only the last includes its upper boundary.';break;
    }
    case 'delivery': {
      // Count shipments once per validated ID even when several purchased items share that shipment.
      result.type='stacked';result.unit='deliveries';result.series=['On time','Late'];
      const events=unique(rows,'Delivery_ID').filter(r=>r.Delivery_Outcome);
      result.items=group(events.map(r=>({...r,month:(r.Delivery_Due || r.Delivered_At || r.Date)?.slice(0,7) || 'All deliveries'})),'month').sort((a,b)=>a[0].localeCompare(b[0])).map(([n,r])=>[n,r.filter(x=>x.Delivery_Outcome==='On time').length,r.filter(x=>x.Delivery_Outcome==='Late').length]);
      result.note='Unique completed deliveries by promised month (actual/sales month if unavailable). Pending and unknown outcomes are excluded.';break;
    }
    case 'hour':
    case 'unitsHour': {
      // Keep the largest product series readable and group the remainder without dropping their totals.
      const metric=id==='unitsHour'?'Quantity':'Net_Sales';
      result.type='stacked';result.unit=id==='unitsHour'?'units':'money';
      const ranked=totalBy(rows,'Product_Name',metric), names=ranked.slice(0,5).map(x=>x[0]);
      const rest=ranked.length>5;result.series=rest?[...names,'Other products']:names;
      result.items=group(rows,'Hour').sort((a,b)=>a[0]-b[0]).map(([hour,r])=>[`${hour}:00`,...names.map(n=>sum(r.filter(x=>x.Product_Name===n),metric)),...(rest?[sum(r.filter(x=>!names.includes(x.Product_Name)),metric)]:[])]);
      if(result.items.some(r=>r.slice(1).some(v=>v<0))) {
        result.type='bars';result.items=result.items.map(r=>[r[0],r.slice(1).reduce((a,b)=>a+b,0)]);
        result.note='Returns create negative contributions, so net totals are shown instead of stacked shares.';
      }break;
    }
    case 'bookings': {
      result.type='heatmap';result.unit='bookings';
      const events=activeBookings(rows);
      result.items=Array.from({length:7},(_,day)=>Array.from({length:24},(_,hour)=>[day,hour,0])).flat();
      events.forEach(r=>{
        const day=(new Date(r.Appointment_Day+'T12:00:00Z').getUTCDay()+6)%7;
        result.items[day*24+Number(r.Appointment_Hour)][2]++;
      });
      result.note='Unique appointments by start weekday and hour. Cancelled and no-show bookings are excluded.';break;
    }
    case 'utilization': {
      // Daily availability repeats on booking rows, so sum capacity once per represented employee-day.
      result.type='horizontal';result.unit='percent';
      const events=activeBookings(rows);
      result.items=group(rows,'Employee_Name').map(([name,r])=>{
        const available=sum(unique(r,'Appointment_Day'),'Available_Minutes');
        const booked=sum(events.filter(x=>x.Employee_Name===name),'Appointment_Minutes');
        return [name,available?booked/available*100:0];
      }).sort((a,b)=>b[1]-a[1]);
      result.note='Booked minutes ÷ supplied availability on represented staff-days. Filters can show partial schedules. Values above 100% indicate overbooking or overlapping records; this is not measured working time.';break;
    }
    default: return null;
  }
  return result;
}

export function renderBusinessChart(id, rows, meta, color, money, layout = null) {
  // Optional pixel dimensions let preview plots fill their cards while keeping text at a readable size.
  const data=businessChartData(id,rows,meta.capabilities);
  if(!data) return null;
  if(!data.items.length) return '<p class="chartNote">No matching records for this chart.</p>';
  const title=chartTitle(id,meta.business);
  const fmt=v=>data.unit==='money'?money(v):`${Number(v.toFixed(1)).toLocaleString()}${data.unit==='percent'?'%':' '+data.unit}`;
  const palette=[color,'#cb6b42','#5689b1','#a77ab0','#b69b3c','#708477'];
  const font=layout?.fontSize || 12, W=layout?.width || 680;
  let output='';
  if(data.type==='horizontal') {
    // Scale by magnitude so refunds and losses can retain their sign in labels while sharing one track.
    const items=data.items.slice(0,12),max=Math.max(...items.map(r=>Math.abs(r[1])),data.unit==='percent'?100:1);
    output=items.map(([name,value])=>`<div class="barrow"><div class="barhead"><span>${esc(name)}</span><strong>${esc(fmt(value))}</strong></div><div class="track"><div class="fill" style="width:${Math.abs(value)/max*100}%;background:${value<0?'#b34242':color}"></div></div></div>`).join('');
    if(data.items.length>12) data.note+=' Showing the top 12 groups.';
  } else if(data.type==='heatmap') {
    const max=Math.max(...data.items.map(r=>r[2]),1),days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const H=layout?.height || 240, left=layout?38:55, top=layout?10:25;
    const cellW=layout?(W-left-12)/24:25, cellH=layout?(H-top-font-16)/7:25;
    output=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>`;
    data.items.forEach(([day,hour,count])=>{const x=left+hour*cellW,y=top+day*cellH;output+=`<rect x="${x}" y="${y}" width="${cellW-2}" height="${cellH-2}" rx="3" fill="${color}" opacity="${.08+.92*count/max}"><title>${days[day]} ${hour}:00: ${count} bookings</title></rect>`;});
    days.forEach((day,i)=>output+=`<text x="5" y="${top+(i+.5)*cellH+font/3}" font-size="${font}">${day}</text>`);
    for(let h=0;h<24;h+=layout && W<400?6:3) output+=`<text x="${left+h*cellW}" y="${layout?H-5:222}" font-size="${font}">${h}:00</text>`;
    output+='</svg>';
  } else {
    let items=data.items;
    if(!['line','stacked'].includes(data.type) && items.length>12) {items=items.slice(0,12);data.note+=' Showing the top 12 groups.';}
    const stacked=data.type==='stacked',values=items.map(r=>stacked?r.slice(1).reduce((a,b)=>a+b,0):r[1]);
    const max=Math.max(...values,1),min=Math.min(...values,0),H=layout?.height || 280;
    const axisFmt=v=>layout && data.unit==='money' && Math.abs(v)>=10000
      ? new Intl.NumberFormat(undefined,{style:'currency',currency:meta.currency || 'USD',notation:'compact',maximumFractionDigits:1}).format(v):fmt(v);
    // Reserve room for tick labels before positioning marks; negative values share the same zero baseline.
    const ticks=Array.from({length:5},(_,i)=>min+(max-min)*i/4);
    const left=layout?Math.max(42,...ticks.map(v=>axisFmt(v).length*font*.58+12)):80;
    const right=W-12,bottom=layout?H-font-18:220,top=layout?12:30;
    const y=v=>bottom-(v-min)/(max-min)*(bottom-top),step=(right-left)/items.length;
    const width=data.type==='histogram'?step:Math.min(layout?56:42,step*.72);
    output=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>`;
    for(const v of ticks) output+=`<line x1="${left}" y1="${y(v)}" x2="${right}" y2="${y(v)}" stroke="#e1e8ec"/><text x="${left-7}" y="${y(v)+4}" text-anchor="end" font-size="${layout?font:10}">${esc(axisFmt(v))}</text>`;
    if(data.type==='line') output+=`<polyline fill="none" stroke="${color}" stroke-width="3" points="${items.map((r,i)=>`${left+step*(i+.5)},${y(r[1])}`).join(' ')}"/>`;
    items.forEach((r,i)=>{
      const x=left+step*(i+.5);
      if(data.type==='line') output+=`<circle cx="${x}" cy="${y(r[1])}" r="${layout?4:3}" fill="${color}"><title>${esc(r[0])}: ${esc(fmt(r[1]))}</title></circle>`;
      else {
        let base=0;
        (stacked?r.slice(1):[r[1]]).forEach((v,k)=>{const end=base+v;output+=`<rect x="${x-width/2}" y="${Math.min(y(base),y(end))}" width="${width}" height="${Math.abs(y(base)-y(end))}" fill="${palette[k%palette.length]}"><title>${esc(r[0])}${stacked?' · '+esc(data.series[k]):''}: ${esc(fmt(v))}</title></rect>`;base=end;});
      }
      const maxLabels=layout?Math.max(1,Math.floor((right-left)/75)):6;
      // Thin crowded axis labels only; every data point and its full hover value remain in the chart.
      const labelStep=Math.ceil(items.length/maxLabels);
      if((!layout && items.length<=8) || i%labelStep===0) {
        const label=layout && data.type==='line' && r[0].length===10?r[0].slice(5):String(r[0]);
        const maxChars=layout?Math.max(3,Math.min(18,Math.floor(step*labelStep/(font*.6)))):18;
        const shown=label.length>maxChars?label.slice(0,maxChars-1)+'…':label;
        output+=`<text x="${x}" y="${layout?H-7:241}" text-anchor="middle" font-size="${layout?font:10}"><title>${esc(r[0])}</title>${esc(shown)}</text>`;
      }
    });
    output+='</svg>';
    if(stacked) output+=`<div class="legendBox">${data.series.map((s,i)=>`<span><i style="background:${palette[i%palette.length]}"></i>${esc(s)}</span>`).join('')}</div>`;
    if(data.type==='histogram') output+=`<p class="chartNote">Horizontal axis: order value (${esc(meta.currency)}). Vertical axis: number of orders.</p>`;
  }
  return output+(data.note?`<p class="chartNote">${esc(data.note)}</p>`:'');
}
