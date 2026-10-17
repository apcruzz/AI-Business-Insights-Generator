// Page structure and stable element IDs; dashboard.js fills these containers and handles events.
import { useEffect } from "react";
import { initDashboard } from "./dashboard.js";
import "./styles.css";
// Load setup.css after the base stylesheet so its layout overrides win.
import "./setup.css";

export default function App() {
  // Run the DOM controller after React has mounted the elements it needs.
  useEffect(() => {
    initDashboard();
  }, []);

  return (
    <>
      {/* Navigation and dataset labels are updated by showPage() and build(). */}
      <header>
        <div>
          <small>
            <span id="businessName">BUSINESS INSIGHTS</span>
          </small>
          <h1>Sales overview</h1>
        </div>
        <small>
          <span id="datasetName">Choose your business and dataset</span>
        </small>
        <nav className="topnav" aria-label="Dashboard pages">
          <button id="overviewNav" type="button" aria-current="page">
            Business Overview
          </button>
          <button id="detailNav" type="button">
            Detailed Dashboard
          </button>
          <button id="setupNav" type="button">
            Change dataset
          </button>
        </nav>
      </header>

      {/* Upload setup: inspect sends the chosen file or sample to /api/profile. */}
      <section className="setup" id="setupPage">
        <h2>Build your business dashboard</h2>
        <p>
          Choose your business, upload a data table, and confirm the columns.
          Files are processed on this computer.
        </p>
        <div className="setupGrid">
          <label>
            What business do you run?
            <select id="business" defaultValue="Restaurant">
              <option value="Restaurant">Restaurant</option>
              <option value="Furniture shop">Furniture shop</option>
              <option value="Retail store">Retail store</option>
              <option value="Cafe">Cafe</option>
              <option value="Other business">Other business</option>
            </select>
          </label>
          <label>
            Upload CSV or Excel
            <input id="upload" type="file" accept=".csv,.xlsx,.xls" />
          </label>
          <label>
            Or try a sample
            <select id="sample" defaultValue="">
              <option value="">Choose a sample</option>
              <option value="Restaurant_Synthetic.csv">
                Restaurant (fictional)
              </option>
              <option value="Furniture_Shop_Synthetic.csv">
                Furniture shop (fictional)
              </option>
              <option value="Retail_Store_Synthetic.csv">
                Retail store (fictional)
              </option>
              <option value="Cafe.csv">Original cafe dataset</option>
            </select>
          </label>
        </div>
        <div className="setupActions">
          <button className="primary" id="inspectButton" type="button">
            Inspect columns
          </button>
          <span id="setupStatus" aria-live="polite"></span>
        </div>

        {/* After inspection, display worksheet options and suggested source-to-dashboard column mappings. */}
        <div id="mappingPanel" hidden>
          <hr />
          <h2>Confirm your columns</h2>
          <div className="mapInfo">
            Each row should represent a sales line or one order. Map amounts at
            that same level. Leave unavailable fields blank; profit and other
            unsupported metrics will stay unavailable.
          </div>
          <div className="setupGrid">
            <label>
              Worksheet
              <select id="sheet"></select>
            </label>
            <label>
              Currency code
              <input id="currency" defaultValue="USD" maxLength="3" />
            </label>
            <label>
              Date order
              <select id="dateOrder" defaultValue="month">
                <option value="month">Month first (MM/DD/YYYY)</option>
                <option value="day">Day first (DD/MM/YYYY)</option>
              </select>
            </label>
            <label>
              Decimal separator
              <select id="decimal" defaultValue="dot">
                <option value="dot">Dot (1,234.56)</option>
                <option value="comma">Comma (1.234,56)</option>
              </select>
            </label>
          </div>
          {/* dashboard.js creates one mapping dropdown per canonical field in this container. */}
          <div
            id="mappingGrid"
            className="mappingGrid"
            style={{ marginTop: 20 }}
          ></div>
          {/* Amount semantics prevent add-ons or discounts from being counted twice. */}
          <div id="lineTotalOptions" hidden>
            <label>Does the line total include discounts?
              <select id="lineTotalBasis" defaultValue="">
                <option value="">Choose how this total was calculated</option>
                <option value="gross">Before discounts — subtract discounts separately</option>
                <option value="net">After discounts — use as net sales</option>
              </select>
            </label>
            <p>Use a total that includes add-ons but excludes tax and tips. Do not map an order total repeated on every item row.</p>
          </div>
          <div id="modifierOptions" hidden>
            <label>Modifier charge applies to
              <select id="modifierBasis" defaultValue="line">
                <option value="line">The whole sales line</option>
                <option value="unit">Each unit — multiply by quantity</option>
              </select>
            </label>
            <p>Map a numeric charge, not an ingredient name. Blank charges count as zero. When a sales total is mapped, it takes priority and modifiers are not added again.</p>
          </div>
          {/* Show source rows for checking the mapping before normalization. */}
          <details style={{ marginTop: 18 }}>
            <summary>Preview source rows</summary>
            <div id="preview"></div>
          </details>
          <div className="setupActions">
            <button className="primary" id="buildButton" type="button">
              Build dashboard
            </button>
            <button id="cancelSetup" type="button" hidden>
              Return to dashboard
            </button>
          </div>
        </div>
        <div id="setupError" className="error" role="alert"></div>
      </section>

      {/* Chart selection dialog: only charts supported by validated columns are offered. */}
      <section
        className="chartChooser"
        id="chartChooser"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chartChooserTitle"
        hidden
      >
        <div className="chartChooserPanel">
          <div>
            <h2 id="chartChooserTitle">Choose overview charts</h2>
            <p id="chartChooserSummary" className="sub">
              Pick up to 3 charts for Business Overview
            </p>
          </div>
          <div id="chartChoices" className="chartChoices"></div>
          <div className="chartChooserActions">
            <button id="selectRecommendedCharts" type="button">
              Recommended 3
            </button>
            <button className="primary" id="loadSelectedCharts" type="button">
              Load dashboard
            </button>
          </div>
        </div>
      </section>

      {/* Dashboard content stays hidden until an upload is normalized successfully. */}
      <main id="dashboardMain" hidden>
        <div id="overview">
          <div id="overviewCards" className="cards"></div>
          {/* Three empty slots are filled with the charts selected in the chooser. */}
          <div className="overviewGrid">
            <section className="panel overviewChartSlot" id="overviewSlot0"></section>
            <section className="panel overviewChartSlot" id="overviewSlot1"></section>
            <section className="panel overviewChartSlot" id="overviewSlot2"></section>
          </div>

          {/* Insights combine computed summary cards with calculated answers or local Ollama chat. */}
          <div className="overviewBottom">
            <section className="panel insightsPanel">
              <div className="insightHeader">
                <div>
                  <h2>Business insights</h2>
                  <p className="sub">
                    <span id="insightMode">
                      Calculated insights · local AI optional
                    </span>
                  </p>
                </div>
                {/* Downloaded Ollama models populate this selector; blank selects calculated answers. */}
                <div className="modelRow">
                  <label htmlFor="localModel">Answer mode</label>
                  <select id="localModel" defaultValue="">
                    <option value="">Calculated answers</option>
                  </select>
                  <button id="refreshModels" type="button">
                    Check local AI
                  </button>
                </div>
              </div>
              <div className="insightBody">
                <div className="insightAsk">
                  {/* Submitting a question calls ask(); suggestion buttons reuse the same path. */}
                  <form id="insightForm">
                    <label htmlFor="insightQuestion">
                      Ask a question about this dashboard
                    </label>
                    <div className="askRow">
                      <input
                        id="insightQuestion"
                        placeholder="Example: Which product should we investigate?"
                        required
                      />
                      <button id="askButton" type="submit">
                        Ask
                      </button>
                    </div>
                    <div className="suggestions">
                      <button
                        type="button"
                        data-question="Which product leads sales?"
                      >
                        Top product
                      </button>
                      <button
                        type="button"
                        data-question="Which product sold the least?"
                      >
                        Least sold
                      </button>
                      <button
                        type="button"
                        data-question="Is the business successful?"
                      >
                        Business health
                      </button>
                      <button type="button" data-question="What should we do next?">
                        Next step
                      </button>
                    </div>
                  </form>
                  {/* Chat transcript and supporting SQL results are filled safely by the controller. */}
                  <button type="button" id="newConversation">New conversation</button>
                  <small>Follow up on your last answer. Changing data or filters starts a new conversation.</small>
                  <p id="insightAnswer" aria-live="polite"></p>
                  <div id="analystEvidence" hidden></div>
                </div>
                <div id="insightCards" className="insightCards"></div>
              </div>
            </section>
          </div>
        </div>

        {/* These controls filter both browser calculations and backend analyst queries. */}
        <div className="filters">
          <strong style={{ fontSize: 14 }}>Filters</strong>
          <label>
            From
            <input id="from" type="date" />
          </label>
          <label>
            Through
            <input id="to" type="date" />
          </label>
          <label>
            Category
            <select id="category" defaultValue="">
              <option value="">All categories</option>
            </select>
          </label>
          <label>
            Product
            <select id="product" defaultValue="">
              <option value="">All products</option>
            </select>
          </label>
          <label>
            Day of week
            <select id="weekday" defaultValue="">
              <option value="">All days</option>
              <option value="1">Monday</option>
              <option value="2">Tuesday</option>
              <option value="3">Wednesday</option>
              <option value="4">Thursday</option>
              <option value="5">Friday</option>
              <option value="6">Saturday</option>
              <option value="0">Sunday</option>
            </select>
          </label>
          <label>
            Time of day
            <select id="period" defaultValue="">
              <option value="">All hours</option>
              <option value="overnight">Overnight · 12-5 am</option>
              <option value="morning">Morning · 6-11 am</option>
              <option value="afternoon">Afternoon · 12-5 pm</option>
              <option value="evening">Evening · 6-11 pm</option>
            </select>
          </label>
          <button id="reset" type="button">
            Reset filters
          </button>
          <button id="chooseCharts" type="button">
            Choose charts
          </button>
          <span className="hint" id="count" aria-live="polite"></span>
          <details>
            <summary>Data notes</summary>
            <div id="sidebarNotes"></div>
          </details>
        </div>

        {/* Detailed panels show supported charts not selected for the overview. */}
        <div id="detailPage" hidden>
          <section className="panel" data-chart-panel="weekday">
            <h2>Sales by day of week</h2>
            <div id="ovDays"></div>
          </section>
          <div className="cards" id="cards"></div>
          <div className="grid" data-chart-group>
            <section className="panel" data-chart-panel="trend">
              <h2>Daily performance</h2>
              <p className="sub">
                Revenue and gross profit across the selected period
              </p>
              <div className="legend">
                <span></span>Net sales<span className="profit"></span>Gross
                profit
              </div>
              <div className="chart" id="daily"></div>
            </section>
            <section className="panel" data-chart-panel="category">
              <h2>Sales by category</h2>
              <p className="sub">Share of selected net sales</p>
              <div id="categories"></div>
            </section>
          </div>

          <div className="grid" data-chart-group>
            {/* Product rows display revenue, quantity, and optional profit metrics. */}
            <section className="panel" data-chart-panel="products">
              <h2>Product performance</h2>
              <p className="sub">
                Ranked by net sales · margin uses net sales after discounts
              </p>
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th className="num">Units</th>
                      <th className="num">Net sales</th>
                      <th className="num">Gross profit</th>
                      <th className="num">Margin</th>
                    </tr>
                  </thead>
                  <tbody id="products"></tbody>
                </table>
              </div>
            </section>
            <section className="panel" data-chart-panel="hour">
              <h2>Sales by hour</h2>
              <p className="sub">
                Net sales by hour, split by product · hover or tap a segment for
                details
              </p>
              <div className="chart" id="hours"></div>
              <p className="hint" id="peak"></p>
            </section>
          </div>

          <div className="grid" data-chart-group>
            <section className="panel" data-chart-panel="profitability">
              <h2>Product profitability leaderboard</h2>
              <p className="sub">Products ranked by gross margin, after discounts</p>
              <div id="profitability"></div>
            </section>
            {/* Weather comparisons use uploaded values only, with coverage limitations explained below. */}
            <section className="panel" data-chart-panel="weather">
              <h2>Weather versus sales</h2>
              <p className="sub">
                Net sales by weather condition and product category
              </p>
              <div id="weather"></div>
              <p className="hint">
                Sales per recorded day helps account for unequal day counts.
                Partial days and other factors can affect this comparison; it
                does not establish a weather effect.
              </p>
            </section>
          </div>

          {/* Employee totals summarize handled sales rather than measuring staff productivity. */}
          <section
            className="panel"
            data-chart-panel="staff"
            style={{ marginTop: 20 }}
          >
            <h2>Staff sales comparison</h2>
            <p className="sub">
              Sales handled by each employee in the current selection
            </p>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th className="num">Gross sales</th>
                    <th className="num">Discounts</th>
                    <th className="num">Net sales</th>
                    <th className="num">Gross profit</th>
                    <th className="num">Margin</th>
                  </tr>
                </thead>
                <tbody id="staff"></tbody>
              </table>
            </div>
            <p className="hint">
              Shift hours and customer assignments are unavailable, so these
              totals should not be treated as employee productivity ratings.
            </p>
          </section>
        </div>

        {/* Display validation warnings and coverage limitations supplied by the backend. */}
        <div className="note" id="dataNotes"></div>
        <footer>
          Local data processing. Gross profit excludes operating expenses.
        </footer>
      </main>
    </>
  );
}
