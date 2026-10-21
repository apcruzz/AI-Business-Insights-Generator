// Page structure and stable element IDs; dashboard.js fills these containers and handles events.
import { SAMPLE_DATASETS } from "./sample-datasets.js";
import { BUSINESSES } from "./business-config.js";
import { useEffect } from "react";
import { initDashboard } from "./dashboard.js";
import { AccountAccess } from "./AccountAccess.jsx";
import { OverviewPreview } from "./OverviewPreview.jsx";
import "./styles.css";
// Load setup.css after the base stylesheet so its layout overrides win.
import "./setup.css";
import "./overview-preview.css";

export default function App() {
  return <AccountAccess>{({openAccount}) => <Dashboard openAccount={openAccount} />}</AccountAccess>;
}

function Dashboard({openAccount}) {
  // Run the DOM controller after React has mounted the elements it needs.
  useEffect(() => {
    return initDashboard();
  }, []);

  return (
    <>
      {/* Navigation and dataset labels are updated by showPage() and build(). */}
      <OverviewPreview openAccount={openAccount} />
      <header className="dashboardHeader">
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
          <button id="previewNav" type="button">
            Overview preview
          </button>
          <button id="setupNav" type="button">
            Change dataset
          </button>
          {openAccount && <button id="accountButton" type="button" onClick={openAccount} aria-haspopup="dialog">Account</button>}
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
          {/* The controls stay together; either expanded panel spans the full form. */}
          <div className="mappingTools">
            <button id="toggleOptionalColumns" className="mappingTool optionalColumnsButton" type="button" aria-expanded="false" aria-controls="operationalMapping">
              <span>Optional delivery, booking, waste, channel and job columns</span>
              <span className="disclosureIcon" aria-hidden="true">+</span>
            </button>
            <button id="toggleSourcePreview" className="mappingTool sourcePreviewButton" type="button" aria-expanded="false" aria-controls="sourcePreviewPanel">
              <span>Preview source rows</span>
              <span className="disclosureIcon" aria-hidden="true">+</span>
            </button>
          </div>
          <section id="operationalMapping" className="mappingToolsPanel" aria-labelledby="optionalColumnsTitle" hidden>
            <h3 id="optionalColumnsTitle">Optional operational columns</h3>
            <div id="operationalGrid" className="mappingGrid"></div>
          </section>
          <section id="sourcePreviewPanel" className="mappingToolsPanel" aria-labelledby="sourcePreviewTitle" hidden>
            <h3 id="sourcePreviewTitle">Source preview</h3>
            <p className="sub">First five rows, before mapping and calculations.</p>
            <div id="preview" tabIndex="0" role="region" aria-label="Source row preview"></div>
          </section>
          <div className="setupActions">
            <button className="primary" id="buildButton" type="button">
              Confirm columns
            </button>
            <button id="cancelSetup" type="button" hidden>
              Return to dashboard
            </button>
          </div>
        </div>
        <div id="setupError" className="error" role="alert"></div>
      </section>

      {/* One customization dialog: KPI cards first, then supported overview charts. */}
      <dialog
        className="chartChooser"
        id="chartChooser"
        aria-labelledby="chartChooserTitle"
      >
        <div className="chartChooserPanel">
          <div className="chooserHeader">
            <div>
              <h2 id="chartChooserTitle">Customize your overview</h2>
              <p className="sub">Put your most useful numbers and charts up front.</p>
            </div>
            <button id="closeChartChooser" className="iconButton" type="button" aria-label="Close customization">×</button>
          </div>
          <div className="chooserContent">
            <section id="kpiPanel" className="chooserSection" aria-labelledby="kpiTitle">
              <h3 id="kpiTitle"><span className="sectionNumber">01</span> KPI cards</h3>
              <p id="kpiHelp" className="sub">Choose your key measures, or leave all unchecked to use the defaults.</p>
              <div id="kpiOptions" className="kpiOptions"></div>
            </section>
            <section className="chooserSection" aria-labelledby="chartsTitle">
              <div className="chooserSectionHeading">
                <h3 id="chartsTitle"><span className="sectionNumber">02</span> Overview charts</h3>
                <button id="selectRecommendedCharts" type="button">Recommended charts</button>
              </div>
              <p id="chartChooserSummary" className="sub" aria-live="polite">Pick up to 3 charts.</p>
              <details className="recommendationExplanation"><summary>Why these charts?</summary><div id="chartRecommendationNotes"></div></details>
              <div id="chartChoices" className="chartChoices"></div>
            </section>
          </div>
          <div className="chartChooserActions">
            <small>Detailed Dashboard keeps every supported chart.</small>
            <button className="primary" id="loadSelectedCharts" type="button">
              Load dashboard
            </button>
          </div>
        </div>
      </dialog>

      {/* Connection controls and setup help stay available without expanding the chat card. */}
      <dialog id="aiSettings" className="aiSettingsDialog" aria-labelledby="aiSettingsTitle">
        <div className="chooserHeader">
          <div>
            <h2 id="aiSettingsTitle">AI settings</h2>
            <p className="sub">Choose how you connect and review how your data is used.</p>
          </div>
          <button id="closeAiSettings" className="iconButton" type="button" aria-label="Close AI settings">×</button>
        </div>
        <div className="aiSettingsContent">
          <h3>Current answer mode</h3>
          <p id="aiDataNotice" className="sub aiDataNotice" aria-live="polite">Choose an answer mode to see how your data is used.</p>
          <button id="refreshModels" type="button">Refresh AI options</button>
          <p className="sub modelStatus" id="insightMode" role="status">Calculated insights · AI optional</p>
          <div className="browserOllamaPanel">
            <h3>Local Ollama</h3>
            <div className="browserOllamaActions">
              <button id="connectBrowserOllama" type="button">Connect Local Ollama</button>
              <button id="disconnectBrowserOllama" type="button" disabled>Disconnect</button>
            </div>
            <p id="browserOllamaStatus" role="status">Not connected. Connect only if you want AI inference on this computer.</p>
            <details className="ollamaSetup">
              <summary>Setup and troubleshooting</summary>
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
        </div>
      </dialog>

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
            <section className="panel insightsPanel compactAssistant" aria-labelledby="assistantTitle">
              <div className="insightHeader">
                <div>
                  <h2 id="assistantTitle">Business assistant</h2>
                </div>
                <button id="openAiSettings" className="quietButton" type="button" aria-haspopup="dialog">AI settings</button>
              </div>
              <div className="modelRow">
                <label htmlFor="localModel" className="srOnly">Answer mode</label>
                <select id="localModel" defaultValue="" aria-describedby="aiModeSummary">
                  <option value="">Calculated answers</option>
                </select>
                <span id="aiModeSummary" className="modeSummary" aria-live="polite">Uses dashboard data</span>
              </div>
              <div className="conversationViewport" tabIndex="0" aria-label="Conversation and supporting calculations">
                <p id="insightAnswer" aria-live="polite"></p>
                <div id="analystEvidence" hidden></div>
              </div>
              <form id="insightForm">
                <label htmlFor="insightQuestion" className="srOnly">Ask a question about this dashboard</label>
                <div className="askRow">
                  <input id="insightQuestion" placeholder="Ask about your business…" required />
                  <button id="askButton" type="submit">Ask</button>
                </div>
              </form>
              <div className="conversationFooter">
                <small>New data or filters reset the conversation.</small>
                <button type="button" id="newConversation" className="quietButton">New conversation</button>
              </div>
            </section>
            <section className="panel highlightsPanel" aria-labelledby="highlightsTitle">
              <h2 id="highlightsTitle">At a glance</h2>
              <p className="previewHighlightsNote">Calculated from your selected data</p>
              <div id="insightCards" className="insightCards"></div>
            </section>
          </div>
        </div>

        {/* These controls filter both browser calculations and backend analyst queries. */}
        <div id="dashboardFilters" className="filters" role="region" aria-label="Dashboard filters">
          <div className="filterHeading">
            <strong>Filters</strong>
            <span className="hint" id="count" aria-live="polite"></span>
          </div>
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
          <div className="filterActions">
            <button id="reset" type="button">Reset filters</button>
            <button id="chooseCharts" type="button" aria-haspopup="dialog">Customize overview</button>
          </div>
          <details>
            <summary>Data notes</summary>
            <div id="sidebarNotes"></div>
          </details>
        </div>

        {/* Detailed Dashboard includes every chart supported by the mapped data. */}
        {/* The overview selection only controls its three featured chart slots. */}
        <div id="detailPage" hidden>
          <div className="detailHeading">
            <div>
              <h2>Detailed dashboard</h2>
              <p className="sub">All supported charts, using your current filters.</p>
            </div>
            <a href="#datasetTablePanel" className="tableJump">View data table ↓</a>
          </div>
          <div className="cards" id="cards"></div>
          <div id="detailCharts" className="businessDetailGrid"></div>
          <div id="detailTables" className="businessDetailGrid"></div>
          <section id="datasetTablePanel" className="panel datasetTablePanel" aria-labelledby="datasetTableTitle">
            <div className="datasetTableHeader">
              <div>
                <h2 id="datasetTableTitle">Dataset rows</h2>
                <p className="sub">All mapped and calculated columns. Filters apply to every row.</p>
              </div>
              <span id="datasetRowCount" className="rowCount" aria-live="polite"></span>
            </div>
            <div className="datasetTableScroll" tabIndex="0" role="region" aria-label="Filtered dataset rows">
              <table id="datasetTable"></table>
            </div>
            <nav className="datasetPagination" aria-label="Dataset table pages">
              <small id="datasetPageStatus" aria-live="polite"></small>
              <div>
                <button id="previousDataPage" type="button">Previous</button>
                <button id="nextDataPage" type="button">Next</button>
              </div>
            </nav>
          </section>
        </div>

        <div className="note" id="dataNotes"></div>
        <footer>
          Local data processing. Gross profit excludes operating expenses.
        </footer>
      </main>
    </>
  );
}
