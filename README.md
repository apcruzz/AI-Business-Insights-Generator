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
  20 POSTs per user, and 6 AI questions per user. Limits return 429 with Retry-After.
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
  connectivity. Ollama is unavailable in hosted mode, including direct API requests;
  Render never connects to a visitor's computer. Keep `APP_ENV` unset for local
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


Local preparation verification: 53 Python tests and 9 JavaScript tests pass, sample
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
