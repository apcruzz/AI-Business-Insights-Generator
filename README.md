# Free Business Dashboard

A local version of your two-page dashboard with business setup, CSV/Excel uploads, column suggestions, automatic charts, calculated insights, and optional local AI explanations.

There are no API keys, subscriptions, cloud model calls, or hosting bills in this app. It runs on your existing computer. You still supply the computer, electricity, and initial downloads. Uploaded files are processed in memory and are not saved by the server.

## Project structure

```text
free_business_dashboard/
├── backend/              # Python API, file analysis, Ollama integration
├── src/                  # React/Vite frontend
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

1. Choose Restaurant, Furniture shop, Retail store, Café, or Other business.
2. Upload a CSV, XLSX, or XLS file, or choose a included sample.
3. Click **Inspect columns**. For a workbook, choose the worksheet containing the sales table.
4. Check the suggested mappings, date order, decimal separator, and currency. The first row must contain unique column headings. No merged heading rows or subtotal rows.
5. Click **Build dashboard**. Use the top navigation to switch between Business Overview and Detailed Dashboard.

The business selection provides context for explanations; available columns determine which charts and metrics can be calculated. This version is designed for sales/order data. Payroll logs, inventory-only files, and unrelated business records require additional data models.

**Required:** net sales/revenue, gross sales, or both quantity and unit price. When deriving net sales from gross sales without discounts, the app explicitly treats discounts as zero and reports that assumption.

**Optional:** dates, times, products, categories, quantities, costs, gross profit, discounts, employee, weather, payment labels, store, and order IDs. Profit is unavailable without mapped costs or gross profit. Missing quantities never default to one. Ambiguous names such as `Amount` need manual mapping. Date columns with raw numeric Excel serials need formatting as dates in the source workbook. Amounts should exclude tax/tips if intended to represent sales revenue.

All mapped amounts must represent the same grain: one sales line or one order per row. Do not repeat an order total on every line. Order IDs are checked for conflicting dates, times, or payment labels. Conflicting IDs disable order counts. Even passing these checks does not prove receipt grouping is correct; confirm what the IDs mean in your system. When filtering by product/category, order counts mean matching orders and order averages mean selected revenue per matching order, not the original full receipt value.

For more than 14 recorded dates, the trend uses weekly totals. For more than 40, it uses monthly totals. Missing days are not silently treated as zero. Hourly charts show the top eight products and group the rest under Other products. Negative category totals use a contribution list in place of a pie. Duplicate source rows are flagged and retained for review. Gross margin is total gross profit divided by total net sales, not an average of line margins.

## Optional free local AI

Without a model, **Calculated answers** already handles product sales, gross margin, sales timing, and matching-order questions. These are deterministic calculations, not a language model.

For broader explanations:

1. Install Ollama from https://ollama.com/download.
2. Download a local model. For example:

```sh
ollama pull qwen3:4b
```

This is an existing trained model; you do not need to train a new one. The listed Qwen3 4B quantized download is about 2.5 GB; working memory needs are higher and speed depends on your hardware. A smaller model can be used if your computer struggles.

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

4. In your dashboard, click **Check local AI** and select a downloaded local model under **Answer mode**.

The app connects only to `127.0.0.1:11434`, excludes cloud-linked model entries, and does not sign in or download models automatically. It sends your question and a small summary of filtered totals/rankings to the local model, not the entire workbook. Calculations and chart values remain controlled by code. Model answers are explanations and can still make mistakes. No generated code is executed. No fine-tuning/training is performed.

The model files are not bundled. Internet is needed for initial Python package/model downloads. After setup, data processing and local model inference can operate offline. This download does not provide a public hosted URL or multi-user service.

## Samples and validation

The furniture, restaurant, and retail samples in `data/samples/` are fictional test data spanning June 1–August 29, 2026. `Cafe.csv` is the original provided café dataset and includes receipt-grouping warnings.

Run `npm test` on Mac after creating `.venv`, or run `python -m tests.validate_samples` from an activated environment, to verify expected totals and key missing-data behavior. CSV/Excel ingestion, number/date parsing, model request wiring, adaptive chart generation, filtering, and page switching were checked. Actual language-model inference requires your installed Ollama model and was not run during packaging. Browser layout was not visually checked here; the desktop overview uses a compact layout, with scrolling retained on small screens for access to controls.

## Sources

- Ollama local-only configuration: https://docs.ollama.com/faq
- Model listing API: https://docs.ollama.com/api/tags
- Local chat API: https://docs.ollama.com/api/chat
- Example model and license: https://ollama.com/library/qwen3:4b
- Ollama pricing, including local use: https://ollama.com/pricing

The app code is provided under the included MIT license. Python packages and downloaded models retain their own licenses.
