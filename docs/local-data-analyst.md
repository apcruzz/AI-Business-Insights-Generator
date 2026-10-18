# Data analyst: local Ollama and GroqCloud

## Workflow

The existing upload/mapping/chart workflow remains unchanged. `/api/analyze` now also registers an immutable analysis snapshot and returns an opaque `datasetId`. CSV and the selected Excel worksheet share the same pipeline. Source fields not mapped to dashboard fields are preserved under their original names (or a collision-safe alias).

The snapshot is not sent wholesale to an LLM, and no inference runs automatically at upload time. Once an AI model is selected and the user asks a question:

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
- At most two simultaneous analyst requests, six model turns and four queries per request. Overall loop deadline 180 seconds; each model request timeout at most 60 seconds.
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
