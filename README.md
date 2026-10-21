# Free Business Dashboard

A local two-page dashboard with business setup, CSV/Excel uploads, column suggestions, automatic charts, calculated insights, and optional AI data analysts through Ollama or GroqCloud GPT-OSS 120B.

The dashboard and Ollama run on your computer without API keys or subscriptions. Uploaded files are processed in memory and are not saved by the server. Groq is a separate, optional cloud choice requiring a Groq API key and internet access. Selecting it sends questions, recent conversation, dataset metadata, column samples, and query results to Groq. Groq's free plan has usage limits; your account's plan determines any charges.

## Project structure

```text
free_business_dashboard/
├── backend/              # Python API, file analysis, and AI integrations
│   ├── app.py            # Backward-compatible backend entry point
│   ├── config.py         # Shared paths and local service settings
│   ├── data_loader.py    # CSV/Excel/sample loading
│   ├── fields.py         # Dashboard field names and column aliases
│   ├── business_data.py # Validate optional delivery, booking, waste and job fields
│   ├── normalizer.py     # Mapping validation and sales-data normalization
│   ├── ollama_client.py  # Local AI prompt and Ollama API calls
│   ├── groq_client.py    # Server-only Groq API transport and error handling
│   ├── ai_providers.py   # Model discovery and explicit provider selection
│   ├── analyst_agent.py  # Shared question/query/evidence/conversation loop
│   └── server.py         # Local HTTP routes used by the browser
├── src/                  # React/Vite frontend
│   ├── App.jsx           # React shell for the dashboard
│   ├── dashboard.js      # Dashboard behavior, charts, and business answers
│   ├── business-config.js # Business profiles, chart requirements and fallback rankings
│   ├── business-charts.js # Shared chart calculations and SVG renderers
│   ├── dashboard-utils.js # Shared browser helper functions
│   ├── main.jsx          # React mount point
│   ├── setup.css         # Setup and mapping styles
│   └── styles.css        # Main dashboard styling
├── data/samples/         # Included sample CSV files
├── docs/                 # Supporting project documentation
├── tests/                # Validation checks
├── app.py                # Root launcher for the Python server
├── index.html            # Vite entry HTML
├── package.json          # Frontend scripts/dependencies
├── requirements.txt      # Python dependencies
└── README.md
```

## Start on Mac

Install Python 3.10 or newer from https://www.python.org/downloads/ if needed. Extract the ZIP. In Terminal, change to its `free_business_dashboard` folder, then run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm install
npm run build
python app.py
```

The dashboard opens at http://127.0.0.1:8765. Keep Terminal open while using it. Press Control+C to stop. This version uses React and Vite for the browser app; `npm run build` creates the local `dist/` folder that `python app.py` serves.

After the first setup, start again with:

```sh
source .venv/bin/activate
python app.py
```

## Start on Windows

Install Python 3.10 or newer if needed. In PowerShell, change to the extracted `free_business_dashboard` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm run build
.\.venv\Scripts\python.exe app.py
```

To start again, run only the final command. If the port is already occupied, use `python app.py --port 8766` (or the Windows Python path).

## React/Vite development

Use this only when editing the React frontend. Keep the Python API running on port 8765 in one Terminal:

```sh
source .venv/bin/activate
python app.py --no-browser
```

Then run Vite in a second Terminal:

```sh
npm install
npm run dev
```

Open http://127.0.0.1:5173. When you finish frontend changes, rebuild the files served by Python:

```sh
npm run build
```

## Use your data

1. Choose Café, Restaurant / food truck, Retail / clothing, Tech / electronics, Furniture, Bakery, Grocery store, Ice cream shop, Online shop, Salon / barbershop, Repair / service shop, or Other business.
2. Upload a CSV, XLSX, or XLS file, or choose an included sample.
3. Click **Inspect columns**. For a workbook, choose the worksheet containing the sales table.
4. Check the suggested mappings, date order, decimal separator, and currency. The first row must contain unique column headings. No merged heading rows or subtotal rows.
5. Click **Build dashboard**. Use the top navigation to switch between Business Overview and Detailed Dashboard.

The selected business sets the recommended charts, dashboard heading, terminology, and accent colors. Recommendations follow each business’s preferred three charts and fill missing slots with supported alternatives. **Why these charts?** explains missing data; you can override the choices. If fewer than three meaningful charts are supported, only those are recommended. This version is designed for sales/order data. Payroll logs, inventory-only files, and unrelated business records require additional data models.

Grocery stores use a green theme and recommend **revenue by grocery category** (bar chart), **best-selling groceries** (horizontal bars), and **grocery product gross margin** (horizontal bars). These show department contribution, item demand, and margins; missing costs prioritize a sales trend instead. Ice cream shops use a berry-pink theme and recommend **best-selling flavors and treats** (horizontal bars), **sales by hour** (stacked columns), and **weather versus sales** (bar chart using uploaded weather only). Missing weather prioritizes a sales trend; missing hours can use category sales. Best sellers use quantities when available and explicitly use revenue otherwise.

**Required:** net sales/revenue, gross sales, or both quantity and unit price. When deriving net sales from gross sales without discounts, the app explicitly treats discounts as zero and reports that assumption.

**Optional:** dates, times, products, categories, quantities, costs, gross profit, discounts, employee, weather, payment labels, store, and order IDs. Profit is unavailable without mapped costs or gross profit. Missing quantities never default to one. Ambiguous names such as `Amount` need manual mapping. Date columns with raw numeric Excel serials need formatting as dates in the source workbook. Amounts should exclude tax/tips if intended to represent sales revenue.

All mapped amounts must represent the same grain: one sales line or one order per row. Do not repeat an order total on every line. Order IDs are checked for conflicting dates, times, or payment labels. Conflicting IDs disable order counts. Even passing these checks does not prove receipt grouping is correct; confirm what the IDs mean in your system. When filtering by product/category, order counts mean matching orders and order averages mean selected revenue per matching order, not the original full receipt value.

For more than 14 recorded dates, the trend uses weekly totals. For more than 40, it uses monthly totals. Missing days are not silently treated as zero. Hourly charts show the top eight products and group the rest under Other products. Negative category totals use a contribution list in place of a pie. Duplicate source rows are flagged and retained for review. Gross margin is total gross profit divided by total net sales, not an average of line margins.

## Optional free local AI

Without a model, **Calculated answers** already handles product sales, gross margin, sales timing, and matching-order questions. These are deterministic calculations, not a language model.

For questions that require new calculations directly against the uploaded data:

1. Install Ollama from https://ollama.com/download.
2. Download the recommended local model:

```sh
ollama pull llama3
```

This is an existing trained model; you do not need to train a new one. Llama 3 is preferred when installed. A smaller Llama 3.2 model can be used if your computer struggles:

```sh
ollama pull llama3.2:3b
```

3. Start Ollama in **local-only** mode. Quit an already running Ollama app/service first, then run it in a separate terminal:

```sh
# Mac or Linux
OLLAMA_NO_CLOUD=1 ollama serve
```

```powershell
# Windows PowerShell
$env:OLLAMA_NO_CLOUD="1"
ollama serve
```

4. In your dashboard, click **Refresh AI options**. On initial discovery, `llama3:latest` is preferred under **Answer mode**, with Llama 3.2 as a fallback. You can still choose a different downloaded local model. Refreshing preserves your explicit choice, including Calculated answers.

The Ollama option connects only to `127.0.0.1:11434`, excludes cloud-linked Ollama model entries, and does not sign in or download models automatically. After column confirmation, the backend retains the uploaded CSV/selected Excel worksheet as a bounded in-memory analysis dataset. When you ask a question, the selected model receives its schema and sample values, requests read-only calculations against **all filtered rows**, inspects the returned results, and explains them. Extra source columns remain available for analysis even if they are not dashboard fields.

Expand **Supporting calculations** to inspect the actual results and, optionally, the query. The model is required to query before giving a numerical answer; invalid queries can be corrected. The application checks explicitly named extra columns and rejects new digit-based figures absent from query evidence. These checks improve traceability but do not prove that every question has been interpreted correctly. AI answers can still be wrong.

The analyst uses restricted in-memory SQL rather than `allow_dangerous_code=True` or a Python REPL. It cannot write data, read other files, load extensions or issue network requests. No fine-tuning/training is performed. No LangChain dependencies or paid services are required. See [analyst architecture, limits and tests](docs/local-data-analyst.md).

The model files are not bundled. Internet is needed for initial Python package/model downloads. After setup, data processing and local model inference can operate offline. This download does not provide a public hosted URL or multi-user service.

## Optional GroqCloud GPT-OSS 120B

1. Create a key in the [Groq API key console](https://console.groq.com/keys). Keep it on the backend; do not put it in frontend code, a `VITE_` variable, Git, or the chat input.
2. Stop the running Python dashboard. From the project directory, set the key and restart in the **same terminal**:

```sh
# macOS / Linux — replace the placeholder with your own key locally.
export GROQ_API_KEY="your-groq-api-key"
npm run build
.venv/bin/python app.py
```

```powershell
# Windows PowerShell, with your Python environment activated.
$env:GROQ_API_KEY="your-groq-api-key"
npm run build
python app.py
```

The app reads the process environment; it does not automatically load `.env` files. No new Python dependencies or local model downloads are required for Groq.

3. Reload the dashboard and upload your CSV/Excel file again, or choose a sample. Confirm the columns and load the dashboard. Restarting the backend clears previously uploaded datasets.
4. Under **Business insights**, click **Refresh AI options**, then choose **GPT-OSS 120B · Groq (cloud)** in **Answer mode**. It stays disabled until the backend has a key. Discovery checks configuration, not whether your key is valid; authentication is checked when you ask a question. Groq is never automatically selected, and works even if Ollama is stopped.
5. Ask questions such as “Compare monthly revenue changes and explain which products contributed,” “Which Milk Type brings in the most revenue?” or “How can we grow the business based on this data?” Follow up with “Why?” or “Break that down by category.” Expand **Supporting calculations** to review the numbers.

Groq uses `openai/gpt-oss-120b` and the same bounded analysis tools as Ollama. It can run multiple calculations, correct rejected queries, compare trends, and explain business recommendations. The complete selected dataset is queryable locally; the raw file is not uploaded wholesale. Column samples and returned query values can still include sensitive data, and those values are sent to Groq when selected. Only the selected Excel worksheet and current dashboard filters are included. Uploading a file alone makes no Groq call. Weather comes only from uploaded columns; no web search or external data tools are enabled.

The [Groq free plan](https://console.groq.com/docs/rate-limits) is rate-limited, and a complex question may need several model requests. The app reports quota, authentication, connectivity, and response-limit errors without silently switching providers or retrying quota errors. Start a new conversation, simplify the question, wait for the quota to reset, or choose another answer mode when needed. The app does not manage your Groq billing plan or guarantee unlimited free use. See [Groq structured outputs](https://console.groq.com/docs/structured-outputs) and the [API reference](https://console.groq.com/docs/api-reference).

If Groq rejects a request, the app distinguishes invalid credentials (`401`) from denied access (`403`). A gateway rejection can happen before API authentication and does not prove the key is wrong. The HTTP client identifies itself as `FreeBusinessDashboard/1.0`; Python's default urllib identity was observed to receive a gateway `403`/`1010` response. Restart the Python backend after updating this code. Explicit organization/project model blocks report which permissions need changing; see [Groq model permissions](https://console.groq.com/docs/model-permissions).

For request-format errors (`400`), run this from the project directory in the **same terminal where you set the key** (stop the backend with Control+C first if it is running):

```sh
.venv/bin/python -m scripts.check_groq
```

This runs the real query-and-answer loop on three fictional rows without uploading your business files. The expected result is hour 10 with USD 50 in revenue. On a rejected request, it displays a bounded diagnostic with API keys redacted, including the setting Groq rejected when supplied. The check consumes normal Groq API requests; it does not print the key or write data to disk. After the check, start the backend again with `.venv/bin/python app.py`.

A successful connection check confirms the key and basic analysis flow, not every uploaded-data question. Retry the original question in a new dashboard conversation after restarting the backend. HTTP 400 messages now distinguish explicit model-output failures, context-size limits, and rejected request settings when Groq identifies them. Only `json_validate_failed` and `tool_use_failed` receive one corrective retry, within the existing six-turn limit. Rejected output is never executed or presented as evidence. Other errors stop immediately; unknown causes remain explicitly unclassified.

## Samples and validation

Choose a business demo under **Or try a sample**. The matching business is selected automatically. Click **Inspect columns → Build dashboard → Load dashboard** to see its three preferred charts. All eleven demos are fictional, use USD, and include the required columns; no outside weather or business data is fetched. Sales and bookings are generated from August–September 2026; some deliveries and completed jobs extend into October.

| Business | Demo CSV | Included chart data |
| --- | --- | --- |
| Café / coffee shop | [Cafe_Demo.csv](data/samples/Cafe_Demo.csv) | Dated sales, categories, fictional weather |
| Restaurant / food truck | [Restaurant_Demo.csv](data/samples/Restaurant_Demo.csv) | Dish margins, categories, hourly sales |
| Retail / clothing | [Retail_Demo.csv](data/samples/Retail_Demo.csv) | Clothing categories, quantities, margins |
| Tech / electronics | [Tech_Demo.csv](data/samples/Tech_Demo.csv) | Device/accessory categories, quantities, margins |
| Furniture | [Furniture_Demo.csv](data/samples/Furniture_Demo.csv) | Category revenue, product profit, on-time/late deliveries |
| Bakery | [Bakery_Demo.csv](data/samples/Bakery_Demo.csv) | Hourly units, product waste, daily sales |
| Grocery store | [Grocery_Demo.csv](data/samples/Grocery_Demo.csv) | Grocery categories, multi-item baskets, quantities, product margins |
| Ice cream shop | [Ice_Cream_Demo.csv](data/samples/Ice_Cream_Demo.csv) | Flavors and treats, hourly sales, fictional daily weather |
| Online shop | [Online_Shop_Demo.csv](data/samples/Online_Shop_Demo.csv) | Sales channels, products, multi-line order values |
| Salon / barbershop | [Salon_Demo.csv](data/samples/Salon_Demo.csv) | Services, bookings, cancellations, daily staff capacity |
| Repair / service shop | [Repair_Shop_Demo.csv](data/samples/Repair_Shop_Demo.csv) | Services, elapsed job times, open/completed job statuses |

Cancelled/no-show salon bookings and unfinished repair jobs have zero recorded sales. Appointment schedules fit within the supplied staff capacity; repeated delivery IDs belong to multiple lines of the same delivery. All figures are illustrative, not industry benchmarks.

Regenerate these demos with `python scripts/generate_business_samples.py`. Fixed seeds keep results reproducible. Labels and business associations live in `data/sample_catalog.json` and are shared by the generator and frontend.

The earlier furniture, restaurant, and retail samples are still available under **Earlier samples** and remain unchanged. They span June 1–August 29, 2026. `Cafe.csv` is the original provided café dataset and includes receipt-grouping warnings.

Run `npm test` on Mac after creating `.venv`, or run `python -m tests.validate_samples` from an activated environment, to verify expected totals and key missing-data behavior. CSV/Excel ingestion, number/date parsing, model request wiring, adaptive chart generation, filtering, and page switching were checked. The analyst was additionally checked against local Llama 3 with synthetic monthly and extra-column questions. The desktop overview uses a compact layout, with scrolling retained on small screens for access to controls.

## Sources

- Ollama local-only configuration: https://docs.ollama.com/faq
- Model listing API: https://docs.ollama.com/api/tags
- Local chat API: https://docs.ollama.com/api/chat
- Example model and license: https://ollama.com/library/llama3.2
- Ollama pricing, including local use: https://ollama.com/pricing

The app code is provided under the included MIT license. Python packages and downloaded models retain their own licenses.

### Add-ons and line totals

Map numeric add-on charges to **Add-on / modifier charge** and select whether they apply per line or per unit. Without an existing sales total, gross sales is `quantity × unit price + modifier charge` (multiply the modifier by quantity first for per-unit charges). Discounts are then subtracted. Blank modifier cells count as zero; ingredient names are not prices. If multiple modifier columns exist, combine their charges into one numeric column before upload.

Map a completed **Line total** and confirm whether it is before or after discounts. Existing gross/net/line totals take priority over quantity, base price, and modifiers; charges are never added again. Totals must include add-ons, exclude tax/tips, and not repeat an order total on each item row. Conflicting mapped totals are rejected. Cost data should include add-on costs when calculating gross profit.

### Business-specific chart data

All uploads still need a sales amount (or the components to calculate it). Optional operational columns can be mapped in the expandable section below the main mapping fields. Column names are suggested automatically; service names/types can map to Product / dish / item.

| Chart | Additional mapped data | Counting rule |
| --- | --- | --- |
| Delivery performance | Delivery ID plus on-time/late status, or promised and actual delivery timestamps | Each delivery ID once; pending/unknown outcomes excluded |
| Bakery hourly units | Product, quantity, hour/time | Sum quantity; returns use a net-total chart |
| Waste cost | Product and waste cost | Sum per source row; do not repeat a daily waste total on every sale |
| Channel revenue | Sales channel | Sum selected net sales per channel |
| Order histogram | Validated order IDs | Sum selected lines per order; filters may show partial orders |
| Booking heatmap | Appointment ID and start timestamp | Each appointment once; cancelled/no-show bookings excluded |
| Staff utilization | Appointment ID/start/duration minutes, employee, available minutes per employee per day | Unique booked minutes divided by daily availability counted once per represented staff-day |
| Job turnaround | Job ID, service type, opened/completed timestamps | Average elapsed hours per completed job, excluding invalid/reversed timestamps |
| Job status | Job ID and status | Each job ID once |

Repeated event IDs must have consistent details. Conflicts disable the corresponding chart and produce a data note. Staff utilization measures booked capacity within the represented data, not actual working time; days absent from the upload are not inferred. Operational dates use local timestamps without timezone offsets. Weather still comes exclusively from uploaded columns.

The preferred charts and fallback order live in `src/business-config.js`; calculations and SVG rendering live in `src/business-charts.js`. Backend validation in `backend/business_data.py` controls availability. The same renderers serve both dashboard pages.

## Render Free sponsor/team demonstration

This deployment runs the React build and Python APIs on **one Docker Web Service**.
It is restricted to invited team members using individual HTTP Basic credentials
and HTTPS. The browser displays its standard sign-in prompt. Use a separate private
browser window per person; close that window after the demo (Basic authentication
has no dependable application logout). Never share credentials or use this setup
for anonymous public access or sensitive production records.

### Deployment configuration

| Setting | Exact value |
| --- | --- |
| Repository | `apcruzz/AI-Business-Insights-Generator` |
| Branch | `feature/render-free-deployment` after you review and push it |
| Service type / language | Web Service / Docker |
| Compute plan | Free |
| Root directory / Docker context | repository root / `.` |
| Dockerfile path | `./Dockerfile` |
| Docker command | leave empty; uses image CMD |
| Effective command | `gunicorn --config gunicorn.conf.py 'backend.production:create_app()'` |
| Bind address | `0.0.0.0:$PORT` (default `10000`) |
| Health check | `/health` (public; all app/API/assets require credentials) |
| Auto deploy | Off; deploy manually after review |
| Workers / threads | **1 worker**, 4 threads; 1 upload/analysis operation at a time |
| Persistent disk / database | none |

Required server environment variables:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` (also set by Dockerfile) |
| `PUBLIC_ORIGIN` | exact `https://YOUR-SERVICE.onrender.com`, no path; update if using a custom domain |
| `DEMO_USERS_JSON` | JSON object mapping each invited username to a PBKDF2 password hash |
| `GROQ_API_KEY` | your server-side Groq credential; required for cloud conversations |
| `PORT` | supplied by Render; do not put the Groq key in a `VITE_*` variable |

No shared application secret/token authenticates the hosted application. The
`/api/session` token is an authenticated session's CSRF token, not a password.
Startup rejects missing/invalid team configuration, a non-HTTPS origin, or a missing
frontend build. Groq is optional at startup so calculated dashboards remain usable
if its key is missing; configure it for this demo's AI requirement.

### Deploy step by step

1. Review this feature branch and the security notes below. Run `npm test` and
   `npm run build`; install the updated `requirements.txt` into your virtualenv first.
   The changes are intentionally **not pushed, merged, or deployed automatically**.
2. Run `.venv/bin/python scripts/demo_users.py`. Choose a unique username and a
   strong password (at least 16 characters) for each sponsor/team member. The
   script prompts invisibly for passwords and prints only a JSON hash mapping.
   Store that mapping in Render's secret environment settings, never in Git.
   Share each person's password separately through your approved private channel.
3. When you approve the changes, commit and push `feature/render-free-deployment`
   to your GitHub repository yourself. You may merge through your normal review
   process and select the merged branch instead.
4. In Render choose **New → Web Service**, connect this repository, select the
   reviewed branch, and use the settings in the table above. Pick the intended
   region and Free plan. No separate frontend service is needed.
5. Set the environment variables above. Use the exact assigned Render hostname
   for `PUBLIC_ORIGIN`; if the URL isn't known until creation, set the intended
   hostname first, then correct it and redeploy before opening the demo. Render
   health checks can succeed while an incorrect origin blocks application access.
6. Deploy manually. Wait for `/health` to return `{"status":"ok"}`. Open the HTTPS
   service URL and sign in with a team member's credentials.
7. Verify the deployed instance with **fictional data**: inspect/upload a CSV and
   XLSX, build a dashboard, change filters/charts/KPIs, explicitly select Groq, ask
   for total revenue, and ask a follow-up. Verify a second private browser using
   another account cannot use the first browser's dataset/conversation references.
   Confirm unauthenticated `/api/session`, `/api/models`, and POST requests fail.
8. Restart the service. An old POST must fail with a session-expired message;
   reload, choose the file again, and rebuild. Do not invite sponsors until these
   deployed checks pass. Rotate/remove credentials in `DEMO_USERS_JSON` and restart
   the service to revoke access; rotate the Groq key if it was exposed.

`render.yaml` provides the same service definition for an optional Blueprint.
Select the reviewed pushed branch and provide the three `sync: false` secrets
when prompted. The Blueprint disables auto deploys. If the Render CLI is installed,
validate with `render blueprints validate render.yaml` before applying. No remote
resources are created by the repository preparation itself.

### Storage, limits, and security boundaries

- Datasets are owned by an authenticated **browser session**, not just an opaque ID.
  Another account or a fresh browser cannot reuse an ID, even if it knows it.
  Conversations also include that owner, dataset, filters, and provider/model in
  their scope. The existing restricted read-only SQLite authorizer, function
  allowlist, query deadline, output bounds, and filtered-data calculations remain.
- Hosted uploads: **2 MiB**, 10,000 rows, 60 columns, 12 MiB parsed table memory.
  JSON bodies are limited to 3 MiB. XLSX expansion is capped at 12 MiB / 256 ZIP
  members, worksheet XML is checked before parsing, and encrypted XLSX is rejected.
  CSV, XLSX, and XLS remain supported. Unsupported/malformed uploads return errors.
  Local mode retains its 20 MiB / 100,000 row / 200 column limits.
- Hosted AI cache: 32 MiB total / four datasets with a one-hour lifetime; least
  recently used datasets can be evicted sooner. Conversations and browser sessions
  are bounded and expire after one hour. Uploads are processed in memory, never
  saved. Browser-rendered dashboards can remain visible after server memory expires;
  reload and rebuild before continuing questions. Closing a browser does not
  immediately delete server data; expiry/eviction/restart clears it.
- Per-minute process-local limits: 240 total authenticated/unauthenticated requests,
  120 expensive password checks, 20 failed authentications, 90 requests per user,
  20 ordinary POSTs per user, 60 browser-local step/cancel POSTs per user,
  and 6 AI questions (Groq/server Ollama or browser-local starts combined) per user. Limits return 429 with Retry-After.
  They deliberately ignore spoofable forwarded IP headers. Health checks are exempt.
  Limits reset on restart; they are not distributed abuse protection.
- One Gunicorn worker is essential because ownership, rates, datasets, and history
  are in memory. Do not increase workers/replicas without shared session/storage
  infrastructure. Work is serialized to reduce peak pandas/SQLite memory use and
  keep other threads available for health checks. Oversized/complex files can still
  exhaust memory or parser CPU; this is a small trusted-team demonstration, not a
  hardened hostile-upload service. Representative workload testing remains necessary.
- Groq reads only `GROQ_API_KEY` in the server environment. Selecting cloud AI sends
  dataset context and query results to Groq; use fictional/nonconfidential data and
  review your provider account's limits. Discovery reports configuration, not live
  connectivity. Server-side Ollama is unavailable in hosted mode. The explicit browser-local
  workflow below connects the visitor’s browser to their own Ollama; Render never
  connects to a visitor’s computer. Keep `APP_ENV` unset for local
  `python app.py` and local Ollama. Vite development continues to proxy to port 8765.
- Secure HttpOnly SameSite cookies, exact-origin POST validation, CSRF checks,
  authentication on static files/APIs, no-store responses, frame protection, and a
  restrictive content security policy are enabled. No request bodies, questions,
  passwords, or provider diagnostics are logged by the application.
- The Docker build uses an allowlist and copies only `*_Demo.csv` generated samples.
  The existing original `data/samples/Cafe.csv` is excluded from the hosted image.
  Its confidentiality cannot be established automatically: review that already
  tracked file and repository history before sharing the repository. `.gitignore`
  excludes `.env` files, but cannot protect arbitrary newly named confidential CSVs.
  Never add real uploads, credential mappings, or API keys to Git.

Render Free has 512 MB RAM, spins down after 15 minutes idle, and can take about a
minute to wake. Its storage is ephemeral; restarts/spin-down lose all sessions,
datasets, rate counters, and conversations. Free services have usage limits and
are intended for demos rather than production. See [Render Free limitations](https://render.com/docs/free)
and [compute plans](https://render.com/docs/compute-plans).

### Verification and remaining release checks

`npm test` includes the existing calculation/SQL/provider tests and production HTTP
tests for authentication, CSRF/origin validation, browser/user dataset isolation,
conversation isolation, restart recovery, CSV/XLSX uploads, malformed files, ZIP
expansion, size limits, hosted Ollama exclusion, and Groq error propagation. Cloud
responses in automated tests are mocked; they do not spend quota or send uploads.
To verify a real key/network with fictional data, run
`.venv/bin/python -m scripts.check_groq` in the environment holding your key; this
makes actual Groq calls. Complete the deployed browser checks above as well.

Passing local tests does not certify anonymous public deployment. Remaining risks
include Basic-auth credential sharing/browser caching, application-level denial of
service, parser vulnerabilities, memory exhaustion, cloud provider availability
and quotas, and loss of in-memory data. Use this configuration only for a limited
invited demo after deployment verification; use stronger identity, persistent
storage, external rate controls, and further security review for broader use.


Original Render preparation verification: 53 Python tests and 9 JavaScript tests passed, sample
validation and Vite builds pass, and the Linux/amd64 multi-stage image builds.
The real Gunicorn container smoke test runs as non-root with a custom PORT under
512 MiB / 0.1 CPU limits, verifies authentication plus profile/analyze APIs, and
confirms original samples are excluded. The current Render JSON schema validates
`render.yaml` (Render CLI was unavailable). Python and npm vulnerability audits
report no known vulnerabilities after updating Flask to 3.1.3. A tracked-file
credential-pattern scan found no matches; repository history and the original
café file's confidentiality still need human review. A live Groq connection was
not verified because the preparation environment had no `GROQ_API_KEY`.

To repeat the container check after building the image:

```sh
docker build --platform linux/amd64 -t ai-business-insights:render-demo .
docker run --rm --platform linux/amd64 --memory=512m --cpus=0.1 -i ai-business-insights:render-demo python - < tests/container_smoke.py
```

This test uses generated credentials only and makes no Groq requests. The resource
limit check is a small sample smoke test, not a concurrency/capacity certification.


## Connect your own Ollama from the deployed website

Browser Local Ollama lets an invited user run AI inference on their own Windows
or macOS computer while using the Render website. No companion application,
public Ollama server, tunnel, or Render-hosted model is required. Install Ollama,
download a local model, allow the exact trusted website origin, and explicitly
connect in the dashboard. Ollama settings are local computer settings, not Render
environment variables.

**Data flow:** uploads and SQL processing still happen on Render. Render sends
schema/sample context, recent conversation, and verified query results to your
browser. Your browser sends that context to your own `127.0.0.1:11434` Ollama.
The browser returns model action text to Render, where dataset ownership and SQL
restrictions are checked. No Groq inference is requested in this mode. The raw
file remains subject to the existing temporary server storage and authentication
rules. This feature does not provide fully offline or device-only data analysis.

### Windows setup

1. Install [Ollama for Windows](https://ollama.com/download/windows).
2. In PowerShell, download a local model (internet is needed for the download):

   ```powershell
   ollama pull llama3.2:3b
   ```

3. Quit the running Ollama app from the taskbar/system tray before starting another
   server. In PowerShell run, and keep that window open:

   ```powershell
   $env:OLLAMA_HOST="127.0.0.1:11434"
   $env:OLLAMA_NO_CLOUD="1"
   $env:OLLAMA_ORIGINS="https://ai-business-insights-generator.onrender.com"
   ollama serve
   ```

4. Alternatively set those same three **user environment variables** through Windows
   Settings → Edit environment variables for your account, then restart the Ollama
   app. Terminal settings affect only the server launched from that terminal.

### macOS setup

1. Install [Ollama for macOS](https://ollama.com/download/mac).
2. In Terminal, download `ollama pull llama3.2:3b` (or use a local model you already
   installed). Quit an already running Ollama app/server first. Then run:

   ```sh
   OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_ORIGINS=https://ai-business-insights-generator.onrender.com ollama serve
   ```

   Keep this terminal open. If you prefer the macOS Ollama app, set its environment
   before restarting it:

   ```sh
   launchctl setenv OLLAMA_HOST "127.0.0.1:11434"
   launchctl setenv OLLAMA_NO_CLOUD "1"
   launchctl setenv OLLAMA_ORIGINS "https://ai-business-insights-generator.onrender.com"
   ```

   Reopen Ollama yourself after quitting the old app. These commands configure the
   app launched in your macOS login session; they do not modify the Render server.

The allowed origin must be the exact site you trust, with scheme and hostname, no
path. For a preview/custom domain, replace the example with that exact HTTPS
origin. The dashboard shows the active origin in its setup instructions. Never
use `OLLAMA_ORIGINS=*`, bind to `0.0.0.0`, open router ports, disable browser
security, or create a public tunnel. The allowlisted origin can call your local
Ollama API while Ollama is running; remove it and restart Ollama to revoke that
access. The connection button is consent within this app, not an access-control
boundary for a compromised trusted site.

Ollama's [environment and origin configuration](https://docs.ollama.com/faq) and
[structured output documentation](https://docs.ollama.com/capabilities/structured-outputs)
explain the underlying server settings and JSON-schema format.

### Use it in the website

1. Sign in, upload a fictional CSV/XLSX or load a demo, confirm mappings, choose
   KPIs/charts, and load the dashboard.
2. Under **Business insights**, click **Connect Local Ollama**. No localhost fetch
   is made by the browser during page load, upload, model refresh, or cloud chat.
3. If Chrome asks for **Local Network Access**, allow it for this trusted website.
   Current Chrome supports the `targetAddressSpace: "loopback"` fetch hint used by
   this transport. CORS permission from Ollama is still required separately. See
   [Chrome's permission guidance](https://developer.chrome.com/blog/local-network-access)
   and the [Local Network Access specification](https://wicg.github.io/local-network-access/).
4. The status shows connected, missing models, or troubleshooting details. Select
   an installed **Local Ollama (this browser)** entry under **Answer mode**. Connecting
   does not automatically select local inference or switch a prior Groq choice.
5. Ask your business question. Supporting calculations and follow-up history work
   through the same server-owned analyst engine as Groq. Changing filters, dataset,
   provider, model, or conversation resets the relevant scope. A question uses at
   most six model actions and four model-requested SQL queries; advice can also
   receive a server-calculated product/month overview.
6. **Reconnect Local Ollama** refreshes installed models explicitly. **Disconnect**
   aborts this page's local fetches and pending local analysis, removes local browser
   models, and returns an active local selection to Calculated answers. It never
   switches to Groq. Disconnect does not stop Ollama, revoke Chrome permission,
   or change the allowlisted origin. Normal local-development/server Ollama remains
   available when running `python app.py` with `APP_ENV` unset.

### Troubleshooting and compatibility

- **Connection/CORS/permission error:** check Ollama is running, the exact active
  website origin is allowed, and the old Ollama process was stopped before changing
  settings. In Chrome's site settings, allow local-network access if previously
  denied. JavaScript cannot reliably distinguish CORS denial from permission denial
  or an offline loopback service, so the message lists these checks together.
- **Connected with no models:** download a local model, then Reconnect. Llama 3 (`llama3:latest`) is the preferred
  tested model when your computer has sufficient memory; `llama3.2:3b` is lighter
  but was less reliable on recommendations and comparisons. Remote/cloud
  linked models and names ending in `:cloud` are excluded. Run `ollama list` locally
  to inspect installed models.
- **Missing model / timeout:** a selected model might have been removed or need time
  to load into memory. Reconnect, wait, or select a smaller model. Each local chat
  request times out after 120 seconds; a complete pending question expires after
  ten minutes. There is no cloud fallback after any local failure.
- **Session/server restart or expired dataset:** reload, upload/build the dashboard
  again, and reconnect. Pending runs and conversations are temporary.
- **Browser limitations:** Chrome on Windows/macOS is the primary manual acceptance
  target. Older Chrome, managed browser policies, OS privacy controls, Firefox,
  Safari, and mobile devices can have different mixed-content, CORS, or local-network
  behavior. They are not certified by the automated transport tests. Do not disable
  browser security flags to make a connection work; use supported Chrome or choose
  an existing answer mode explicitly.

### Browser-local security and validation

The production CSP adds only `http://127.0.0.1:11434` to `connect-src 'self'`.
The transport has no configurable URL, rejects redirects, omits all credentials
and referrers, requests only `/api/tags` and `/api/chat`, excludes cloud-linked
model discovery results, and does not call generation, pull, delete, or arbitrary
Ollama endpoints. Model output remains untrusted even with structured output.

Authenticated, CSRF-protected `/api/ollama-start`, `/api/ollama-step`, and
`/api/ollama-cancel` retain the production host/origin checks and user rate limits.
Runs are bound to the browser session and checked against dataset ownership on
every step. Single-use random step tokens prevent replay/out-of-order actions.
Clients cannot supply evidence, SQL results, conversation history, or different
filters mid-run. The shared engine validates model text and uses the unchanged
read-only SQLite authorizer/limits. No Python evaluation or remote SQL connection
is introduced. Weighted product margins and monthly rankings/comparisons receive additional
server-calculated evidence. Grouped margin queries reject bare per-line financial
ratios, and explicit conflicting margin/change/ranking claims receive corrective
feedback. These checks are deliberately limited, not a general SQL/prose proof.
Natural-language correctness checks remain heuristic; supporting
numbers do not prove a model's causal explanation or recommendation.

At most four pending runs exist per process, one per session, with a ten-minute
TTL. Inference packets are capped at 128 KiB, accepted model text at 16,000
characters, and browser HTTP responses at 256 KiB. SQL connections and filtered
DataFrames are not retained between browser steps. Cancellation, completed runs,
new questions, TTL expiry and capacity eviction free pending-run slots. No browser
model request occupies a Render worker while local inference is running.

Automated validation includes all six requested question types with deterministic
model actions and real authorized SQL, active filters, history, evidence tables,
wrong-user/browser access, replay, malicious SQL, forged evidence, expiry, output
bounds, and cancellation. Browser transport tests cover explicit connection,
local model discovery, schema format, credentials/redirect restrictions, timeout,
permission/CORS messages, no cloud fallback, and privacy notices. Existing Groq
transport and conversation tests still run against mocked provider responses;
these are not a live Groq quota/credential test.

Optional macOS Chrome check with the installed Ollama and **fictional data only**:

```sh
.venv/bin/python -m pip install playwright
.venv/bin/python -m scripts.check_browser_ollama
```

By default this check uses the already-installed `llama3:latest`; use
`--model llama3.2:3b` to try the smaller model. This uses an isolated headless Chrome profile and temporary HTTPS server at
`https://127.0.0.1:9443`. It does not change your Ollama settings, download models,
use Groq, or access the deployed service. The local HTTPS origin is normally
allowed by Ollama's default origins; a custom Ollama allowlist may reject it.
This checks local browser integration, not a public-origin permission prompt.

Manual release checks on **both Windows Chrome and macOS Chrome**, using the
actual HTTPS Render origin and individual team accounts:

1. Load/sign in and inspect browser Network tools: no `11434` request until Connect.
2. Set up the exact Ollama origin, click Connect, and allow the Chrome permission.
   Repeat with permission denied and wrong origin to check the troubleshooting UI.
3. Upload fictional CSV and XLSX, choose a model, and test:
   - Which product generated the highest revenue?
   - Which product has the lowest gross profit margin?
   - What month had the lowest sales?
   - How can this business improve profitability?
   - Why did revenue decrease compared with the previous month?
   - What other information is needed to make a better recommendation?
4. Compare tables to the dashboard with and without active date/product filters.
   Check that missing/cause information is stated honestly rather than invented.
5. Verify follow-up history, New conversation, filter/provider/model changes,
   disconnect during inference, reconnect, stopped Ollama, missing models and timeout.
6. Confirm browser `/api/chat` calls go only to `127.0.0.1:11434`, and server-local
   inference does not occur. Explicitly switch to Groq and check its existing flow.
7. Verify two separate signed-in accounts/browsers cannot use each other's dataset,
   conversation or pending-run IDs. Restart the service and check reload/reupload
   recovery. Keep credentials and provider keys out of browser screenshots.

### Review and deploy this change

Work is on `feature/browser-local-ollama`, separate from the running
`feature/render-free-deployment` branch. Nothing is pushed, merged or deployed
automatically. Run `npm test`, `npm run build`, and review the diff. After review:

1. Commit and push only this reviewed feature branch to GitHub. Keep `.env`, keys,
   hashes, model files and uploaded datasets out of commits.
2. Open a pull request from `feature/browser-local-ollama` into
   `feature/render-free-deployment`, review it, and merge when approved. You can
   alternatively create a separate Render test service from the new branch.
3. The existing Render service has Auto-Deploy off. After merging, use **Manual
   Deploy → Deploy latest commit** for `feature/render-free-deployment`. Docker
   rebuilds the frontend and Python backend together. No new Render environment
   variables are needed; preserve `APP_ENV`, `PUBLIC_ORIGIN`, `DEMO_USERS_JSON`,
   `GROQ_API_KEY`, the Free plan, one Gunicorn worker and `/health`.
4. Complete the Windows/macOS production-origin acceptance checks before sponsor
   use. If necessary, use Render rollback to return to the prior working image.


After reviewing the diff, these commands stage only the intended feature files:

```sh
git switch feature/browser-local-ollama
git diff --check
git add README.md docs/local-data-analyst.md backend/ai_providers.py backend/analyst_agent.py backend/api.py backend/production.py backend/browser_analyst.py src/App.jsx src/ai-options.js src/browser-ollama.js src/dashboard.js src/styles.css tests/test_analyst.py tests/container_smoke.py tests/test_browser_analyst.py tests/browser-ollama.test.mjs scripts/check_browser_ollama.py
git diff --cached --stat
git commit -m "Add browser-mediated local Ollama analyst"
git push -u origin feature/browser-local-ollama
```

These commands are instructions for your review/release step; they are not run
automatically. On GitHub, create a pull request with **base**
`feature/render-free-deployment` and **compare** `feature/browser-local-ollama`.


Browser feature test status: the deterministic suite passes 61 Python tests and
17 JavaScript tests, including all six question categories, real filtered SQL,
owned sessions, unsafe actions and evidence verification. Vite and Linux Docker
builds pass. Live macOS Chrome 155 testing used installed local models with
fictional rows on a temporary HTTPS origin; this does not certify the actual
public-origin permission prompt. Initial 3B runs exposed wrong margin and monthly
interpretations; the resulting regression checks now reject grouped bare-row
margins and selected explicit contradictory claims. Model interpretation remains
fallible, so verify supporting tables and use a stronger model when possible.
Windows Chrome, the real Render-origin permission/CORS path, and live Groq remain
manual release checks. No Groq key was available for a live connection test here.


The final macOS Chrome 155 / `llama3:latest` browser check completed all six
questions through the real local Ollama. It verified Tea USD 220 revenue, Coffee
10% margin, February USD 60 sales, and rendered evidence for recommendations.
The comparison/follow-up checks used a real date-filter change to January–February:
three selected rows, January USD 100, February USD 60 and a USD 40 decline. The
model correctly stated that causal information was missing. Disconnect and zero
server/Groq inference calls were verified. The final Gunicorn Linux container
smoke check passed under 512 MiB / 0.1 CPU, including authenticated browser-analysis
SQL steps with synthetic actions. No public Render-origin or Windows browser
acceptance check was performed, and no service was deployed or changed.
