# Data analyst: browser Ollama, server-local Ollama and GroqCloud

## Workflow

The existing upload/mapping/chart workflow remains unchanged. `/api/analyze` now also registers an immutable analysis snapshot and returns an opaque `datasetId`. CSV and the selected Excel worksheet share the same pipeline. Source fields not mapped to dashboard fields are preserved under their original names (or a collision-safe alias).

The snapshot is not sent wholesale to an LLM, and no inference runs automatically at upload time. Once Gemini or an explicitly connected Ollama model is selected, a compact automatic overview uses server-calculated aggregates (see below). Follow-up questions use the full analyst workflow:

1. The browser sends the explicit provider/model, dataset ID, question, conversation ID and current filters to `/api/analyst`. Requests without a provider retain the original Ollama behavior.
2. The backend retrieves that dataset and applies the dashboard date/category/product/weekday/time-of-day filters.
3. The selected provider receives the available columns, bounded sample values, column origins, row count and limitations. Ollama stays local. Groq receives this context over HTTPS, along with recent conversation and subsequent calculation results.
4. The model requests a read-only SQL calculation against the complete selected rows.
5. The application runs it, returns the actual result, and allows the model to correct errors or request another calculation.
6. The model explains the evidence; the UI shows the computed table separately from its interpretation.

For “Which month had the highest sales revenue?”, the model can group `Net_Sales` by `strftime('%Y-%m', Date)` and rank the results. For “Sales by Milk Type,” it can query an uploaded Milk Type column even though that field is not one of the predefined dashboard metrics. Sample rows are for schema interpretation, not the numerical basis of the answer.

## Modules

- `backend/analyst_datasets.py`: thread-safe, process-local dataset cache, source-field preservation and filter application.
- `backend/analyst_query.py`: read-only SQLite execution tool and result/resource limits.
- `backend/analyst_agent.py`: bounded structured-output query/result/review loop, extra-column checks and digit-based evidence checks.
- `backend/ollama_client.py`: local model discovery and shared chat transport. The original `/api/explain` route remains compatible but the UI now uses `/api/analyst`.
- `backend/groq_client.py`: fixed Groq HTTPS endpoint, server-side environment key, strict JSON-schema actions, bounded responses, and sanitized provider errors. It does not execute calculations or enable Groq browsing/code tools.
- `backend/ai_providers.py`: discovery, provider/model validation and a shared transport interface. Groq discovery does not need Ollama or make cloud calls. Provider identity is part of conversation scope.
- `backend/server.py`: connects upload registration and the analyst endpoint to these services.
- `src/ai-options.js`, `src/dashboard.js`, `src/App.jsx`, `src/setup.css`: explicit provider selection, cloud data notice, dataset ID propagation, active filters, analyst progress and expandable evidence tables.

No new runtime dependencies, database migrations, saved uploads, business profiles or external weather integrations were introduced. All dataset preparation uses the existing pandas dependency; calculations use Python's built-in SQLite.

## Why this differs from create_csv_agent

[LangChain's pandas agent implementation](https://github.com/langchain-ai/langchain-experimental/blob/main/libs/experimental/langchain_experimental/agents/agent_toolkits/pandas/base.py) uses a Python REPL and requires an appropriately sandboxed environment when dangerous code is enabled. This app instead implements the inspect/calculate/review workflow using an allowlisted read-only tool. [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) and [Groq strict structured outputs](https://console.groq.com/docs/structured-outputs) provide the same query/answer action format. This is application-managed tool execution: the model selects an action, the backend validates/runs it, and results return to the next model turn.

Generated Python, shell commands, `eval` and `exec` are never used. SQLite's authorizer denies writes, schema reads, file attachment, PRAGMA, extensions, unapproved functions and recursive CTEs. Each request gets an isolated in-memory table containing only the selected dataset rows. Model text and upload cells cannot grant additional permissions.

## Limits and accuracy

- Cache: four datasets, total estimated DataFrame memory at most 128 MiB, one-hour expiry; server restart clears it. Evicted/expired data requires rebuilding the dashboard. Oversized datasets retain calculated-answer functionality.
- At most two simultaneous server analyst requests. Manual questions retain six model turns and four queries, with a 180-second loop deadline (60 seconds per local/Groq call; 90 seconds per Gemini call). Browser Ollama runs have their existing session-owned expiry and local transport limits.
- SQL: one statement, at most 8000 characters, two-second/progress-budget limit, at most 12 output columns and 30 returned rows. Truncation is explicitly shown. Result JSON is limited to 14,000 characters and prompt history is bounded.
- Canonical financial columns are validated by existing normalization. Extra source fields remain text; monetary/date conversion of these fields requires care and is not automatically trusted.
- Missing canonical fields and unvalidated order IDs are not exposed as invented data. Row count is not order count. Weather analysis can use uploaded columns only.
- An explicit extra-column reference in the question must be used by its query. New digit-based numbers in the explanation must occur in the question or successful result values (with rounding tolerance). This is a check, not a proof: it does not validate every inference, numbers written as words, dimension choice, or natural-language interpretation. Always inspect the supporting calculation for consequential decisions.
- Unsupported questions, invalid plans and timeouts produce an honest unavailable/incomplete result. Calculated answers remain selectable without Ollama. There is no silent substitution of unrelated dashboard facts.
- Follow-up questions retain up to four recent exchanges and bounded verified calculation results in server memory. Conversations expire after an hour and are isolated by dataset, filters, provider and model. New conversation clears the browser context. Restarting the server clears all memory.
- Growth questions receive a product/time overview where available and guidance to link recommendations to measured findings. Recommendations are suggestions to test, not guaranteed outcomes.
- Arbitrary Python libraries, external datasets and forecasting models are not provided.

## Running and validation

```sh
npm test
npm run build
.venv/bin/python app.py
```

For local AI, Ollama must be running with a downloaded model. Llama 3 (`llama3:latest`) is preferred, with Llama 3.2 as a fallback. For Groq, set `GROQ_API_KEY` in the backend environment and explicitly select GPT-OSS 120B. See the [README setup steps](../README.md#optional-groqcloud-gpt-oss-120b). Rebuild/reupload after restarting the Python backend because the analysis cache is intentionally temporary.

Groq tests mock only the provider/network while running actual CSV/Excel parsing, filtered in-memory SQL, source-column queries, multi-step/window calculations, and conversation scoping. Transport tests check authentication, strict schema, quota/connectivity failures, truncated output, and secret-free errors. Browser helper tests ensure cloud inference is never selected automatically and that explicit Calculated answers choices survive refresh. These tests do not establish live Groq answer quality; that requires a configured key and a live request.

Automated tests cover month/year aggregation and ties, active filters, extra source dimensions, CSV/Excel parity, cache eviction/expiry, unsupported data, invalid query correction, evidence checks and blocked filesystem/write operations. Live synthetic-data checks with Llama 3 correctly returned March 2025 / USD 320 and, under a January–February filter, Oat USD 150 / Whole USD 200. These examples are tests of this workflow, not a general accuracy guarantee.


## Browser-mediated local inference

The explicit `browser_ollama` provider uses `/api/ollama-start`, `/api/ollama-step`
and `/api/ollama-cancel`. `AnalystRun` is the shared server-owned state machine for
all transports: prompts, schema, filters, evidence, SQL authorization and history
stay on the backend. `BrowserRuns` stores bounded, session-owned runs with
single-use step tokens. The browser calls only its own fixed loopback Ollama and
returns raw model text; it cannot replace evidence or switch datasets mid-run.
QueryTool connections are created/closed per step, so no SQLite connection crosses
HTTP request threads. Inference is never proxied through Render or Groq in this
mode. Existing synchronous `/api/analyst` remains the path for Groq and local
server Ollama, with its existing deadlines and provider behavior.

See the README's browser Ollama section for exact OS setup, privacy boundaries,
limits, automated checks and the production-origin manual acceptance checklist.

## Short automatic reviews

The overview computes totals and reviewed product/category/month groups against
all filtered rows in one temporary, read-only SQLite table. Only necessary
normalized fields enter this table. Full query results remain available for
verification and follow-ups; the model receives totals and up to three recorded
groups per dimension, not raw column samples or a SQL-planning prompt. Long
uploaded labels are omitted from that compact input rather than renamed.

Local overviews request at most 450 output tokens with a 4,096-token context,
and a short review of at most 130 words. There are at most two narration attempts
including correction; a model cannot add SQL rounds to this initial review.
The existing numerical checks still apply, so an unverified response is never
shown as a completed review. Manual questions retain 1,200 output tokens and an
8,192-token context. Explicitly used local models stay loaded for five minutes;
there is no background connection, preload, or cloud fallback. Browser overview
calls time out after 90 seconds. Cold model loading, available RAM/GPU, and
other local inference can still affect response time.

Gemini uses its own compact reasoning/output profile and one bounded retry only
for transient overview transport failures; see [Gemini setup](gemini-setup.md).
The same dataset/filter/provider/account scopes and explicit local connection
requirements continue to apply.

The November 16, 2026 fictional three-row check on this Mac reduced a Llama
3.2:3b review from six calls / 41.5 seconds ending incomplete to one call /
7.1 seconds ending answered. Llama 3 (8B) finished the compact review in one call /
11.4 seconds, including 3.5 seconds of model loading. These are individual local
measurements, not latency guarantees or proof of every natural-language claim.
The 202 unit tests, Vite build and four Chrome integration checks passed; cloud
responses in the tests were mocked. No Gemini API key was available for a live
Gemini latency/availability check. With your backend key set, the existing
`python -m scripts.check_gemini --model gemini-3.5-flash-lite` performs an optional
live connection check using fictional data and normal API quota.
