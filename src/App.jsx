// Page structure and stable element IDs; dashboard.js fills these containers and handles events.
import { SAMPLE_DATASETS } from "./sample-datasets.js";
import { BUSINESSES } from "./business-config.js";
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
          <h1 id="dashboardTitle">Your business at a glance</h1>
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
          Uploads and AI conversations are temporary and may expire or be cleared
          when the server restarts. Keep your original file so you can rebuild the dashboard.
        </p>
        <p id="uploadLimitNote" hidden>Demo uploads: up to 2 MB, 10,000 rows, and 60 columns. Use fictional or nonconfidential data.</p>
        <p id="businessHint" className="businessHint"></p>
        <div className="setupGrid">
          <label>
            What business do you run?
            <select id="business" defaultValue="Restaurant">
              {Object.entries(BUSINESSES).map(([value, business]) => (
                <option key={value} value={value}>{business.label}</option>
              ))}
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
              <optgroup label="Business demos · fictional data">
                {SAMPLE_DATASETS.filter(sample => !sample.legacy).map(sample => (
                  <option key={sample.filename} value={sample.filename}>{sample.label}</option>
                ))}
              </optgroup>
              <optgroup label="Earlier samples">
                {SAMPLE_DATASETS.filter(sample => sample.legacy).map(sample => (
                  <option key={sample.filename} value={sample.filename}>{sample.label}</option>
                ))}
              </optgroup>
            </select>
          </label>
        </div>
        <p id="sampleDescription" className="sampleDescription" aria-live="polite" hidden></p>
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
              Confirm columns
            </button>
            <button id="cancelSetup" type="button" hidden>
              Return to dashboard
            </button>
          </div>
          <section id="kpiPanel" className="kpiPanel" hidden>
            <hr />
            <h2>Customize your Business Overview</h2>
            <p>
              Choose the KPI cards and overview charts you want to see. Choices
              depend on your confirmed columns. Leave everything unchecked for
              the default Business Overview. The Detailed Dashboard always
              includes all of its sections.
            </p>
            <h3>KPI cards</h3>
            <div id="kpiOptions" className="kpiOptions"></div>
            <div className="setupActions">
              <button className="primary" id="dashboardButton" type="button">
                Build dashboard
              </button>
              <span id="kpiStatus" aria-live="polite"></span>
            </div>
          </section>
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
          <details className="recommendationExplanation"><summary>Why these charts?</summary><div id="chartRecommendationNotes"></div></details>
          <div id="chartChoices" className="chartChoices"></div>
          <div className="chartChooserActions">
            <button id="selectRecommendedCharts" type="button">
              Use recommendations
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
            <section className="panel overviewChartSlot" data-dashboard-module="salesTrend" id="overviewSlot0">
              <h2>Net sales trend</h2>
              <div id="ovTrend"></div>
            </section>
            <section className="panel overviewChartSlot" data-dashboard-module="categoryChart" id="overviewSlot1">
              <h2>Sales by category</h2>
              <div id="ovCategory"></div>
            </section>
            <section className="panel overviewChartSlot" data-dashboard-module="topProductsChart" id="overviewSlot2">
              <h2>Top 5 products by net sales</h2>
              <div id="ovTop"></div>
            </section>
          </div>

          {/* Insights combine computed cards with calculated answers, Ollama, or Groq chat. */}
          <div className="overviewBottom">
            <section className="panel insightsPanel">
              <div className="insightHeader">
                <div>
                  <h2>Business insights</h2>
                  <p className="sub">
                    <span id="insightMode">
                      Calculated insights · AI optional
                    </span>
                  </p>
                </div>
                {/* Backend discovery lists local and cloud models; blank selects calculated answers. */}
                <div className="modelRow">
                  <label htmlFor="localModel">Answer mode</label>
                  <select id="localModel" defaultValue="" aria-describedby="aiDataNotice">
                    <option value="">Calculated answers</option>
                  </select>
                  <button id="refreshModels" type="button">
                    Refresh AI options
                  </button>
                </div>
              </div>
              <p id="aiDataNotice" className="sub aiDataNotice" aria-live="polite">
                Choose an answer mode to see how your data is used.
              </p>
              <div className="browserOllamaPanel">
                <div className="browserOllamaActions">
                  <button id="connectBrowserOllama" type="button">Connect Local Ollama</button>
                  <button id="disconnectBrowserOllama" type="button" disabled>Disconnect</button>
                </div>
                <p id="browserOllamaStatus" role="status">Not connected. Connect only if you want AI inference on this computer.</p>
                <details className="ollamaSetup">
                  <summary>Local Ollama setup and troubleshooting</summary>
                  <p>Install <a href="https://ollama.com/download" target="_blank" rel="noreferrer">Ollama for Windows or macOS</a> and download a model:</p>
                  <pre>ollama pull llama3.2:3b</pre>
                  <p>Quit the running Ollama app first. Keep the server on 127.0.0.1:11434 and allow only this trusted website origin: <code data-ollama-origin></code>.</p>
                  <p>macOS Terminal (keep it open while using the dashboard):</p>
                  <pre>OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_ORIGINS=<span data-ollama-origin></span> ollama serve</pre>
                  <p>Windows PowerShell (keep it open while using the dashboard):</p>
                  <pre>{'$env:OLLAMA_HOST="127.0.0.1:11434"\n$env:OLLAMA_NO_CLOUD="1"\n$env:OLLAMA_ORIGINS="'}<span data-ollama-origin></span>{'"\nollama serve'}</pre>
                  <p>Click Connect, allow Chrome’s Local Network Access prompt, then select a model in Answer mode. If no models appear, download a local model and Reconnect. Cloud-linked models are excluded.</p>
                  <p>If access fails: check Ollama is running, quit an older instance before changing its settings, check the exact origin, and allow local-network access in Chrome’s site settings. A timeout can mean your model is still loading; wait or try a smaller model. Other browsers and managed devices may block HTTPS-to-loopback access.</p>
                  <p>AI inference runs on your computer. Uploads, SQL calculations, evidence verification and conversation storage still run on the dashboard server. Keep Ollama on loopback; no public tunnel, wildcard origin or extra desktop app is required. Disconnect stops this page’s requests; it does not stop Ollama or revoke the site’s permission.</p>
                </details>
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
            <span id="productFilterLabel">Product</span>
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

        {/* Detailed Dashboard includes every chart supported by the mapped data. */}
        {/* The overview selection only controls its three featured chart slots. */}
        <div id="detailPage" hidden>
          <div className="cards" id="cards"></div>
          <div id="detailCharts" className="businessDetailGrid"></div>
          <div id="detailTables" className="businessDetailGrid"></div>
        </div>

        <div className="note" id="dataNotes"></div>
        <footer>
          Local data processing. Gross profit excludes operating expenses.
        </footer>
      </main>
    </>
  );
}
