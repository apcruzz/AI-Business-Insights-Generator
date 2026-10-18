import {SAMPLE_DATASETS} from "./sample-datasets.js";
import {BUSINESS_FIELDS, CHARTS, businessProfile, chartPlan, chartTitle} from "./business-config.js";
import {renderBusinessChart} from "./business-charts.js";
// Frontend controller: upload -> map columns -> normalize via API -> filter/render -> ask questions.
import {
  $,
  bottomBy,
  dayNames,
  esc,
  findNamed,
  group,
  median,
  missingDataAnswer,
  pct,
  period,
  round2,
  sourceOptions,
  standardDeviation,
  sum,
  topBy,
  weekKey,
} from "./dashboard-utils.js";

// Keep state and handlers inside the initializer called by App after mounting.
export function initDashboard() {

// Shared app state. `data` holds normalized rows returned by the Python server.
let data = [],
  meta = {},
  selected = [],
  uploadPayload = {},
  profile = null,
  token = "",
  busy = false,
  conversationId = null,
  conversationTurns = [],
  revision = 0,
  overviewChartIds = [];

// Preferred local model for this project. Other downloaded local models still work.
const preferredLocalModel = "llama3:latest";

// Fields the dashboard understands. The mapping UI connects source columns to these names.
const fields = {
  Date: "Date",
  Time: "Time (24-hour)",
  Hour: "Hour (0–23)",
  Product_Name: "Product / dish / item / service",
  Category: "Category",
  Quantity: "Quantity sold",
  Unit_Price: "Unit selling price",
  Modifier_Amount: "Add-on / modifier charge (numeric)",
  Line_Total: "Line total (includes add-ons)",
  Gross_Sales: "Gross sales amount (includes add-ons)",
  Discount_Amount: "Discount amount",
  Net_Sales: "Net sales amount (after discounts, includes add-ons)",
  Unit_COGS: "Unit product cost",
  Total_COGS: "Total product cost",
  Gross_Profit: "Gross profit amount",
  Transaction_ID: "Order / receipt ID",
  Employee_Name: "Employee",
  Payment_Method: "Payment method",
  Weather: "Weather",
  Store_Location: "Store location",
  ...BUSINESS_FIELDS,
};

// Formats money using the currency chosen during setup.
const money = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: meta.currency || "USD",
  }).format(n);

// Formats money in compact chart labels, such as $1K or $2M.
const axisMoney = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: meta.currency || "USD",
    maximumFractionDigits: 0,
    notation: "compact",
  }).format(n);
// Reusable chart palette; colorFor maps source labels to these colors.
const colors = [
  "#008d79",
  "#e8ad2c",
  "#e77939",
  "#438dcc",
  "#6750a4",
  "#be123c",
  "#0f766e",
  "#475569",
  "#4d7c0f",
];

// Gives each category or product a stable color while the dashboard is open.
function colorFor(name, field = "Category") {
  const names = [...new Set(data.map((r) => r[field]))].sort();
  const palette = [businessProfile(meta.business).color, ...colors.slice(1)];
  return palette[Math.max(0, names.indexOf(name)) % palette.length];
}

// Builds a small message that can sit where a chart would normally appear.
function note(text) {
  return `<p class="chartNote">${esc(text)}</p>`;
}

// POST helper for the local Python API. The token ties requests to this page load.
async function api(path, payload) {
  if (!token) token = (await (await fetch("/api/session")).json()).token;
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Dashboard-Token": token },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok)
    throw Error(result.error || "Unable to complete this action.");
  return result;
}
function showSetup() {
  // Show the upload/mapping screen and hide the dashboard views.
  $("setupPage").hidden = false;
  $("dashboardMain").hidden = true;
  document.body.classList.remove("overviewMode");
  $("cancelSetup").hidden = !data.length;
}
function showPage(page) {
  // The overview page uses the compact dashboard layout; detail keeps full charts.
  if (!data.length) return showSetup();
  applyBusinessTheme(meta.business);
  const overview = page === "overview";
  $("setupPage").hidden = true;
  $("dashboardMain").hidden = false;
  $("overview").hidden = !overview;
  $("detailPage").hidden = overview;
  document.body.classList.toggle("overviewMode", overview);
  $("overviewNav").setAttribute("aria-current", overview ? "page" : "false");
  $("detailNav").setAttribute("aria-current", overview ? "false" : "page");
}
// Rank business preferences first, then choose distinct, supported fallback metrics.
function chartOptions() {
  const plan = chartPlan(meta.business, meta.capabilities);
  const ordered = [...new Set([...plan.recommended, ...plan.available])];
  return ordered.map(id => ({id, title:chartTitle(id, meta.business),
    detail:CHARTS[id].kind + " · " + CHARTS[id].requires,
    recommended:plan.recommended.includes(id)}));
}
function applyBusinessTheme(name) {
  const p = businessProfile(name);
  document.documentElement.style.setProperty("--business-accent", p.color);
  document.documentElement.style.setProperty("--business-tint", p.tint);
  document.body.dataset.business = name;
  $("dashboardTitle").textContent = p.title;
  $("businessName").textContent = p.label.toUpperCase();
  $("businessHint").textContent = p.label + " · recommendations adapt to your uploaded columns";
  $("insightQuestion").placeholder = `Example: How can we improve ${p.item.toLowerCase()} sales?`;
  $("productFilterLabel").textContent = p.item;
  if ($("product").firstChild) $("product").firstChild.textContent = p.item.startsWith("Service") ? "All services" : p.item === "Dish" ? "All dishes" : "All products";
  const topChip = document.querySelector('[data-question="Which product leads sales?"]');
  if (topChip) topChip.textContent = p.item.startsWith("Service") ? "Top service" : p.item === "Dish" ? "Top dish" : "Top product";
}
function applyChartVisibility() {
  // Detailed Dashboard shows the available charts not chosen for Business Overview.
  const available = new Set(chartOptions().map((option) => option.id)),
    overview = new Set(overviewChartIds);
  document.querySelectorAll("[data-chart-panel]").forEach((panel) => {
    const id = panel.dataset.chartPanel;
    panel.hidden = !available.has(id) || overview.has(id);
  });
  document.querySelectorAll("[data-chart-group]").forEach((group) => {
    group.hidden = ![...group.querySelectorAll("[data-chart-panel]")].some(
      (panel) => !panel.hidden,
    );
  });
}
function showChartChooser(resetSelection = false) {
  // Ask which three available charts should be featured in Business Overview.
  if (!data.length) return;
  const options = chartOptions(),
    optionIds = options.map((option) => option.id);
  overviewChartIds = overviewChartIds.filter((id) => optionIds.includes(id));
  if (resetSelection || !overviewChartIds.length)
    overviewChartIds = optionIds.slice(0, 3);
  $("chartChooserSummary").textContent = options.length
    ? `Choose up to 3 charts for Business Overview. The rest will appear in Detailed Dashboard.`
    : "No optional charts are available from the mapped columns.";
  const plan = chartPlan(meta.business, meta.capabilities);
  $("chartRecommendationNotes").innerHTML = `<p>Recommended for ${esc(businessProfile(meta.business).label)} from the available data.</p>` + plan.missing.map(id => `<p><strong>${esc(chartTitle(id, meta.business))}</strong> needs ${esc(CHARTS[id].requires)}. A supported alternative is selected when available.</p>`).join("");
  $("chartChoices").innerHTML = options.length
    ? options
        .map(
          (option) =>
            `<label class="chartChoice"><input type="checkbox" name="chartChoice" value="${esc(option.id)}" ${overviewChartIds.includes(option.id) ? "checked" : ""}><span><strong>${esc(option.title)}${option.recommended ? ' <em class="recommendedBadge">Recommended</em>' : ""}</strong><small>${esc(option.detail)}</small></span></label>`,
        )
        .join("")
    : `<p class="chartChoiceEmpty">Summary cards and Business insights will still load.</p>`;
  document
    .querySelectorAll('input[name="chartChoice"]')
    .forEach((input) => input.addEventListener("change", updateChartChoiceState));
  updateChartChoiceState();
  $("chartChooser").hidden = false;
  $("loadSelectedCharts").focus();
}
function updateChartChoiceState() {
  // Limit Business Overview to three featured charts.
  const inputs = [...document.querySelectorAll('input[name="chartChoice"]')],
    checked = inputs.filter((input) => input.checked),
    max = Math.min(3, inputs.length);
  inputs.forEach((input) => {
    input.disabled = !input.checked && checked.length >= max;
  });
  $("loadSelectedCharts").disabled = inputs.length > 0 && checked.length === 0;
  if (inputs.length) {
    $("chartChooserSummary").textContent =
      `${checked.length}/${max} overview charts selected. Remaining available charts will appear in Detailed Dashboard.`;
  }
}
function loadSelectedCharts() {
  // Save the selected overview chart ids, then draw Overview and Detail.
  const selectedIds = [
    ...document.querySelectorAll('input[name="chartChoice"]:checked'),
  ].map((input) => input.value);
  overviewChartIds = selectedIds.length
    ? selectedIds.slice(0, 3)
    : chartOptions()
        .slice(0, 3)
        .map((option) => option.id);
  $("chartChooser").hidden = true;
  applyChartVisibility();
  render();
  $("setupStatus").textContent = "Dashboard ready.";
}
function selectRecommendedCharts() {
  const recommended = new Set(chartOptions().slice(0, 3).map((option) => option.id));
  document.querySelectorAll('input[name="chartChoice"]').forEach((input) => {
    input.checked = recommended.has(input.value);
  });
  updateChartChoiceState();
}
async function inspect() {
  // Read the chosen sample/upload and ask the server for column suggestions.
  $("setupError").textContent = "";
  $("setupStatus").textContent = "Reading columns…";
  $("inspectButton").disabled = true;
  try {
    if ($("sample").value) uploadPayload = { sample: $("sample").value };
    else if ($("upload").files.length) {
      const file = $("upload").files[0];
      if (file.size > 20 * 1024 * 1024)
        throw Error("Choose a file smaller than 20 MB.");
      const base64 = await new Promise((resolve, reject) => {
        // Uploads are encoded in the browser, then sent only to the local server.
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject(Error("Cannot read this file."));
        reader.readAsDataURL(file);
      });
      uploadPayload = { file: base64, filename: file.name };
    } else if (!Object.keys(uploadPayload).length)
      throw Error("Choose a sample or upload an Excel/CSV file.");
    if ($("sheet").value && profile?.sheets.includes($("sheet").value))
      uploadPayload.sheet = $("sheet").value;
    profile = await api("/api/profile", uploadPayload);
    $("mappingPanel").hidden = false;
    const sheet = $("sheet").value;
    $("sheet").replaceChildren();
    profile.sheets.forEach((name) => {
      const o = document.createElement("option");
      o.value = name;
      o.textContent = name;
      $("sheet").append(o);
    });
    if (profile.sheets.includes(sheet)) $("sheet").value = sheet;
    $("sheet").disabled = !profile.sheets.length;
    $("mappingGrid").innerHTML = Object.entries(fields)
      .map(
        ([key, label]) =>
          `<label>${esc(label)}<select id="map_${key}"></select></label>`,
      )
      .join("");
    Object.keys(fields).forEach((key) =>
      sourceOptions(
        $("map_" + key),
        profile.columns,
        profile.mapping[key] || "",
      ),
    );
    // Keep operational fields in a separate collapsible group; expose detected fields automatically.
    const operational = document.createElement("details");
    operational.className = "operationalMapping";
    const summary = document.createElement("summary");
    summary.textContent = "Optional delivery, booking, waste, channel and job columns";
    operational.append(summary);
    const grid = document.createElement("div"); grid.className = "mappingGrid";
    Object.keys(BUSINESS_FIELDS).forEach(key => grid.append($("map_" + key).parentElement));
    operational.append(grid); $("mappingGrid").append(operational);
    operational.open = Object.keys(BUSINESS_FIELDS).some(key => profile.mapping[key]);
    // Ask about amount semantics only for mapped add-on or line-total columns.
    $("lineTotalBasis").value = "";
    $("modifierBasis").value = "line";
    const updateAmountOptions = () => {
      $("lineTotalOptions").hidden = !$("map_Line_Total").value;
      $("modifierOptions").hidden = !$("map_Modifier_Amount").value;
    };
    $("map_Line_Total").onchange = updateAmountOptions;
    $("map_Modifier_Amount").onchange = updateAmountOptions;
    updateAmountOptions();
    $("preview").innerHTML =
      "<table><thead><tr>" +
      profile.columns.map((c) => `<th>${esc(c)}</th>`).join("") +
      "</tr></thead><tbody>" +
      profile.preview
        .map(
          (r) =>
            "<tr>" +
            profile.columns.map((c) => `<td>${esc(r[c])}</td>`).join("") +
            "</tr>",
        )
        .join("") +
      "</tbody></table>";
    $("setupStatus").textContent =
      `${profile.rows.toLocaleString()} source rows · ${profile.columns.length} columns. Check the suggested mappings.`;
  } catch (e) {
    $("setupError").textContent = e.message;
    $("setupStatus").textContent = "";
  } finally {
    $("inspectButton").disabled = false;
  }
}
async function build() {
  // Send the confirmed mapping to the server and receive normalized records.
  $("setupError").textContent = "";
  $("buildButton").disabled = true;
  $("setupStatus").textContent = "Validating and calculating…";
  try {
    const mapping = Object.fromEntries(
      Object.keys(fields).map((key) => [key, $("map_" + key).value]),
    );
    const currency = $("currency").value.trim().toUpperCase();
    new Intl.NumberFormat("en-US", { style: "currency", currency });
    const result = await api("/api/analyze", {
      ...uploadPayload,
      sheet: $("sheet").value,
      mapping,
      business: $("business").value,
      currency,
      dateOrder: $("dateOrder").value,
      decimal: $("decimal").value,
      lineTotalBasis: $("lineTotalBasis").value,
      modifierBasis: $("modifierBasis").value,
    });
    meta = result;
    data = result.rows;
    for (const id of ["category", "product"])
      sourceOptions(
        $(id),
        [
          ...new Set(
            data.map((r) => r[id === "category" ? "Category" : "Product_Name"]),
          ),
        ].sort(),
      );
    $("category").firstChild.textContent = "All categories";
    $("product").firstChild.textContent = "All products";
    for (const id of ["from", "to"]) {
      // Disable filters that cannot work with the mapped columns.
      $(id).disabled = !meta.capabilities.Date;
      $(id).min = meta.dateMin || "";
      $(id).max = meta.dateMax || "";
    }
    $("weekday").disabled = !meta.capabilities.Date;
    $("period").disabled = !meta.capabilities.Hour;
    $("category").disabled = !meta.capabilities.category;
    $("product").disabled = !meta.capabilities.product;
    applyBusinessTheme(meta.business);
    $("datasetName").textContent = meta.filename;
    $("sidebarNotes").innerHTML = meta.warnings
      .map((w) => `<p>${esc(w)}</p>`)
      .join("");
    $("dataNotes").textContent = meta.warnings.join(" ");
    setDefaultFilterValues();
    showPage("overview");
    showChartChooser(true);
    $("setupStatus").textContent = "Choose charts to load.";
  } catch (e) {
    $("setupError").textContent = e.message;
  } finally {
    $("buildButton").disabled = false;
  }
}
function setDefaultFilterValues() {
  // Return all filters to the full dataset range.
  $("from").value = meta.dateMin || "";
  $("to").value = meta.dateMax || "";
  ["category", "product", "weekday", "period"].forEach(
    (id) => ($(id).value = ""),
  );
}
function resetFilters() {
  setDefaultFilterValues();
  render();
}
function filtered() {
  // Apply all current dashboard filters to the normalized rows.
  return data.filter(
    (r) =>
      (!meta.capabilities.Date ||
        ((!$("from").value || r.Date >= $("from").value) &&
          (!$("to").value || r.Date <= $("to").value))) &&
      (!$("category").value || r.Category === $("category").value) &&
      (!$("product").value || r.Product_Name === $("product").value) &&
      (!$("weekday").value ||
        String(new Date(r.Date + "T12:00:00Z").getUTCDay()) ===
          $("weekday").value) &&
      (!$("period").value || period(r.Hour) === $("period").value),
  );
}
function chart(items, dual = false) {
  // Generic SVG bar chart used by trend and weekday charts.
  if (!items.length) return note("No matching sales.");
  const W = 680,
    H = 270,
    L = 70,
    B = 220,
    T = 22,
    values = items.flatMap((x) => (dual ? [x[1], x[2]] : [x[1]])),
    max = Math.max(...values, 1),
    min = Math.min(...values, 0),
    range = max - min;
  const Y = (v) => B - ((v - min) / range) * (B - T),
    zero = Y(0),
    step = (W - L - 15) / items.length,
    bw = Math.min(step * 0.68, 52);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Sales chart"><title>Recorded sales ${dual ? "and gross profit" : ""}</title>`;
  for (let i = 0; i < 5; i++) {
    const v = min + (range * i) / 4,
      y = Y(v);
    svg += `<line x1="${L}" y1="${y}" x2="665" y2="${y}" stroke="#e1e8ec"/><text x="61" y="${y + 4}" text-anchor="end" fill="#657686" font-size="13">${esc(axisMoney(v))}</text>`;
  }
  items.forEach((x, i) => {
    const cx = L + step * (i + 0.5),
      w = dual ? bw / 2 : bw;
    for (let k = 1; k <= (dual ? 2 : 1); k++) {
      const y = Y(x[k]),
        h = Math.abs(zero - y);
      svg += `<rect x="${cx - bw / 2 + (k - 1) * w}" y="${Math.min(y, zero)}" width="${w}" height="${h}" fill="${k === 1 ? businessProfile(meta.business).color : "#438dcc"}" rx="2"><title>${esc(x[0])}: ${k === 1 ? "Net sales" : "Gross profit"} ${esc(money(x[k]))}</title></rect>`;
    }
    if (items.length <= 12 || i % Math.ceil(items.length / 10) === 0)
      svg += `<text x="${cx}" y="245" text-anchor="middle" font-size="12" fill="#657686">${esc(x[0])}</text>`;
  });
  return svg + "</svg>";
}
function trend(rows, dual = false) {
  // Daily data is grouped weekly/monthly when there are many dates.
  if (!meta.capabilities.Date)
    return note("Map a date column to show sales trends.");
  const dates = [...new Set(rows.map((r) => r.Date))].sort();
  let key = "Date",
    source = rows;
  if (dates.length > 40) {
    source = rows.map((r) => ({ ...r, Period: r.Date.slice(0, 7) }));
    key = "Period";
  } else if (dates.length > 14) {
    source = rows.map((r) => {
      const d = new Date(r.Date + "T12:00:00Z");
      d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
      return { ...r, Period: d.toISOString().slice(0, 10) };
    });
    key = "Period";
  }
  return chart(
    group(source, key)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([d, r]) => [
        key === "Period" && d.length === 7 ? d : d.slice(5),
        sum(r, "Net_Sales"),
        sum(r, "Gross_Profit"),
      ]),
    dual,
  );
}
function categoryPie(rows) {
  // Category share is shown as a pie only when totals are positive.
  const groups = group(rows, "Category")
      .map(([c, r]) => [c, sum(r, "Net_Sales")])
      .sort((a, b) => b[1] - a[1]),
    total = sum(rows, "Net_Sales");
  if (!rows.length) return note("No matching sales.");
  if (!meta.capabilities.category)
    return note("Map a category column to compare category sales.");
  if (total <= 0 || groups.some((x) => x[1] < 0))
    return (
      note(
        "Category totals include returns; a pie cannot show negative contributions.",
      ) +
      groups
        .map(
          ([c, n]) =>
            `<div class="categoryLegend"><span>${esc(c)}</span><strong>${money(n)}</strong></div>`,
        )
        .join("")
    );
  if (groups.length > 7) {
    const rest = groups.splice(7);
    groups.push(["Other categories", rest.reduce((n, r) => n + r[1], 0)]);
  }
  let angle = -Math.PI / 2,
    svg =
      '<svg viewBox="0 0 320 300" role="img" aria-label="Category net sales share">';
  groups.forEach(([c, n], i) => {
    const share = n / total,
      next = angle + share * 2 * Math.PI,
      col = colorFor(c);
    if (share > 0.999999)
      svg += `<circle cx="160" cy="150" r="119" fill="${col}"/>`;
    else
      svg += `<path d="M160 150 L${160 + 119 * Math.cos(angle)} ${150 + 119 * Math.sin(angle)} A119 119 0 ${share > 0.5 ? 1 : 0} 1 ${160 + 119 * Math.cos(next)} ${150 + 119 * Math.sin(next)} Z" fill="${col}" stroke="white" stroke-width="2"><title>${esc(c)}: ${money(n)} (${pct(share * 100)})</title></path>`;
    if (share > 0.08) {
      const mid = (angle + next) / 2;
      svg += `<text x="${160 + 77 * Math.cos(mid)}" y="${155 + 77 * Math.sin(mid)}" text-anchor="middle" fill="white" font-size="16" font-weight="600">${pct(share * 100)}</text>`;
    }
    angle = next;
  });
  return (
    svg +
    '</svg><div class="categoryLegendList">' +
    groups
      .map(
        ([c, n]) =>
          `<div class="categoryLegend"><span><i style="display:inline-block;width:10px;height:10px;background:${colorFor(c)};margin-right:5px"></i>${esc(c)}</span><span>${money(n)} · ${pct((n / total) * 100)}</span></div>`,
      )
      .join("") +
    "</div>"
  );
}
function hourStack(rows) {
  // Hour chart stacks the top products and groups the rest as "Other products".
  if (!meta.capabilities.Hour)
    return note("Map a time or hour column to show hourly sales.");
  if (!rows.length) return note("No matching sales.");
  if (rows.some((r) => r.Net_Sales < 0))
    return (
      note("Hourly totals include returns; showing total net sales.") +
      chart(
        group(rows, "Hour")
          .sort((a, b) => a[0] - b[0])
          .map(([h, r]) => [h + ":00", sum(r, "Net_Sales")]),
      )
    );
  const ranked = group(rows, "Product_Name").sort(
      (a, b) => sum(b[1], "Net_Sales") - sum(a[1], "Net_Sales"),
    ),
    names = ranked.slice(0, 8).map((x) => x[0]),
    remainder = ranked.length > 8;
  const groups = group(rows, "Hour").sort((a, b) => a[0] - b[0]),
    W = 760,
    H = 300,
    L = 70,
    B = 245,
    T = 20,
    max = Math.max(...groups.map(([h, r]) => sum(r, "Net_Sales")), 1),
    step = (W - L - 20) / groups.length,
    bw = Math.min(step * 0.7, 45);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Hourly net sales by product">`;
  for (let i = 0; i < 5; i++) {
    const v = (max * i) / 4,
      y = B - (v / max) * (B - T);
    svg += `<line x1="${L}" y1="${y}" x2="740" y2="${y}" stroke="#e1e8ec"/><text x="61" y="${y + 4}" text-anchor="end" font-size="13" fill="#657686">${axisMoney(v)}</text>`;
  }
  groups.forEach(([h, r], i) => {
    let y = B;
    const segments = names.map((p) => [
      p,
      r.filter((x) => x.Product_Name === p),
      colorFor(p, "Product_Name"),
    ]);
    if (remainder)
      segments.push([
        "Other products",
        r.filter((x) => !names.includes(x.Product_Name)),
        "#475569",
      ]);
    segments.forEach(([p, items, col]) => {
      const n = sum(items, "Net_Sales"),
        height = (n / max) * (B - T);
      y -= height;
      if (n)
        svg += `<rect x="${L + step * (i + 0.5) - bw / 2}" y="${y}" width="${bw}" height="${height}" fill="${col}" tabindex="0" aria-label="${esc(p)} at ${h}:00"><title>${h}:00 · ${esc(p)} · ${money(n)}${meta.capabilities.Quantity ? " · " + sum(items, "Quantity") + " units" : ""}</title></rect>`;
    });
    svg += `<text x="${L + step * (i + 0.5)}" y="263" text-anchor="middle" font-size="12" fill="#657686">${h}</text>`;
  });
  svg +=
    '<text x="400" y="292" text-anchor="middle" font-size="13" fill="#657686">Hour of day (24-hour)</text></svg>';
  return (
    svg +
    `<div class="legendBox">${names.map((p) => `<span><i style="background:${colorFor(p, "Product_Name")}"></i>${esc(p)}</span>`).join("")}${remainder ? '<span><i style="background:#475569"></i>Other products</span>' : ""}</div>`
  );
}
function metrics(rows, overview = false) {
  // Metric cards adapt to the columns the user mapped.
  const n = sum(rows, "Net_Sales"),
    g = sum(rows, "Gross_Profit"),
    gross = sum(rows, "Gross_Sales"),
    discount = sum(rows, "Discount_Amount"),
    c = meta.capabilities;
  return (
    overview
      ? [
          ["Net sales", money(n), "Selected recorded revenue"],
          [
            "Gross profit",
            c.Gross_Profit ? money(g) : "—",
            c.Gross_Profit && n > 0
              ? pct((g / n) * 100) + " gross margin"
              : "Product costs not provided",
          ],
          [
            "Units sold",
            c.Quantity ? sum(rows, "Quantity").toLocaleString() : "—",
            c.Quantity ? "Total selected quantity" : "Quantity not provided",
          ],
          [
            "Discounts",
            c.Discount_Amount ? money(discount) : "—",
            c.Discount_Amount && c.Gross_Sales && gross > 0
              ? pct((discount / gross) * 100) + " of gross sales"
              : "Discount data not provided",
          ],
          [
            c.orders ? "Matching orders" : "Sales lines",
            c.orders
              ? new Set(rows.map((r) => r.Order_Key)).size.toLocaleString()
              : rows.length.toLocaleString(),
            c.orders
              ? "Distinct matching order IDs"
              : "Order IDs need validation",
          ],
        ]
      : [
          ["Net sales", money(n), "Selected recorded revenue"],
          [
            "Gross profit",
            c.Gross_Profit ? money(g) : "—",
            "Net sales minus product cost",
          ],
          [
            "Gross margin",
            c.Gross_Profit && n > 0 ? pct((g / n) * 100) : "—",
            "Total gross profit ÷ net sales",
          ],
          [
            "Units sold",
            c.Quantity ? sum(rows, "Quantity").toLocaleString() : "—",
            "Total selected quantity",
          ],
          [
            "Discount rate",
            c.Gross_Sales && c.Discount_Amount && gross > 0
              ? pct((discount / gross) * 100)
              : "—",
            "Discounts ÷ gross sales",
          ],
        ]
  )
    .map(
      (m) =>
        `<article class="card"><div class="label">${esc(m[0])}</div><div class="value">${esc(m[1])}</div><div class="hint">${esc(m[2])}</div></article>`,
    )
	    .join("");
}
// Sum selected revenue for each weekday in Monday-to-Sunday display order.
function weekdayChart(rows, c) {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return c.Date
    ? chart(
        days.map((day, index) => [
          day,
          sum(
            rows.filter(
              (row) =>
                (new Date(row.Date + "T12:00:00Z").getUTCDay() + 6) % 7 ===
                index,
            ),
            "Net_Sales",
          ),
        ]),
      )
    : note("Map a date column to compare weekdays.");
}
// Render the five highest-revenue product groups as relative horizontal bars.
function topProductsChart(products, c) {
  if (!c.product) return note("Map a product column to rank products.");
  const top = products.slice(0, 5),
    max = Math.max(...top.map((item) => sum(item[1], "Net_Sales")), 1);
  return (
    top
      .map(
        ([product, rows]) =>
          `<div class="barrow"><div class="barhead"><span>${esc(product)}</span><strong>${money(sum(rows, "Net_Sales"))}</strong></div><div class="track"><div class="fill" style="background:#008d79;width:${Math.max(0, (sum(rows, "Net_Sales") / max) * 100)}%"></div></div></div>`,
      )
      .join("") || note("No matching sales.")
  );
}
// Rank positive-revenue products by total gross profit divided by total revenue.
function profitabilityChart(products, c) {
  return c.Gross_Profit
    ? products
        .map(([product, rows]) => [
          product,
          sum(rows, "Net_Sales"),
          sum(rows, "Gross_Profit"),
        ])
        .filter((item) => item[1] > 0)
        .sort((a, b) => b[2] / b[1] - a[2] / a[1])
        .map(
          ([product, netSales, grossProfit]) =>
            `<div class="barrow"><div class="barhead"><strong>${esc(product)}</strong><span>${pct((grossProfit / netSales) * 100)}</span></div><div class="track"><div class="fill" style="background:#438dcc;width:${Math.max(0, Math.min(100, (grossProfit / netSales) * 100))}%"></div></div></div>`,
        )
        .join("") || note("No positive sales for a margin comparison.")
    : note("Map product costs or gross profit to show profitability.");
}
// Group selected rows by employee and sort by handled net sales.
function staffGroups(rows) {
  return group(rows, "Employee_Name").sort(
    (a, b) => sum(b[1], "Net_Sales") - sum(a[1], "Net_Sales"),
  );
}
// Build detailed employee rows, displaying unavailable financial metrics as dashes.
function staffTable(rows, c) {
  return (
    staffGroups(rows)
      .map(([name, items]) => {
        const netSales = sum(items, "Net_Sales"),
          grossProfit = sum(items, "Gross_Profit");
        return `<tr><td>${esc(name)}</td><td class="num">${c.Gross_Sales ? money(sum(items, "Gross_Sales")) : "—"}</td><td class="num">${c.Discount_Amount ? money(sum(items, "Discount_Amount")) : "—"}</td><td class="num">${money(netSales)}</td><td class="num">${c.Gross_Profit ? money(grossProfit) : "—"}</td><td class="num">${c.Gross_Profit && netSales > 0 ? pct((grossProfit / netSales) * 100) : "—"}</td></tr>`;
      })
      .join("") || '<tr><td colspan="6">No matching sales.</td></tr>'
  );
}
// Show a compact ranking of the five employees with the highest handled revenue.
function staffChart(rows, c) {
  if (!c.employee) return note("Map an employee column to compare staff sales.");
  const top = staffGroups(rows).slice(0, 5),
    max = Math.max(...top.map((item) => sum(item[1], "Net_Sales")), 1);
  return (
    top
      .map(
        ([name, items]) =>
          `<div class="barrow"><div class="barhead"><span>${esc(name)}</span><strong>${money(sum(items, "Net_Sales"))}</strong></div><div class="track"><div class="fill" style="background:#6750a4;width:${Math.max(0, (sum(items, "Net_Sales") / max) * 100)}%"></div></div></div>`,
      )
      .join("") || note("No matching sales.")
  );
}
// Compare sales per recorded date for each uploaded weather label; no weather lookup occurs.
function weatherChart(rows, c) {
  return c.weather && c.Date
    ? chart(
        group(rows, "Weather").map(([weather, items]) => [
          weather,
          sum(items, "Net_Sales") / new Set(items.map((row) => row.Date)).size,
        ]),
      ) +
        note(
          "Average per recorded day; coverage and other factors can affect this comparison.",
        )
    : note("Map date and weather columns to compare sales by weather.");
}
// Dispatch a selected chart ID to the same chart builders used in the detail view.
function overviewChartHtml(id, rows, products, c) {
  const specialized = renderBusinessChart(id, rows, meta, businessProfile(meta.business).color, money);
  if (specialized !== null) return specialized;
  if (id === "trend") return trend(rows);
  if (id === "category") return categoryPie(rows);
  if (id === "products") return topProductsChart(products, c);
  if (id === "weekday") return weekdayChart(rows, c);
  if (id === "hour") return hourStack(rows);
  if (id === "profitability") return profitabilityChart(products, c);
  if (id === "weather") return weatherChart(rows, c);
  if (id === "staff") return staffChart(rows, c);
  return note("Choose a chart to show here.");
}
function renderOverviewCharts(rows, products, c) {
  // Fill the three Business Overview slots with the user's selected charts.
  const options = chartOptions(),
    optionById = new Map(options.map((option) => [option.id, option])),
    availableIds = new Set(options.map((option) => option.id));
  overviewChartIds = overviewChartIds
    .filter((id) => availableIds.has(id))
    .slice(0, 3);
  if (!overviewChartIds.length)
    overviewChartIds = options.slice(0, 3).map((option) => option.id);
  document.querySelectorAll(".overviewChartSlot").forEach((slot, index) => {
    const id = overviewChartIds[index],
      option = optionById.get(id);
    slot.hidden = !option;
    slot.innerHTML = option
      ? `<h2>${esc(option.title)}</h2><div class="overviewChartContent" data-overview-chart="${esc(id)}">${overviewChartHtml(id, rows, products, c)}</div>`
      : "";
  });
}
function render() {
  // Recalculate every chart/table whenever filters or data change.
  if (!data.length) return;
  revision++;
  selected = filtered();
  const rows = selected,
    c = meta.capabilities;
  $("count").textContent =
    rows.length.toLocaleString() + " sales lines selected";
  $("cards").innerHTML = metrics(rows);
  $("overviewCards").innerHTML = metrics(rows, true);
  const products = group(rows, "Product_Name").sort(
    (a, b) => sum(b[1], "Net_Sales") - sum(a[1], "Net_Sales"),
  );
  renderOverviewCharts(rows, products, c);
  // Render remaining charts through the same dispatcher as Overview.
  $("detailCharts").innerHTML = chartOptions().filter(option => !overviewChartIds.includes(option.id)).map(option =>
    `<section class="panel" data-chart-panel="${esc(option.id)}"><h2>${esc(option.title)}</h2><p class="sub">${esc(CHARTS[option.id].kind)}</p><div class="businessDetailChart">${overviewChartHtml(option.id, rows, products, c)}</div></section>`).join("") || '<p class="chartNote">All supported charts are shown in Business Overview.</p>';
  // Retain the detailed source summaries alongside the new business charts.
  $("detailTables").innerHTML = (c.product ? `<details class="panel"><summary>${esc(businessProfile(meta.business).item)} totals</summary><div class="scroll"><table><thead><tr><th>Item</th><th>Units</th><th>Net sales</th><th>Gross profit</th><th>Margin</th></tr></thead><tbody>${products.map(([name, items]) => {
    const sales = sum(items, "Net_Sales"), profit = sum(items, "Gross_Profit");
    return `<tr><td>${esc(name)}</td><td>${c.Quantity ? sum(items, "Quantity") : "—"}</td><td>${esc(money(sales))}</td><td>${c.Gross_Profit ? esc(money(profit)) : "—"}</td><td>${c.Gross_Profit && sales > 0 ? pct(profit / sales * 100) : "—"}</td></tr>`;
  }).join("")}</tbody></table></div></details>` : "") + (c.employee ? `<details class="panel"><summary>Staff sales totals</summary><div class="scroll"><table><thead><tr><th>Employee</th><th>Gross sales</th><th>Discounts</th><th>Net sales</th><th>Gross profit</th><th>Margin</th></tr></thead><tbody>${staffTable(rows, c)}</tbody></table></div></details>` : "");
  applyChartVisibility();
  renderInsights(rows);
  resetConversation();
  $("analystEvidence").hidden = true;
  $("analystEvidence").replaceChildren();
}
function uniqueOrders(rows) {
  // Returns null when order IDs are missing or failed validation.
  return meta.capabilities.orders
    ? new Set(rows.map((r) => r.Order_Key)).size
    : null;
}
function aov(rows) {
  // Average order value is revenue divided by valid order count.
  const orders = uniqueOrders(rows);
  return orders ? round2(sum(rows, "Net_Sales") / orders) : null;
}
function compareHalves(rows, key) {
  // Simple trend proxy: compare earlier dates with later dates in the selection.
  if (!meta.capabilities.Date) return [];
  const dates = [...new Set(rows.map((r) => r.Date))].sort();
  if (dates.length < 2) return [];
  const split = dates[Math.floor(dates.length / 2)];
  return group(rows, key)
    .map(([name, items]) => {
      const first = sum(
        items.filter((r) => r.Date < split),
        "Net_Sales",
      );
      const second = sum(
        items.filter((r) => r.Date >= split),
        "Net_Sales",
      );
      return {
        name,
        firstHalfNetSales: round2(first),
        secondHalfNetSales: round2(second),
        change: round2(second - first),
        changePercent:
          first > 0 ? Math.round(((second - first) / first) * 1000) / 10 : null,
      };
    })
    .filter((x) => x.firstHalfNetSales || x.secondHalfNetSales)
    .sort((a, b) => b.change - a.change);
}
function facts(rows = selected) {
  // Build facts for calculated answers/cards; the legacy /api/explain accepts this shape.
  // The active /api/analyst path instead queries uploaded rows in the backend.
  const c = meta.capabilities,
    n = sum(rows, "Net_Sales"),
    g = sum(rows, "Gross_Profit"),
    gross = sum(rows, "Gross_Sales"),
    discount = sum(rows, "Discount_Amount"),
    productFacts = group(rows, "Product_Name")
      .map(([name, r]) => {
        // One object per product: revenue, units, discounts, profit, margin.
        const netSales = Math.round(sum(r, "Net_Sales") * 100) / 100,
          grossProfit = c.Gross_Profit
            ? Math.round(sum(r, "Gross_Profit") * 100) / 100
            : null,
          units = c.Quantity ? sum(r, "Quantity") : null,
          productDiscount = c.Discount_Amount
            ? round2(sum(r, "Discount_Amount"))
            : null,
          productGross = c.Gross_Sales ? round2(sum(r, "Gross_Sales")) : null;
        return {
          name,
          netSales,
          units,
          grossProfit,
          discounts: productDiscount,
          discountRatePercent:
            productGross && productDiscount !== null && productGross > 0
              ? Math.round((productDiscount / productGross) * 1000) / 10
              : null,
          averageSellingPrice: units ? round2(netSales / units) : null,
          grossProfitPerUnit:
            units && grossProfit !== null ? round2(grossProfit / units) : null,
          grossMarginPercent:
            grossProfit !== null && netSales > 0
              ? Math.round((grossProfit / netSales) * 1000) / 10
              : null,
          rows: r.length,
        };
      })
      .sort((a, b) => b.netSales - a.netSales),
    categoryFacts = group(rows, "Category")
      .map(([name, r]) => {
        // Category summaries mirror product summaries where possible.
        const netSales = round2(sum(r, "Net_Sales")),
          grossProfit = c.Gross_Profit ? round2(sum(r, "Gross_Profit")) : null,
          categoryDiscount = c.Discount_Amount
            ? round2(sum(r, "Discount_Amount"))
            : null;
        return {
          name,
          netSales,
          units: c.Quantity ? sum(r, "Quantity") : null,
          grossProfit,
          discounts: categoryDiscount,
          grossMarginPercent:
            grossProfit !== null && netSales > 0
              ? Math.round((grossProfit / netSales) * 1000) / 10
              : null,
        };
      })
      .sort((a, b) => b.netSales - a.netSales),
    // Build chronological daily aggregates; use a separate copy for revenue rankings.
    dayFacts = c.Date
      ? group(rows, "Date")
          .map(([date, r]) => ({
            date,
            netSales: Math.round(sum(r, "Net_Sales") * 100) / 100,
            grossProfit: c.Gross_Profit
              ? Math.round(sum(r, "Gross_Profit") * 100) / 100
              : null,
          }))
          .sort((a, b) => a.date.localeCompare(b.date))
      : [],
    sortedDaysBySales = [...dayFacts].sort((a, b) => b.netSales - a.netSales),
    // Aggregate dates into Monday-based weeks and year-months so different years stay separate.
    weekFacts = c.Date
      ? group(
          rows.map((r) => ({ ...r, Week: weekKey(r.Date) })),
          "Week",
        )
          .map(([week, r]) => ({ week, netSales: round2(sum(r, "Net_Sales")) }))
          .sort((a, b) => b.netSales - a.netSales)
      : [],
    monthFacts = c.Date
      ? group(
          rows.map((r) => ({ ...r, Month: r.Date.slice(0, 7) })),
          "Month",
        )
          .map(([month, r]) => ({
            month,
            netSales: round2(sum(r, "Net_Sales")),
          }))
          .sort((a, b) => b.netSales - a.netSales)
      : [],
    // Compare weekdays and time-of-day buckets with optional units and validated order counts.
    weekdayFacts = c.Date
      ? group(
          rows.map((r) => ({
            ...r,
            Weekday: dayNames[new Date(r.Date + "T12:00:00Z").getUTCDay()],
          })),
          "Weekday",
        )
          .map(([weekday, r]) => ({
            weekday,
            netSales: round2(sum(r, "Net_Sales")),
            units: c.Quantity ? sum(r, "Quantity") : null,
            orders: uniqueOrders(r),
            averageOrderValue: aov(r),
          }))
          .sort((a, b) => b.netSales - a.netSales)
      : [],
    periodFacts = c.Hour
      ? group(
          rows.map((r) => ({ ...r, Period: period(r.Hour) })),
          "Period",
        )
          .map(([name, r]) => ({
            name,
            netSales: round2(sum(r, "Net_Sales")),
            units: c.Quantity ? sum(r, "Quantity") : null,
            orders: uniqueOrders(r),
          }))
          .sort((a, b) => b.netSales - a.netSales)
      : [],
    hourFacts = c.Hour
      ? group(rows, "Hour")
          .map(([hour, r]) => ({
            hour,
            netSales: round2(sum(r, "Net_Sales")),
            units: c.Quantity ? sum(r, "Quantity") : null,
            orders: uniqueOrders(r),
            averageOrderValue: aov(r),
          }))
          .sort((a, b) => b.netSales - a.netSales)
      : [],
    // Separate rows with positive discounts for later discount-versus-no-discount summaries.
    discountedRows = c.Discount_Amount
      ? rows.filter((r) => Number(r.Discount_Amount) > 0)
      : [],
    undiscountedRows = c.Discount_Amount
      ? rows.filter((r) => !(Number(r.Discount_Amount) > 0))
      : [],
    // Optional groupings only work when their columns exist in normalized rows.
    paymentFacts =
      "Payment_Method" in (rows[0] || {})
        ? group(rows, "Payment_Method")
            .map(([name, r]) => ({
              name,
              netSales: round2(sum(r, "Net_Sales")),
              orders: uniqueOrders(r),
              averageOrderValue: aov(r),
            }))
            .sort((a, b) => b.netSales - a.netSales)
        : [],
    locationFacts =
      "Store_Location" in (rows[0] || {})
        ? group(rows, "Store_Location")
            .map(([name, r]) => ({
              name,
              netSales: round2(sum(r, "Net_Sales")),
              grossProfit: c.Gross_Profit
                ? round2(sum(r, "Gross_Profit"))
                : null,
              grossMarginPercent:
                c.Gross_Profit && sum(r, "Net_Sales") > 0
                  ? Math.round(
                      (sum(r, "Gross_Profit") / sum(r, "Net_Sales")) * 1000,
                    ) / 10
                  : null,
              orders: uniqueOrders(r),
            }))
            .sort((a, b) => b.netSales - a.netSales)
        : [],
    employeeFacts =
      "Employee_Name" in (rows[0] || {})
        ? group(rows, "Employee_Name")
            .map(([name, r]) => ({
              name,
              netSales: round2(sum(r, "Net_Sales")),
              orders: uniqueOrders(r),
            }))
            .sort((a, b) => b.netSales - a.netSales)
        : [],
    orderFacts = c.orders
      ? group(rows, "Order_Key")
          .map(([name, r]) => {
            const netSales = round2(sum(r, "Net_Sales")),
              grossProfit = c.Gross_Profit
                ? round2(sum(r, "Gross_Profit"))
                : null,
              orderUnits = c.Quantity ? sum(r, "Quantity") : null,
              productNames = [...new Set(r.map((item) => item.Product_Name))],
              categoryNames = [...new Set(r.map((item) => item.Category))];
            return {
              name,
              netSales,
              grossProfit,
              grossMarginPercent:
                grossProfit !== null && netSales > 0
                  ? Math.round((grossProfit / netSales) * 1000) / 10
                  : null,
              units: orderUnits,
              lines: r.length,
              products: productNames,
              categories: categoryNames,
              productCount: productNames.length,
              categoryCount: categoryNames.length,
              hasDiscount: c.Discount_Amount
                ? r.some((item) => Number(item.Discount_Amount) > 0)
                : null,
              hasNegativeSales: r.some((item) => Number(item.Net_Sales) < 0),
            };
          })
          .sort((a, b) => b.netSales - a.netSales)
      : [],
    averageOrderSales =
      orderFacts.length > 0
        ? round2(sum(orderFacts, "netSales") / orderFacts.length)
        : null,
    medianOrderSales = orderFacts.length
      ? round2(median(orderFacts.map((order) => order.netSales)))
      : null,
    topOrders = orderFacts.slice(0, 5),
    topOrdersByGrossProfit = c.Gross_Profit
      ? topBy(orderFacts, "grossProfit").slice(0, 5)
      : [],
    largeOrders =
      averageOrderSales !== null
        ? orderFacts.filter((order) => order.netSales > averageOrderSales)
        : [],
    multiProductOrders = orderFacts.filter((order) => order.productCount > 1),
    singleProductOrders = orderFacts.filter((order) => order.productCount <= 1),
    productPairFacts = c.orders
      ? Object.values(
          orderFacts.reduce((pairs, order) => {
            const names = [...order.products].sort();
            for (let i = 0; i < names.length; i++)
              for (let j = i + 1; j < names.length; j++) {
                const key = `${names[i]} + ${names[j]}`;
                if (!pairs[key])
                  pairs[key] = { name: key, orders: 0, netSales: 0 };
                pairs[key].orders += 1;
                pairs[key].netSales = round2(pairs[key].netSales + order.netSales);
              }
            return pairs;
          }, {}),
        ).sort((a, b) => b.orders - a.orders || b.netSales - a.netSales)
      : [],
    categoryPairFacts = c.orders
      ? Object.values(
          orderFacts.reduce((pairs, order) => {
            const names = [...order.categories].sort();
            for (let i = 0; i < names.length; i++)
              for (let j = i + 1; j < names.length; j++) {
                const key = `${names[i]} + ${names[j]}`;
                if (!pairs[key])
                  pairs[key] = { name: key, orders: 0, netSales: 0 };
                pairs[key].orders += 1;
                pairs[key].netSales = round2(pairs[key].netSales + order.netSales);
              }
            return pairs;
          }, {}),
        ).sort((a, b) => b.orders - a.orders || b.netSales - a.netSales)
      : [],
    productsInLargeOrders =
      largeOrders.length > 0
        ? Object.values(
            largeOrders.reduce((result, order) => {
              order.products.forEach((name) => {
                if (!result[name])
                  result[name] = { name, orders: 0, netSales: 0 };
                result[name].orders += 1;
                result[name].netSales = round2(result[name].netSales + order.netSales);
              });
              return result;
            }, {}),
          ).sort((a, b) => b.orders - a.orders || b.netSales - a.netSales)
        : [],
    productQuantityPerOrder = c.orders
      ? productFacts
          .map((product) => {
            const matchingOrders = orderFacts.filter((order) =>
              order.products.includes(product.name),
            ).length;
            return {
              name: product.name,
              unitsPerOrder:
                c.Quantity && matchingOrders
                  ? round2(product.units / matchingOrders)
                  : null,
              matchingOrders,
            };
          })
          .filter((item) => item.unitsPerOrder !== null)
          .sort((a, b) => b.unitsPerOrder - a.unitsPerOrder)
      : [],
    // Measure variation across recorded days; absent dates are not inserted as zero sales.
    dailySalesValues = dayFacts.map((day) => day.netSales),
    dailySalesStdDev = standardDeviation(dailySalesValues),
    dailySalesAverage =
      dayFacts.length > 0 ? sum(dayFacts, "netSales") / dayFacts.length : null,
    uniqueHours = c.Hour ? [...new Set(rows.map((r) => r.Hour))].sort((a, b) => a - b) : [],
    // Count date/hour combinations with sales, not actual scheduled operating hours.
    recordedOperatingHours =
      c.Date && c.Hour
        ? new Set(rows.map((r) => `${r.Date}|${r.Hour}`)).size
        : null,
    firstSaleHours = c.Date && c.Hour
      ? group(rows, "Date").map(([, r]) => Math.min(...r.map((item) => item.Hour)))
      : [],
    lastSaleHours = c.Date && c.Hour
      ? group(rows, "Date").map(([, r]) => Math.max(...r.map((item) => item.Hour)))
      : [],
    lastHourRevenue = c.Date && c.Hour
      ? round2(
          sum(
            group(rows, "Date").flatMap(([, r]) => {
              const lastHour = Math.max(...r.map((item) => item.Hour));
              return r.filter((item) => item.Hour === lastHour);
            }),
            "Net_Sales",
          ),
        )
      : null,
    beginningMonthRows = c.Date
      ? rows.filter((r) => Number(r.Date.slice(8, 10)) <= 10)
      : [],
    endMonthRows = c.Date
      ? rows.filter((r) => Number(r.Date.slice(8, 10)) >= 21)
      : [],
    // Average revenue over recorded dates within each uploaded weather label.
    weatherFacts =
      "Weather" in (rows[0] || {}) && c.Date
        ? group(rows, "Weather")
            .map(([name, r]) => ({
              name,
              netSales: round2(sum(r, "Net_Sales")),
              days: new Set(r.map((item) => item.Date)).size,
              averageDailyNetSales: round2(
                sum(r, "Net_Sales") / new Set(r.map((item) => item.Date)).size,
              ),
            }))
            .sort((a, b) => b.averageDailyNetSales - a.averageDailyNetSales)
        : [],
    // Compare earlier and later recorded dates; these differences are descriptive, not forecasts.
    productGrowth = compareHalves(rows, "Product_Name"),
    categoryGrowth = compareHalves(rows, "Category"),
    firstHalfSales =
      dayFacts.length > 1
        ? sum(dayFacts.slice(0, Math.floor(dayFacts.length / 2)), "netSales")
        : null,
    secondHalfSales =
      dayFacts.length > 1
        ? sum(dayFacts.slice(Math.floor(dayFacts.length / 2)), "netSales")
        : null;
  return {
    // Keep these values JSON-safe because they are sent to the Python server.
    business: meta.business,
    currency: meta.currency,
    selectedRows: rows.length,
    sourceRows: meta.sourceRows,
    dateRange: { from: meta.dateMin, to: meta.dateMax },
    netSales: Math.round(n * 100) / 100,
    grossProfit: c.Gross_Profit ? Math.round(g * 100) / 100 : null,
    grossMarginPercent:
      c.Gross_Profit && n > 0 ? Math.round((g / n) * 1000) / 10 : null,
    grossSales: c.Gross_Sales ? Math.round(gross * 100) / 100 : null,
    discounts: c.Discount_Amount ? Math.round(discount * 100) / 100 : null,
    discountRatePercent:
      c.Gross_Sales && c.Discount_Amount && gross > 0
        ? Math.round((discount / gross) * 1000) / 10
        : null,
    units: c.Quantity ? sum(rows, "Quantity") : null,
    averageDailyNetSales:
      dayFacts.length > 0
        ? Math.round((n / dayFacts.length) * 100) / 100
        : null,
    trendComparison:
      firstHalfSales !== null && secondHalfSales !== null && firstHalfSales > 0
        ? {
            firstHalfNetSales: Math.round(firstHalfSales * 100) / 100,
            secondHalfNetSales: Math.round(secondHalfSales * 100) / 100,
            secondVsFirstPercent:
              Math.round(
                ((secondHalfSales - firstHalfSales) / firstHalfSales) * 1000,
              ) / 10,
          }
        : null,
    matchingOrders: c.orders
      ? new Set(rows.map((r) => r.Order_Key)).size
      : null,
    selectedRevenuePerMatchingOrder:
      c.orders && rows.length
        ? Math.round((n / new Set(rows.map((r) => r.Order_Key)).size) * 100) /
          100
        : null,
    // Summarize validated orders; do not treat each line item as a separate order.
    orderStats: c.orders
      ? {
          averageOrderValue: averageOrderSales,
          medianOrderValue: medianOrderSales,
          medianVsAverage:
            averageOrderSales && medianOrderSales !== null
              ? round2(medianOrderSales - averageOrderSales)
              : null,
          percentOrdersUnder10: orderFacts.length
            ? Math.round(
                (orderFacts.filter((order) => order.netSales < 10).length /
                  orderFacts.length) *
                  1000,
              ) / 10
            : null,
          percentNegativeOrders: orderFacts.length
            ? Math.round(
                (orderFacts.filter((order) => order.netSales < 0).length /
                  orderFacts.length) *
                  1000,
              ) / 10
            : null,
          zeroNetOrders: orderFacts.filter((order) => order.netSales === 0).length,
          percentRevenueTop3Orders:
            n > 0
              ? Math.round((sum(orderFacts.slice(0, 3), "netSales") / n) * 1000) /
                10
              : null,
          revenueAboveAverageOrder: round2(sum(largeOrders, "netSales")),
          averageLinesPerOrder: orderFacts.length
            ? round2(sum(orderFacts, "lines") / orderFacts.length)
            : null,
          singleProductOrders: singleProductOrders.length,
          multiProductOrders: multiProductOrders.length,
          singleProductRevenue: round2(sum(singleProductOrders, "netSales")),
          multiProductRevenue: round2(sum(multiProductOrders, "netSales")),
        }
      : null,
    topOrders,
    topOrdersByGrossProfit,
    productPairs: productPairFacts.slice(0, 8),
    categoryPairs: categoryPairFacts.slice(0, 8),
    productsInLargeOrders: productsInLargeOrders.slice(0, 8),
    productQuantityPerOrder: productQuantityPerOrder.slice(0, 8),
    // Attach the current selection so facts can be interpreted within the correct scope.
    filters: Object.fromEntries(
      ["from", "to", "category", "product", "weekday", "period"].map((id) => [
        id,
        $(id).value,
      ]),
    ),
    // Expose bounded rankings for the built-in question matcher and optional fact-summary endpoint.
    topProducts: productFacts.slice(0, 10),
    bottomProductsByRevenue: [...productFacts]
      .filter((p) => p.netSales > 0)
      .sort((a, b) => a.netSales - b.netSales)
      .slice(0, 10),
    bottomProductsByUnits: c.Quantity
      ? [...productFacts]
          .filter((p) => p.units > 0)
          .sort((a, b) => a.units - b.units)
          .slice(0, 10)
      : [],
    topProductsByUnits: c.Quantity
      ? topBy(productFacts, "units").slice(0, 10)
      : [],
    topProductsByGrossProfit: c.Gross_Profit
      ? topBy(productFacts, "grossProfit").slice(0, 10)
      : [],
    bottomProductsByGrossProfit: c.Gross_Profit
      ? bottomBy(productFacts, "grossProfit").slice(0, 10)
      : [],
    topProductsByMargin: c.Gross_Profit
      ? topBy(productFacts, "grossMarginPercent").slice(0, 10)
      : [],
    bottomProductsByMargin: c.Gross_Profit
      ? bottomBy(productFacts, "grossMarginPercent").slice(0, 10)
      : [],
    productGrowth: productGrowth.slice(0, 10),
    productDeclines: [...productGrowth].reverse().slice(0, 10),
    topCategories: categoryFacts.slice(0, 8),
    bottomCategoriesByRevenue: [...categoryFacts]
      .filter((p) => p.netSales > 0)
      .sort((a, b) => a.netSales - b.netSales)
      .slice(0, 8),
    topCategoriesByUnits: c.Quantity
      ? topBy(categoryFacts, "units").slice(0, 8)
      : [],
    bottomCategoriesByUnits: c.Quantity
      ? bottomBy(categoryFacts, "units").slice(0, 8)
      : [],
    topCategoriesByGrossProfit: c.Gross_Profit
      ? topBy(categoryFacts, "grossProfit").slice(0, 8)
      : [],
    topCategoriesByMargin: c.Gross_Profit
      ? topBy(categoryFacts, "grossMarginPercent").slice(0, 8)
      : [],
    bottomCategoriesByMargin: c.Gross_Profit
      ? bottomBy(categoryFacts, "grossMarginPercent").slice(0, 8)
      : [],
    categoryGrowth: categoryGrowth.slice(0, 8),
    topDays: sortedDaysBySales.slice(0, 7),
    bottomDays: [...sortedDaysBySales].reverse().slice(0, 7),
    topWeeks: weekFacts.slice(0, 5),
    topMonths: monthFacts.slice(0, 5),
    dateSummary: c.Date
      ? {
          earliestDate: dayFacts[0]?.date || null,
          latestDate: dayFacts[dayFacts.length - 1]?.date || null,
          monthsCovered: new Set(dayFacts.map((day) => day.date.slice(0, 7))).size,
          averageBusinessDayRevenue:
            dayFacts.length > 0 ? round2(n / dayFacts.length) : null,
          dailySalesStdDev:
            dailySalesStdDev !== null ? round2(dailySalesStdDev) : null,
          dailySalesVariationPercent:
            dailySalesStdDev !== null && dailySalesAverage
              ? Math.round((dailySalesStdDev / dailySalesAverage) * 1000) / 10
              : null,
          beginningMonthRevenue: round2(sum(beginningMonthRows, "Net_Sales")),
          endMonthRevenue: round2(sum(endMonthRows, "Net_Sales")),
        }
      : null,
    weekdays: weekdayFacts,
    periods: periodFacts,
    topHours: hourFacts.slice(0, 6),
    hourSummary: c.Hour
      ? {
          recordedHours: uniqueHours,
          recordedOperatingHours,
          revenuePerRecordedOperatingHour:
            recordedOperatingHours && recordedOperatingHours > 0
              ? round2(n / recordedOperatingHours)
              : null,
          unitsPerRecordedOperatingHour:
            recordedOperatingHours && recordedOperatingHours > 0 && c.Quantity
              ? round2(sum(rows, "Quantity") / recordedOperatingHours)
              : null,
          typicalFirstSaleHour: firstSaleHours.length
            ? round2(median(firstSaleHours))
            : null,
          typicalLastSaleHour: lastSaleHours.length
            ? round2(median(lastSaleHours))
            : null,
          lastRecordedHourRevenue: lastHourRevenue,
        }
      : null,
    bottomHoursByUnits: c.Quantity
      ? bottomBy(hourFacts, "units").slice(0, 6)
      : [],
    topHoursByAov: topBy(hourFacts, "averageOrderValue").slice(0, 6),
    discountSummary: c.Discount_Amount
      ? {
          discountedRevenue: round2(sum(discountedRows, "Net_Sales")),
          undiscountedRevenue: round2(sum(undiscountedRows, "Net_Sales")),
          discountedUnits: c.Quantity ? sum(discountedRows, "Quantity") : null,
          undiscountedUnits: c.Quantity
            ? sum(undiscountedRows, "Quantity")
            : null,
          discountedMarginPercent:
            c.Gross_Profit && sum(discountedRows, "Net_Sales") > 0
              ? Math.round(
                  (sum(discountedRows, "Gross_Profit") /
                    sum(discountedRows, "Net_Sales")) *
                    1000,
                ) / 10
              : null,
          undiscountedMarginPercent:
            c.Gross_Profit && sum(undiscountedRows, "Net_Sales") > 0
              ? Math.round(
                  (sum(undiscountedRows, "Gross_Profit") /
                    sum(undiscountedRows, "Net_Sales")) *
                    1000,
                ) / 10
              : null,
          discountedOrderPercent:
            c.orders && uniqueOrders(rows)
              ? Math.round(
                  (uniqueOrders(discountedRows) / uniqueOrders(rows)) * 1000,
                ) / 10
              : null,
        }
      : null,
    topProductsByDiscounts: c.Discount_Amount
      ? topBy(productFacts, "discounts").slice(0, 8)
      : [],
    topCategoriesByDiscounts: c.Discount_Amount
      ? topBy(categoryFacts, "discounts").slice(0, 8)
      : [],
    topPayments: paymentFacts.slice(0, 8),
    topLocations: locationFacts.slice(0, 8),
    topLocationsByMargin: topBy(locationFacts, "grossMarginPercent").slice(
      0,
      8,
    ),
    weather: weatherFacts.slice(0, 8),
    topEmployees: employeeFacts.slice(0, 8),
    topEmployeesByOrders: topBy(employeeFacts, "orders").slice(0, 8),
    // Report coverage and suspicious values alongside totals rather than silently removing records.
    dataQuality: {
      zeroQuantityLines: c.Quantity
        ? rows.filter((row) => Number(row.Quantity) === 0).length
        : null,
      negativeSalesLines: rows.filter((row) => Number(row.Net_Sales) < 0).length,
      unusuallyLargeLines:
        rows.length > 0
          ? rows
              .map((row) => Number(row.Net_Sales) || 0)
              .filter((value) => value > 0)
              .sort((a, b) => b - a)
              .slice(0, 5)
          : [],
      activeFilters: Object.fromEntries(
        ["from", "to", "category", "product", "weekday", "period"]
          .filter((id) => $(id).value)
          .map((id) => [id, $(id).value]),
      ),
      suppliedMetrics: Object.entries(c)
        .filter(([, available]) => available)
        .map(([key]) => key),
      calculatedMetrics: [
        "net sales",
        "gross margin when profit is available",
        "rankings",
        "trend comparison",
        "average order value when order IDs are valid",
      ],
    },
    availableMetrics: {
      product: c.product,
      category: c.category,
      date: c.Date,
      hour: c.Hour,
      quantity: c.Quantity,
      grossProfit: c.Gross_Profit,
      orders: c.orders,
      discounts: c.Discount_Amount,
    },
    daysCovered: c.Date ? new Set(rows.map((r) => r.Date)).size : null,
    limitations: meta.warnings,
  };
}
function renderInsights(rows) {
  // Three compact summary cards on the overview page.
  if (!rows.length) {
    $("insightCards").innerHTML = note("No sales match these filters.");
    return;
  }
  const f = facts(rows),
    p = f.topProducts[0],
    d = f.topDays[0],
    cards = [];
  cards.push([
    meta.capabilities.product
      ? p.name + " leads " + businessProfile(meta.business).item.toLowerCase() + " revenue"
      : "Selected revenue",
    money(p.netSales) +
      (f.netSales > 0
        ? " · " + pct((p.netSales / f.netSales) * 100) + " of selected sales"
        : ""),
    "Review product costs and stock before changing promotions.",
  ]);
  cards.push(
    d
      ? [
          d.date + " leads recorded daily sales",
          money(d.netSales) + " in selected sales.",
          "Verify comparable daily coverage before changing staffing.",
        ]
      : [
          "Date data unavailable",
          "Map a date column for trend analysis.",
          "The dashboard can still compare product and category totals.",
        ],
  );
  cards.push(
    meta.capabilities.Gross_Profit
      ? [
          "Gross margin",
          f.grossMarginPercent === null
            ? "Margin needs positive net sales."
            : pct(f.grossMarginPercent) + " across selected sales.",
          "Gross profit still needs to cover operating expenses.",
        ]
      : [
          "Profit data unavailable",
          "Sales alone cannot establish profitability.",
          "Add unit costs, total product costs, or gross profit.",
        ],
  );
  $("insightCards").innerHTML = cards
    .map(
      (r, i) =>
        `<article><strong>${i + 1}. ${esc(r[0])}</strong><p>${esc(r[1])}</p><small>${esc(r[2])}</small></article>`,
    )
    .join("");
}
function calculatedAnswer(question) {
  // Deterministic answers cover common business questions without using AI.
  const f = facts(),
    q = question.toLowerCase();
  if (!f.selectedRows) return "No sales match the current filters.";
  const topProduct = f.topProducts[0],
    leastRevenueProduct = f.bottomProductsByRevenue[0],
    leastUnitProduct = f.bottomProductsByUnits[0],
    namedProduct = findNamed(
      f.topProducts.concat(f.bottomProductsByRevenue),
      q,
    ),
    topCategory = f.topCategories[0],
    leastCategory = f.bottomCategoriesByRevenue[0],
    topDay = f.topDays[0],
    lowDay = f.bottomDays[0],
    trend = f.trendComparison;
  if (
    /promotion|coupon|free[- ]?delivery|upsell|price override|giveaway|given away|bundle/.test(
      q,
    )
  )
    return missingDataAnswer(
      "Promotion, coupon, bundle, and campaign performance",
      "promotion names, coupon codes, campaign dates, bundle IDs, direct promotion costs, and return/refund flags",
    );
  if (
    /inventory|stock|supplier|purchase order|reorder|stockout|available stock|counted stock|ingredient|expire|damaged stock|stolen|lost/.test(
      q,
    )
  ) {
    if (/restock|restocking|reorder candidate/.test(q))
      return `${topProduct.name} is a restocking candidate because it leads selected revenue at ${money(topProduct.netSales)}${topProduct.units !== null ? " and " + topProduct.units + " units" : ""}. True inventory decisions need stock-on-hand, reorder levels, supplier lead time, and spoilage or storage limits.`;
    return missingDataAnswer(
      "Inventory, stockout, supplier, ingredient, and purchase-order analysis",
      "current stock, stock counts, reorder levels, supplier records, purchase orders, delivery dates, stockout dates, ingredient recipes, and waste/expiry records",
    );
  }
  if (
    /customer|customers|loyalty|repeat|new customer|lifetime|contact information|segment|business customer|bulk customer|joined/.test(
      q,
    )
  )
    return missingDataAnswer(
      "Customer, loyalty, retention, and customer-segment analysis",
      "customer IDs, customer type, first-purchase dates, contact fields, loyalty membership, and customer-order history",
    );
  if (
    /operating expense|expenses|net profit|rent|payroll|labor|staff hour|fixed cost|variable expense|card-processing|transaction fee|delivery fee|cash flow|owe|unpaid invoice|deposit|collected cash|recognized sales/.test(
      q,
    )
  )
    return f.grossProfit === null
      ? missingDataAnswer(
          "Operating expense, cash collection, and net profit analysis",
          "product costs or gross profit, rent, payroll, labor hours, payment fees, invoices, deposits, refunds, and cash collection records",
        )
      : `Gross profit is ${money(f.grossProfit)}, but net profit and cash collection are not available because operating expenses, labor, fees, invoices, deposits, and collected-cash records are not mapped.`;
  if (
    /website|online|cart|conversion|mobile|desktop|advertising|referral|shipping|sales channel|delivery area|pickup|delivery orders|in-store|in store/.test(
      q,
    )
  )
    return missingDataAnswer(
      "Online, channel, delivery, conversion, and advertising analysis",
      "sales channel, website visits, carts, device type, shipping costs, delivery area, pickup/delivery timestamps, referral source, ad spend, and return records by channel",
    );
  if (
    /restaurant|dish|preparation|prep|table|guest|party size|dine[- ]?in|takeaway|kitchen station|seated|seating|food waste|remade|appetizer|topping|upgrade/.test(
      q,
    )
  )
    return missingDataAnswer(
      "Restaurant operations analysis",
      "prep times, table times, party size, guest count, dining mode, cancellations, food waste, remakes, modifiers, and kitchen station data",
    );
  if (
    /quotation|quote|assembly|installation|warranty|furniture.*delay/.test(q)
  )
    return missingDataAnswer(
      "Furniture quotation, delivery, service, and warranty analysis",
      "quotation dates/statuses, delivery promises, assembly and installation fees/costs, warranty claims, and product service records",
    );
  // These topics require additional business context that the current mapped rows do not contain.
  if (/target|goal|quota/.test(q))
    // Targets are business inputs, not something the sales file can infer.
    return "Sales targets are not included in this dataset. I can show current sales, but I need a target amount to say whether the business met it or how much more revenue is needed.";
  if (/forecast|next month|future|predict/.test(q))
    return trend
      ? `A simple trend check shows second-half sales were ${trend.secondVsFirstPercent >= 0 ? "up" : "down"} ${pct(Math.abs(trend.secondVsFirstPercent))} versus the first half. That is not a forecast; use it as a starting point and compare it with seasonality, promotions, and upcoming business changes.`
      : "There is not enough dated sales history in the current selection to estimate a next-month pattern.";
  // Data-quality questions explain duplicate handling before ordinary metric matching.
  if (/duplicate/.test(q))
    return f.limitations.some((w) => /duplicate/i.test(w))
      ? f.limitations.find((w) => /duplicate/i.test(w))
      : "No duplicate-row warning is currently shown for this selected dataset.";
  if (
    /missing|blank|invalid|inconsistent|reused|match|negative|partial|reliable|enough data|data quality|important columns/.test(
      q,
    )
  )
    // Data-quality questions are answered from warnings generated during normalization.
    return `Data notes: ${f.limitations.join(" ")} Some checks depend on mapped columns; targets, inventory, customer data, labor hours, sales channels, and operating expenses are not available unless your file includes them.`;
  // Match common total and order questions against precomputed facts; branch order matters.
  if (/total net|net sales|total revenue/.test(q))
    return `Total selected net sales are ${money(f.netSales)}.`;
  if (/gross sales/.test(q))
    return f.grossSales === null
      ? "Gross sales are not mapped in this dataset."
      : `Total selected gross sales are ${money(f.grossSales)}.`;
  if (/how many units|units did we sell|total units/.test(q))
    return f.units === null
      ? "Quantity is not mapped, so total units are unavailable."
      : `Total selected units sold are ${f.units.toLocaleString()}.`;
  if (/how many orders|orders did we receive/.test(q))
    return f.matchingOrders === null
      ? "Order IDs are missing or inconsistent, so order count is unavailable."
      : `The selected data contains ${f.matchingOrders.toLocaleString()} matching orders.`;
  if (/largest order|biggest order/.test(q))
    return f.topOrders[0]
      ? `The largest matching order by revenue is ${money(f.topOrders[0].netSales)} with ${f.topOrders[0].lines} sales lines.`
      : "Largest order needs valid order IDs.";
  if (/most profitable order/.test(q))
    return f.topOrdersByGrossProfit[0]
      ? `The most profitable matching order generated ${money(f.topOrdersByGrossProfit[0].grossProfit)} of gross profit from ${money(f.topOrdersByGrossProfit[0].netSales)} in net sales.`
      : "Most profitable order needs valid order IDs and gross profit or cost data.";
  if (/median order/.test(q))
    return f.orderStats?.medianOrderValue != null
      ? `The median matching order value is ${money(f.orderStats.medianOrderValue)}. The average order value is ${money(f.orderStats.averageOrderValue)}, so the median is ${money(Math.abs(f.orderStats.medianVsAverage))} ${f.orderStats.medianVsAverage >= 0 ? "higher" : "lower"} than the average.`
      : "Median order value needs valid order IDs.";
  if (/orders?.*(less than|under|below).*\$?10/.test(q))
    return f.orderStats?.percentOrdersUnder10 != null
      ? `${pct(f.orderStats.percentOrdersUnder10)} of matching orders are worth less than $10.`
      : "This needs valid order IDs.";
  if (/three largest orders|top 3 orders|3 largest orders/.test(q))
    return f.orderStats?.percentRevenueTop3Orders != null
      ? `The three largest matching orders contribute ${pct(f.orderStats.percentRevenueTop3Orders)} of selected revenue.`
      : "This needs valid order IDs and positive selected revenue.";
  if (/negative net sales/.test(q) && /order/.test(q))
    return f.orderStats?.percentNegativeOrders != null
      ? `${pct(f.orderStats.percentNegativeOrders)} of matching orders have negative net sales.`
      : "Negative-order analysis needs valid order IDs.";
  if (/zero net sales/.test(q) && /order/.test(q))
    return f.orderStats
      ? `${f.orderStats.zeroNetOrders.toLocaleString()} matching orders have zero net sales.`
      : "Zero-order analysis needs valid order IDs.";
  if (/product lines|lines.*order|typical order contain/.test(q))
    return f.orderStats?.averageLinesPerOrder != null
      ? `A matching order contains about ${f.orderStats.averageLinesPerOrder} sales lines on average.`
      : "Product-line-per-order analysis needs valid order IDs.";
  if (/single-product|single product|multiple products|multi-product/.test(q))
    return f.orderStats
      ? `Single-product orders: ${f.orderStats.singleProductOrders.toLocaleString()} orders and ${money(f.orderStats.singleProductRevenue)} revenue. Multi-product orders: ${f.orderStats.multiProductOrders.toLocaleString()} orders and ${money(f.orderStats.multiProductRevenue)} revenue.`
      : "Single-product versus multi-product comparison needs valid order IDs.";
  if (/above the average order value|orders above average/.test(q))
    return f.orderStats
      ? `${money(f.orderStats.revenueAboveAverageOrder)} of selected revenue comes from matching orders above the average order value.`
      : "This needs valid order IDs.";
  if (/purchased together|usually purchased|buy alongside|combinations|commonly purchased/.test(q)) {
    if (/categor/.test(q) && f.categoryPairs[0])
      return `Most common category combinations include ${f.categoryPairs
        .slice(0, 3)
        .map((pair) => `${pair.name} (${pair.orders} orders)`)
        .join("; ")}.`;
    return f.productPairs[0]
      ? `Most common product combinations include ${f.productPairs
          .slice(0, 3)
          .map((pair) => `${pair.name} (${pair.orders} orders)`)
          .join("; ")}.`
      : "Product-combination analysis needs valid order IDs with multiple product lines per order.";
  }
  if (/large orders/.test(q) && /product/.test(q))
    return f.productsInLargeOrders[0]
      ? `Products that appear most often in above-average orders include ${f.productsInLargeOrders
          .slice(0, 3)
          .map((item) => `${item.name} (${item.orders} orders)`)
          .join("; ")}.`
      : "This needs valid order IDs and enough above-average orders.";
  if (/average order value|aov/.test(q) && !/payment|day|hour/.test(q))
    return f.selectedRevenuePerMatchingOrder === null
      ? "Average order value needs valid order IDs."
      : `Average order value is ${money(f.selectedRevenuePerMatchingOrder)}.`;
  if (/units.*per order|customers buy per order/.test(q))
    return f.matchingOrders && f.units !== null
      ? `Customers bought about ${(f.units / f.matchingOrders).toFixed(2)} units per matching order.`
      : "Units per order needs both quantity and valid order IDs.";
  // Choose discount comparisons only when the needed amount columns exist.
  if (/discount/.test(q)) {
    // Discount questions share one branch because they use the same split data.
    if (!f.discountSummary)
      return "Discount data is not mapped in this dataset.";
    if (/order/.test(q) && /percent|included/.test(q))
      return f.discountSummary.discountedOrderPercent === null
        ? "Percent of discounted orders needs valid order IDs."
        : `${pct(f.discountSummary.discountedOrderPercent)} of matching orders included a discount.`;
    if (/without|undiscounted/.test(q))
      return `Revenue without discounts was ${money(f.discountSummary.undiscountedRevenue)}.`;
    if (/with|discounted sales|came from discounted/.test(q))
      return `Revenue from discounted sales was ${money(f.discountSummary.discountedRevenue)}.`;
    if (/margin/.test(q))
      return `Discounted sales margin was ${f.discountSummary.discountedMarginPercent === null ? "not available" : pct(f.discountSummary.discountedMarginPercent)}; undiscounted sales margin was ${f.discountSummary.undiscountedMarginPercent === null ? "not available" : pct(f.discountSummary.undiscountedMarginPercent)}.`;
    if (/category/.test(q) && f.topCategoriesByDiscounts[0])
      return `${f.topCategoriesByDiscounts[0].name} received the most discounts at ${money(f.topCategoriesByDiscounts[0].discounts)}.`;
    if (/product/.test(q) && f.topProductsByDiscounts[0])
      return `${f.topProductsByDiscounts[0].name} received the most discounts at ${money(f.topProductsByDiscounts[0].discounts)}.`;
    return `Total discounts were ${money(f.discounts)}${f.discountRatePercent !== null ? ", or " + pct(f.discountRatePercent) + " of gross sales" : ""}.`;
  }
  if (/payment/.test(q)) {
    // Payment method answers work only when that optional column is mapped.
    if (!f.topPayments.length)
      return "Payment method is not mapped in this dataset.";
    if (/order|used/.test(q)) {
      const p = topBy(f.topPayments, "orders")[0];
      return p?.orders
        ? `${p.name} was used for the most matching orders: ${p.orders.toLocaleString()}.`
        : "Payment-method order counts need valid order IDs.";
    }
    if (/average/.test(q)) {
      const p = topBy(f.topPayments, "averageOrderValue")[0];
      return p?.averageOrderValue
        ? `${p.name} has the highest average order value at ${money(p.averageOrderValue)}.`
        : "Average order value by payment method needs valid order IDs.";
    }
    return `${f.topPayments[0].name} accounts for the most revenue at ${money(f.topPayments[0].netSales)}.`;
  }
  // Optional dimensions answer store and employee questions only when those fields were supplied.
  if (/location|store/.test(q)) {
    if (!f.topLocations.length)
      return "Store location is not mapped in this dataset.";
    if (/margin/.test(q) && f.topLocationsByMargin[0])
      return `${f.topLocationsByMargin[0].name} has the highest gross margin at ${pct(f.topLocationsByMargin[0].grossMarginPercent)}.`;
    return `${f.topLocations[0].name} generated the most revenue at ${money(f.topLocations[0].netSales)}.`;
  }
  if (/employee|staff/.test(q)) {
    // Employee totals are sales handled, not productivity ratings.
    if (!f.topEmployees.length)
      return "Employee is not mapped in this dataset.";
    if (/order/.test(q) && f.topEmployeesByOrders[0]?.orders)
      return `${f.topEmployeesByOrders[0].name} handled the most matching orders: ${f.topEmployeesByOrders[0].orders.toLocaleString()}.`;
    if (/hours worked|accounting for hours/.test(q))
      return "Employee hours worked are not included, so this dashboard cannot fairly compare employee productivity by hour.";
    return `${f.topEmployees[0].name} handled the most selected sales revenue at ${money(f.topEmployees[0].netSales)}.`;
  }
  if (/channel/.test(q))
    return "Sales channel is not mapped in this dashboard, so channel revenue is unavailable.";
  if (/least|lowest|worst|bottom|underperform|slowest/.test(q)) {
    // "Least sold" can mean revenue, units, profit, or margin; infer from wording.
    if (/category|department/.test(q) && leastCategory)
      return `${leastCategory.name} is the lowest category by selected revenue at ${money(leastCategory.netSales)}${leastCategory.units !== null ? ", with " + leastCategory.units + " units" : ""}. Check whether this is expected because of assortment size, seasonality, or stock availability before cutting it.`;
    if (/unit/.test(q) && leastUnitProduct)
      return `${leastUnitProduct.name} sold the fewest units: ${leastUnitProduct.units}.`;
    if (/profit/.test(q) && f.bottomProductsByGrossProfit[0])
      return `${f.bottomProductsByGrossProfit[0].name} generated the least gross profit at ${money(f.bottomProductsByGrossProfit[0].grossProfit)}.`;
    if (/margin/.test(q) && f.bottomProductsByMargin[0])
      return `${f.bottomProductsByMargin[0].name} has the lowest gross margin at ${pct(f.bottomProductsByMargin[0].grossMarginPercent)}.`;
    if (!leastRevenueProduct)
      return "There is not enough positive product revenue in the current filter to identify a least-sold item.";
    const unitText = leastUnitProduct
      ? ` By units, ${leastUnitProduct.name} is lowest at ${leastUnitProduct.units} units.`
      : "";
    return `${leastRevenueProduct.name} is lowest by selected revenue at ${money(leastRevenueProduct.netSales)}${leastRevenueProduct.units !== null ? ", with " + leastRevenueProduct.units + " units" : ""}.${unitText} Review placement, stockouts, price, and whether it is intentionally niche.`;
  }
  if (/success|successful|healthy|health|good|bad|perform|doing/.test(q)) {
    const signals = [
      `selected net sales are ${money(f.netSales)}`,
      f.grossMarginPercent !== null
        ? `gross margin is ${pct(f.grossMarginPercent)}`
        : "profit data is not mapped",
      f.averageDailyNetSales !== null
        ? `average recorded daily sales are ${money(f.averageDailyNetSales)}`
        : "date coverage is not mapped",
      trend
        ? `second-half sales are ${trend.secondVsFirstPercent >= 0 ? "up" : "down"} ${pct(Math.abs(trend.secondVsFirstPercent))} versus the first half`
        : "trend comparison is unavailable",
    ];
    return `The dashboard shows ${signals.join(", ")}. That can indicate business health, but it cannot prove overall success without targets, rent, payroll, cash flow, and owner goals. Next, compare these numbers with your break-even point and expected monthly sales target.`;
  }
  if (/selling price|listed price|price vary|price changed|price difference|different selling prices|actual selling price/.test(q))
    return missingDataAnswer(
      "Detailed price-change and listed-price analysis",
      "listed/base price, transaction-level selling price, price override flags, approval records, and enough repeated product sales to compare prices over time, employee, and time of day",
    );
  if (/less profitable after.*cost|costs increased|product costs changed|cost.*over time/.test(q))
    return missingDataAnswer(
      "Product cost-change analysis",
      "historical product costs with effective dates, or line-level cost at the time of each sale",
    );
  if (/dependent.*gross profit|gross profit.*one product/.test(q) && f.topProductsByGrossProfit[0])
    return `${f.topProductsByGrossProfit[0].name} contributes the most gross profit at ${money(f.topProductsByGrossProfit[0].grossProfit)}. Compare its share with total gross profit before relying too heavily on one product.`;
  if (/profit|margin|cost/.test(q))
    if (
      /highest|most/.test(q) &&
      /product/.test(q) &&
      f.topProductsByGrossProfit[0]
    )
      return `${f.topProductsByGrossProfit[0].name} generated the most gross profit at ${money(f.topProductsByGrossProfit[0].grossProfit)}.`;
  if (
    /highest|best/.test(q) &&
    /margin/.test(q) &&
    /product/.test(q) &&
    f.topProductsByMargin[0]
  )
    return `${f.topProductsByMargin[0].name} has the highest gross margin at ${pct(f.topProductsByMargin[0].grossMarginPercent)}.`;
  if (
    /highest|best/.test(q) &&
    /margin/.test(q) &&
    /category/.test(q) &&
    f.topCategoriesByMargin[0]
  )
    return `${f.topCategoriesByMargin[0].name} has the highest category gross margin at ${pct(f.topCategoriesByMargin[0].grossMarginPercent)}.`;
  if (
    /lowest|worst/.test(q) &&
    /margin/.test(q) &&
    /category/.test(q) &&
    f.bottomCategoriesByMargin[0]
  )
    return `${f.bottomCategoriesByMargin[0].name} has the lowest category gross margin at ${pct(f.bottomCategoriesByMargin[0].grossMarginPercent)}.`;
  if (/profit|margin|cost/.test(q))
    return f.grossProfit === null
      ? "Product costs and gross profit are unavailable. Map one of those fields before comparing profitability."
      : `Selected gross profit is ${money(f.grossProfit)}${f.grossMarginPercent !== null ? ", with a " + pct(f.grossMarginPercent) + " gross margin" : ""}. This excludes wages, rent, and other operating expenses.`;
  if (/average|order|transaction|receipt/.test(q))
    return f.matchingOrders === null
      ? "Order IDs are missing or inconsistent. Order count and average order value are unavailable until grouping is verified."
      : `${f.matchingOrders.toLocaleString()} distinct orders match these filters. Selected revenue per matching order is ${money(f.selectedRevenuePerMatchingOrder)}. Product or category filters include only their portion of each order's revenue.`;
  if (/quantity.*greater than one|typical quantity.*per order/.test(q))
    return f.productQuantityPerOrder[0]
      ? `Highest typical quantity per matching order: ${f.productQuantityPerOrder
          .slice(0, 3)
          .map((item) => `${item.name} (${item.unitsPerOrder} units/order)`)
          .join("; ")}.`
      : "Quantity per product per order needs valid order IDs and quantity data.";
  if (/newly introduced|discontinued|preferred item unavailable/.test(q))
    return missingDataAnswer(
      "New product, discontinued product, and substitute-product analysis",
      "product launch dates, discontinued dates, stockout/unavailability records, and substitution records",
    );
  if (/largest share.*discount|lose.*revenue.*discount/.test(q))
    return f.topProductsByDiscounts[0]
      ? `${f.topProductsByDiscounts[0].name} has the highest recorded discounts at ${money(f.topProductsByDiscounts[0].discounts)}. Review discount rate and margin before changing price.`
      : "Product discount analysis needs mapped discount data.";
  if (/product|item|dish|sold/.test(q)) {
    // Product questions include rankings, named product lookups, and sales mix.
    if (namedProduct)
      return `${namedProduct.name}: ${namedProduct.units !== null ? namedProduct.units + " units, " : ""}${money(namedProduct.netSales)} net sales${namedProduct.averageSellingPrice !== null ? ", average selling price " + money(namedProduct.averageSellingPrice) : ""}${namedProduct.grossProfitPerUnit !== null ? ", gross profit per unit " + money(namedProduct.grossProfitPerUnit) : ""}.`;
    if (
      /most units|best-selling|sold the most/.test(q) &&
      f.topProductsByUnits[0]
    )
      return `${f.topProductsByUnits[0].name} sold the most units: ${f.topProductsByUnits[0].units}.`;
    if (/top five|top 5/.test(q))
      return `Top five products by revenue: ${f.topProducts
        .slice(0, 5)
        .map((p) => `${p.name} (${money(p.netSales)})`)
        .join("; ")}.`;
    if (/percentage|percent.*best|share/.test(q) && topProduct)
      return `${topProduct.name} contributes ${pct((topProduct.netSales / f.netSales) * 100)} of selected revenue.`;
    if (/top five|top 5/.test(q) && /percent|percentage|share/.test(q)) {
      const total = sum(f.topProducts.slice(0, 5), "netSales");
      return `The top five products contribute ${pct((total / f.netSales) * 100)} of selected revenue.`;
    }
    if (
      /high sales.*low profit|low margin/.test(q) &&
      f.topProductsByMargin.length
    )
      return `Check high-revenue products with weaker margins first. Lowest product margins include ${f.bottomProductsByMargin
        .slice(0, 3)
        .map((p) => `${p.name} (${pct(p.grossMarginPercent)})`)
        .join("; ")}.`;
    if (
      /low sales.*high profit|high margin/.test(q) &&
      f.topProductsByMargin.length
    )
      return `Low-sales, high-margin opportunities may include ${f.topProductsByMargin
        .slice(0, 3)
        .map(
          (p) =>
            `${p.name} (${pct(p.grossMarginPercent)} margin, ${money(p.netSales)} revenue)`,
        )
        .join("; ")}.`;
    if (/increased|grew|growth/.test(q) && f.productGrowth[0])
      return `${f.productGrowth[0].name} had the largest increase, up ${money(f.productGrowth[0].change)} versus the earlier half of the selected dates.`;
    if (/decline|decreased|dropped/.test(q) && f.productDeclines[0])
      return `${f.productDeclines[0].name} had the largest decline, down ${money(Math.abs(f.productDeclines[0].change))} versus the earlier half of the selected dates.`;
    return `${topProduct.name} leads selected revenue at ${money(topProduct.netSales)}${topProduct.units !== null ? ", with " + topProduct.units + " units sold" : ""}. ${leastRevenueProduct ? leastRevenueProduct.name + " is lowest by revenue at " + money(leastRevenueProduct.netSales) + "." : ""} Compare revenue with margin and stock before changing promotions.`;
  }
  if (/category|department/.test(q) && topCategory) {
    // Category answers use category summaries created in facts().
    if (
      /least|lowest|fewest/.test(q) &&
      /unit/.test(q) &&
      f.bottomCategoriesByUnits[0]
    )
      return `${f.bottomCategoriesByUnits[0].name} sold the fewest units: ${f.bottomCategoriesByUnits[0].units}.`;
    if (/most/.test(q) && /unit/.test(q) && f.topCategoriesByUnits[0])
      return `${f.topCategoriesByUnits[0].name} sold the most units: ${f.topCategoriesByUnits[0].units}.`;
    if (/profit/.test(q) && f.topCategoriesByGrossProfit[0])
      return `${f.topCategoriesByGrossProfit[0].name} generated the most gross profit at ${money(f.topCategoriesByGrossProfit[0].grossProfit)}.`;
    if (/percentage|percent|share|each/.test(q))
      return `Category revenue shares: ${f.topCategories.map((c) => `${c.name} ${pct((c.netSales / f.netSales) * 100)}`).join("; ")}.`;
    if (/within each/.test(q))
      return "Best-selling product within each category is not summarized yet in this view, but the dashboard can rank products after filtering by category.";
    if (/grew|growth|fastest/.test(q) && f.categoryGrowth[0])
      return `${f.categoryGrowth[0].name} grew the most, up ${money(f.categoryGrowth[0].change)} versus the earlier half of the selected dates.`;
    return `${topCategory.name} leads selected category revenue at ${money(topCategory.netSales)}.${leastCategory ? " " + leastCategory.name + " is lowest at " + money(leastCategory.netSales) + "." : ""} Category totals can be affected by the number of products in each category.`;
  }
  // Use recorded date coverage for time questions; missing dates do not establish closed days.
  if (/earliest|latest|date range|dates in the dataset/.test(q))
    return f.dateSummary
      ? `The selected dataset runs from ${f.dateSummary.earliestDate} to ${f.dateSummary.latestDate}.`
      : "Map a date column to identify the earliest and latest dates.";
  if (/months of sales|how many months/.test(q))
    return f.dateSummary
      ? `${f.dateSummary.monthsCovered} month(s) of sales history are available in the current selection.`
      : "Map a date column to count months of sales history.";
  if (/average revenue per business day|average.*business day/.test(q))
    return f.dateSummary
      ? `Average revenue per recorded business day is ${money(f.dateSummary.averageBusinessDayRevenue)}. This uses days present in the file, not closed or missing days.`
      : "Map a date column to calculate revenue per business day.";
  if (/consistent|consistency|vary|variation|stable.*daily|daily sales.*stable/.test(q))
    return f.dateSummary?.dailySalesStdDev != null
      ? `Daily sales vary by about ${money(f.dateSummary.dailySalesStdDev)} around the average, a variation of ${pct(f.dateSummary.dailySalesVariationPercent)}. Lower variation means sales are more consistent.`
      : "Daily-sales consistency needs at least two recorded dates.";
  if (/same weekdays last week|this week.*last week/.test(q))
    return "The dashboard does not yet calculate same-weekday week-over-week comparisons. It can compare current selected dates by weekday, but a precise same-weekday comparison needs a dedicated weekly comparison view.";
  if (/same point last month|so far this month|month.*same point/.test(q))
    return "The dashboard does not yet calculate month-to-date versus the same point last month. It can show monthly totals, but this question needs a month-to-date comparison calculation.";
  if (/beginning and end of the month|beginning.*end.*month|payday/.test(q))
    return f.dateSummary
      ? `Recorded revenue from days 1-10 is ${money(f.dateSummary.beginningMonthRevenue)}. Recorded revenue from days 21-end is ${money(f.dateSummary.endMonthRevenue)}. Payday effects need actual payday dates to confirm.`
      : "Map a date column to compare beginning and end of month sales.";
  if (/seasonal|seasonality|holiday/.test(q))
    return f.dateSummary?.monthsCovered > 2
      ? `There are ${f.dateSummary.monthsCovered} recorded months. That can hint at seasonality, but reliable seasonal or holiday analysis needs holiday flags and more history across comparable seasons.`
      : "There is not enough dated history to judge seasonal or holiday patterns reliably.";
  if (/revenue.*operating hour|per operating hour/.test(q))
    return f.hourSummary?.revenuePerRecordedOperatingHour != null
      ? `Revenue per recorded sales hour is ${money(f.hourSummary.revenuePerRecordedOperatingHour)}. This uses hours that appear in the data, not scheduled open hours.`
      : "Revenue per operating hour needs date and hour/time columns.";
  if (/units.*operating hour/.test(q))
    return f.hourSummary?.unitsPerRecordedOperatingHour != null
      ? `Units sold per recorded sales hour are about ${f.hourSummary.unitsPerRecordedOperatingHour}. This uses hours that appear in the data, not scheduled open hours.`
      : "Units per operating hour needs quantity plus date and hour/time columns.";
  if (/first sale|last sale/.test(q))
    return f.hourSummary
      ? `The typical first recorded sale hour is about ${f.hourSummary.typicalFirstSaleHour}:00, and the typical last recorded sale hour is about ${f.hourSummary.typicalLastSaleHour}:00. Scheduled opening and closing times are not mapped.`
      : "First/last sale timing needs date and hour/time columns.";
  if (/final hour|last hour/.test(q))
    return f.hourSummary?.lastRecordedHourRevenue != null
      ? `The final recorded sales hour of each day contributes ${money(f.hourSummary.lastRecordedHourRevenue)} in selected revenue. Closing-time analysis needs scheduled closing hours.`
      : "Final-hour revenue needs date and hour/time columns.";
  if (/30-minute|30 minute|time between orders|outside business hours|opening time|closing/.test(q))
    return missingDataAnswer(
      "Detailed time-interval and business-hours analysis",
      "full timestamps, scheduled opening/closing hours, and ideally one row per transaction line with reliable order times",
    );
  // Describe uploaded weather associations without claiming that weather caused sales changes.
  if (/weather|rainy|sunny/.test(q))
    return f.weather[0]
      ? `Weather comparison by average recorded daily sales: ${f.weather
          .slice(0, 3)
          .map((item) => `${item.name} ${money(item.averageDailyNetSales)} per recorded day`)
          .join("; ")}. Compare similar weekdays before treating this as a weather effect.`
      : "Weather analysis needs mapped date and weather columns.";
  if (/weekend|weekday/.test(q) && f.weekdays.length) {
    // Weekend/weekday comparison sums the weekday groups.
    const weekend = f.weekdays.filter(
      (d) => d.weekday === "Saturday" || d.weekday === "Sunday",
    );
    const weekdays = f.weekdays.filter(
      (d) => d.weekday !== "Saturday" && d.weekday !== "Sunday",
    );
    return `Weekend revenue was ${money(sum(weekend, "netSales"))}; weekday revenue was ${money(sum(weekdays, "netSales"))}.`;
  }
  if (/week generated|which week/.test(q) && f.topWeeks[0])
    return `The highest-revenue week started ${f.topWeeks[0].week}, with ${money(f.topWeeks[0].netSales)}.`;
  if (/month generated|which month/.test(q) && f.topMonths[0])
    return `The highest-revenue month was ${f.topMonths[0].month}, with ${money(f.topMonths[0].netSales)}.`;
  if (/weekday|day of week/.test(q) && f.weekdays.length) {
    if (/lowest|fewest/.test(q))
      return `${[...f.weekdays].reverse()[0].weekday} has the lowest recorded sales at ${money([...f.weekdays].reverse()[0].netSales)}.`;
    return `${f.weekdays[0].weekday} has the highest recorded sales at ${money(f.weekdays[0].netSales)}.`;
  }
  if (/morning|afternoon|evening|time of day/.test(q) && f.periods.length)
    return `Sales by time of day: ${f.periods.map((p) => `${p.name} ${money(p.netSales)}`).join("; ")}.`;
  if (/hour|time/.test(q) && f.topHours.length) {
    if (/fewest|lowest/.test(q) && /unit/.test(q) && f.bottomHoursByUnits[0])
      return `${f.bottomHoursByUnits[0].hour}:00 sold the fewest units: ${f.bottomHoursByUnits[0].units}.`;
    if (/average order/.test(q) && f.topHoursByAov[0])
      return `${f.topHoursByAov[0].hour}:00 had the highest average order value at ${money(f.topHoursByAov[0].averageOrderValue)}.`;
    return `${f.topHours[0].hour}:00 generates the most revenue at ${money(f.topHours[0].netSales)}.`;
  }
  if (/zero quantity|quantity.*zero/.test(q))
    return f.dataQuality.zeroQuantityLines === null
      ? "Quantity is not mapped, so zero-quantity sales lines cannot be counted."
      : `${f.dataQuality.zeroQuantityLines.toLocaleString()} selected sales lines have zero quantity.`;
  if (/unusually large|unusually small|outlier|transaction amounts/.test(q))
    return f.dataQuality.unusuallyLargeLines.length
      ? `Largest selected line amounts are ${f.dataQuality.unusuallyLargeLines
          .map((value) => money(value))
          .join("; ")}. Very small, zero, or negative amounts should be reviewed as discounts, returns, tests, or data-entry issues.`
      : "There are no positive sales-line amounts to review for unusually large values.";
  if (/active filters|filters.*affecting/.test(q)) {
    const entries = Object.entries(f.dataQuality.activeFilters);
    return entries.length
      ? `Active filters: ${entries.map(([key, value]) => `${key}=${value}`).join(", ")}.`
      : "No dashboard filters are currently active.";
  }
  if (/supplied directly|calculated|displayed metrics/.test(q))
    return `Available source-backed metrics include ${f.dataQuality.suppliedMetrics.join(", ") || "net sales only"}. Calculated metrics include ${f.dataQuality.calculatedMetrics.join(", ")}.`;
  if (/multiple currencies|currency/.test(q))
    return "The dashboard uses the single currency code chosen during setup. It does not detect or convert multiple currencies inside the uploaded file.";
  if (/quantity.*items sold|items remaining|quantity units|kilograms|pieces/.test(q))
    return "The dashboard treats the mapped quantity column as units sold. It cannot verify mixed units or whether the source column means stock remaining unless your file includes separate unit-of-measure and inventory fields.";
  if (/same product.*different categories|product assigned.*categories/.test(q))
    return "The dashboard can show product and category totals, but it does not yet flag products assigned to multiple categories. Review the product table or source file if category consistency matters.";
  if (/canceled|cancelled|return.*original|test transactions|placeholder|last updated|settlement|reconcile/.test(q))
    return missingDataAnswer(
      "Cancellation, return-linking, test-transaction, dataset-update, and settlement reconciliation checks",
      "order status, original-sale IDs for returns, test flags, source export timestamp, and point-of-sale settlement totals",
    );
  if (/filtered totals.*full dataset|reconcile.*full/.test(q))
    return `The current filter selects ${f.selectedRows.toLocaleString()} of ${f.sourceRows.toLocaleString()} source rows and totals ${money(f.netSales)} in net sales. Reset filters to compare against the full dataset.`;
  if (/assumptions|verify before acting|before acting/.test(q))
    return `Before acting, verify: the file covers the full period, returns and discounts are recorded correctly, order IDs group receipts correctly, product costs are current, operating expenses are considered, and stock/customer data supports any inventory or retention decision.`;
  if (/when|day|sales|revenue/.test(q))
    return `Selected net sales total ${money(f.netSales)}.${topDay ? " The highest recorded day is " + topDay.date + " at " + money(topDay.netSales) + "." : ""}${lowDay ? " The lowest recorded day is " + lowDay.date + " at " + money(lowDay.netSales) + "." : ""}${f.topHours[0] ? " The highest recorded hour is " + f.topHours[0].hour + ":00 at " + money(f.topHours[0].netSales) + " across selected days." : ""} These totals reflect recorded coverage, not sales per open hour.`;
  if (/next|recommend|investigate|should/.test(q))
    return `Next step: protect what is working and investigate the weak spots. Check ${topProduct.name}'s margin and stock because it leads revenue, then review ${leastRevenueProduct ? leastRevenueProduct.name : "the lowest-selling item"} for stockouts, pricing, menu placement, or low demand. If profit data is available, prioritize high-revenue low-margin items before changing promotions.`;
  if (/three|3/.test(q) && /important|findings|act/.test(q))
    return `Three priorities: 1. Protect ${topProduct.name}, the top revenue product at ${money(topProduct.netSales)}. 2. Investigate ${leastRevenueProduct ? leastRevenueProduct.name : "the lowest-selling product"} for demand, pricing, or stock issues. 3. Compare gross margin and operating costs before making promotion or staffing decisions.`;
  if (/opportunit|improve/.test(q))
    return `Opportunities: protect top sellers, investigate low-selling products, review discounts against margins, and focus on products or categories with strong margin and enough demand.`;
  if (/average|daily|per day/.test(q))
    return f.averageDailyNetSales === null
      ? "Map a date column to calculate average daily sales."
      : `Average recorded daily net sales are ${money(f.averageDailyNetSales)} across ${f.daysCovered} recorded days. This is based only on days present in the file, not missing or closed days.`;
  return `I can answer from the mapped dashboard data. Selected net sales are ${money(f.netSales)}${f.grossMarginPercent !== null ? ", gross margin is " + pct(f.grossMarginPercent) : ""}, ${topProduct ? topProduct.name + " is the top product" : "product ranking is unavailable"}${leastRevenueProduct ? ", and " + leastRevenueProduct.name + " is lowest by revenue" : ""}. Try asking about least sold, business health, next steps, profit, categories, timing, or average daily sales.`;
}
// Render backend calculation tables and optional query text; escape all dataset values.
function renderAnalystEvidence(response) {
  const container = $("analystEvidence");
  const evidence = response.evidence || [];
  container.hidden = !evidence.length;
  container.innerHTML = evidence.length ? `<details><summary>Supporting calculations · ${response.selectedRows.toLocaleString()} selected rows</summary>${evidence.map((item, i) =>
    `<section><strong>Calculation ${i + 1}</strong><div class="scroll"><table><thead><tr>${item.columns.map(column => `<th>${esc(column)}</th>`).join("")}</tr></thead><tbody>${item.rows.map(row => `<tr>${row.map(value => `<td>${esc(value === null ? "Not available" : value)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${item.truncated ? '<p>Showing the first 30 result rows; this is not the complete result.</p>' : ''}${!item.rows.length ? '<p>No rows matched this calculation.</p>' : ''}<details><summary>View calculation query</summary><pre>${esc(item.query)}</pre></details></section>`).join("")}</details>` : '';
}
// Forget the browser conversation token/transcript and clear evidence for the old selection.
function resetConversation() {
  conversationId = null;
  conversationTurns = [];
  $("insightAnswer").textContent = "";
  $("analystEvidence").hidden = true;
  $("analystEvidence").replaceChildren();
}
// Display recent exchanges as plain text and scroll to the latest response.
function showConversation(pending = "") {
  const panel = $("insightAnswer");
  panel.textContent = [...conversationTurns, pending].filter(Boolean).join("\n\n");
  panel.scrollTop = panel.scrollHeight;
}
async function ask(question) {
  // Ask either the deterministic answer engine or optional local Ollama.
  if (busy) return;
  busy = true;
  $("askButton").disabled = true;
  // Remember the selection revision so a slow response cannot overwrite a newer dashboard.
  const current = revision,
    model = $("localModel").value;
  $("analystEvidence").hidden = true;
  $("analystEvidence").replaceChildren();
  showConversation("You: " + question + "\n" + (model ? "Your local model is inspecting the data and running calculations…" : "Calculating…"));
  try {
    let answer;
    if (model) {
      if (!meta.datasetId) throw Error(meta.analystNote || "Build the dashboard again to load the dataset for local AI analysis.");
      // Send only the dataset reference, conversation token, question, and current filters; rows are cached on the server.
      const response = await api("/api/analyst", {
        model, question, datasetId: meta.datasetId, conversationId,
        filters: Object.fromEntries(["from", "to", "category", "product", "weekday", "period"].map(id => [id, $(id).value])),
      });
      if (revision === current) {
        // If backend memory expired or scope changed, discard the old visible transcript too.
        if (conversationId && conversationId !== response.conversationId) conversationTurns = [];
        conversationId = response.conversationId;
        renderAnalystEvidence(response);
      }
      answer =
        "Local data analyst · " +
        response.model +
        "\n" +
        response.answer +
        (response.evidence?.length ? "\nCheck the supporting calculations below: AI interpretation can still make mistakes." : "");
    } else answer = "Calculated answer\n" + calculatedAnswer(question);
    if (revision === current) {
      // Keep the visible transcript aligned with the backend limit of four recent exchanges.
      conversationTurns.push("You: " + question + "\n" + answer);
      conversationTurns = conversationTurns.slice(-4);
      showConversation();
    }
  } catch (e) {
    if (revision === current)
      showConversation(e.message + " Choose Calculated answers to continue without a model.");
  } finally {
    busy = false;
    $("askButton").disabled = false;
  }
}
async function refreshModels() {
  // Check whether Ollama is running and list downloaded local models.
  $("refreshModels").disabled = true;
  try {
    const result = await (await fetch("/api/models")).json(),
      current = $("localModel").value,
      recommended =
        result.models.find((model) => model === preferredLocalModel) ||
        result.models.find(
          (model) => model === "llama3.2" || model === "llama3.2:latest",
        ) ||
        result.models.find((model) => model.startsWith("llama3.2:")) ||
        "";
    sourceOptions($("localModel"), result.models, current || recommended);
    $("localModel").firstChild.textContent = "Calculated answers";
    $("insightMode").textContent = result.models.length
      ? recommended
        ? `Calculated insights · ${recommended} data analyst ready`
        : "Calculated insights · local AI available"
      : "Calculated insights · install Ollama for optional local AI";
  } finally {
    $("refreshModels").disabled = false;
  }
}
// Connect page buttons, dropdowns, and question chips to the functions above.
$("inspectButton").onclick = inspect;
$("buildButton").onclick = build;
$("sheet").onchange = () => {
  uploadPayload.sheet = $("sheet").value;
  inspect();
};
$("upload").onchange = () => {
  // Switching upload/sample clears the previous mapping preview.
  $("sample").value = "";
  $("sampleDescription").hidden = true;
  profile = null;
  uploadPayload = {};
  $("mappingPanel").hidden = true;
  $("sheet").replaceChildren();
};
$("sample").onchange = () => {
  // Samples also preselect the closest business type for better wording.
  profile = null;
  uploadPayload = {};
  $("upload").value = "";
  $("sheet").replaceChildren();
  $("mappingPanel").hidden = true;
  const sample = SAMPLE_DATASETS.find(item => item.filename === $("sample").value);
  if (sample) $("business").value = sample.business;
  $("sampleDescription").hidden = !sample;
  $("sampleDescription").textContent = sample
    ? (sample.legacy ? "Earlier sample. " : "Fictional demo · ") + (sample.description || sample.label) + " Click Inspect columns, then Build dashboard."
    : "";
  applyBusinessTheme($("business").value);
};
$("business").onchange = () => applyBusinessTheme($("business").value);
$("overviewNav").onclick = () => showPage("overview");
$("detailNav").onclick = () => showPage("detail");
$("setupNav").onclick = showSetup;
$("cancelSetup").onclick = () => showPage("overview");
["from", "to", "category", "product", "weekday", "period"].forEach((id) =>
  $(id).addEventListener("change", render),
);
$("reset").onclick = resetFilters;
$("chooseCharts").onclick = () => showChartChooser(false);
$("selectRecommendedCharts").onclick = selectRecommendedCharts;
$("loadSelectedCharts").onclick = loadSelectedCharts;
$("refreshModels").onclick = refreshModels;
// Starting over or switching model invalidates outstanding answers and clears local chat context.
$("newConversation").onclick = () => { revision++; resetConversation(); };
$("localModel").onchange = () => { revision++; resetConversation(); };
$("insightForm").onsubmit = (e) => {
  // Keep the form on the same page and answer the typed question.
  e.preventDefault();
  ask($("insightQuestion").value);
};
document.querySelectorAll("[data-question]").forEach(
  (b) =>
    (b.onclick = () => {
      // Clicking a suggested question copies it into the input and answers it.
      $("insightQuestion").value = b.dataset.question;
      ask(b.dataset.question);
    }),
);
showSetup();
applyBusinessTheme($("business").value);
refreshModels().catch(() => {});
}
