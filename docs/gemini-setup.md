# Gemini overview and chat

This update adds Google Gemini to the team's Python/React prototype. Groq,
server Ollama, browser Ollama and calculated answers remain available. There
are no database migrations and no new third-party dependencies.

## Windows PowerShell

Run these commands from the team's cloned repository folder, where `app.py`,
`requirements.txt` and `package.json` are located. Use your actual clone path.
Stop an older Python backend with Ctrl+C before restarting it.

Install the existing project dependencies and build the frontend:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
npm.cmd run build
```

Keep this PowerShell window open while running the app. Paste the Gemini API
key only at the hidden input prompt, without quotes. Do not put the key in
the command, source files, browser code, `VITE_` variables, GitHub or chat.

```powershell
& {
    $previousGeminiKey = $env:GEMINI_API_KEY
    $secureGeminiKey = Read-Host 'Paste Gemini API key only (hidden)' -AsSecureString
    try {
        $env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $secureGeminiKey).Password.Trim()
        & .\.venv\Scripts\python.exe app.py --no-browser
    } finally {
        if ($null -eq $previousGeminiKey) {
            Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
        } else {
            $env:GEMINI_API_KEY = $previousGeminiKey
        }
        $secureGeminiKey.Dispose()
        $previousGeminiKey = $null
    }
}
```

Open **http://127.0.0.1:8765**. Upload a file or choose a sample, review the
mapping, confirm columns, then load the dashboard. Under **AI overview and
recommendations**, select **Gemini 3.8 Flash · Google (cloud)**. That explicit
selection generates the overview automatically. Ask follow-up questions in
Business assistant below it.

If Gemini says “API key required,” use **AI settings → Refresh AI options**.
If it remains unavailable, restart the **Python backend** in the terminal
holding the key. Running only `npm.cmd run dev` starts the Vite frontend;
it does not start Python or configure its environment. For frontend development,
keep Python running on port 8765 and run `npm.cmd run dev` in a second terminal.

The backend does not automatically load `.env` files. A Gemini app subscription
does not provide this server's API key or determine the API project's limits.
This integration uses `gemini-3.8-flash`; API project model access, quotas and
billing still apply.

## What generates an overview

The Python server owns the prompt and calculates a bounded overview packet
over **all rows matching the selected filters**. It includes net sales, recorded
date coverage, orders when valid IDs exist, gross profit and weighted margin
when available, leading products/categories, and recorded monthly totals.
Missing values remain unavailable. Monthly totals can represent partial months.

The same restricted read-only calculation engine checks Gemini and the other
AI providers. A numeric consistency check reduces unsupported figures but does
not prove the relevance or truth of every sentence. Review the visible
supporting calculations before making a business decision. “At a glance”
remains a separate set of calculated cards.

The current dataset, filters, provider and model define each overview. The page
reuses completed overviews in a bounded in-memory cache. Chart appearance and
navigation do not issue another overview request. Rapid filter changes are
debounced. Failures show a provider-specific message and **Retry overview**;
there is no automatic provider fallback or repeated network retry. Switching
selection ignores late answers; a request already sent can still consume quota.
Reloading the page clears the cache.

Follow-up chat receives a copy of the matching initial overview's context in a
separate conversation. New conversations, other datasets, filters, providers
and user sessions do not share chat history.

## Data sharing and credentials

Selecting Gemini sends the overview request, questions, recent conversation,
dataset metadata, column names, small sample values and calculation results
to Google. Full source files are not sent wholesale, but sample values and
aggregate labels can still contain sensitive information. Use only data that
you are authorized to share with the selected provider. Server-only
`GEMINI_API_KEY` is never returned to the browser. Existing `GROQ_API_KEY`
configuration remains separate.

For the existing hosted demo, add `GEMINI_API_KEY` as a secret environment
variable on the backend service and redeploy that service. It belongs in the
backend environment, never in the frontend build environment. The existing
authentication, origin checks and AI rate limits also cover `/api/overview`.

## Verification

```powershell
npm.cmd test
npm.cmd run build
```

The normal test suite uses synthetic data and mocks all cloud responses.
An optional **live** connection check uses fictional data and consumes Gemini
API quota. Run it in a terminal where `GEMINI_API_KEY` is set:

```powershell
& .\.venv\Scripts\python.exe -B -m scripts.check_gemini
```

Quota errors, unavailable models, temporary service failures, invalid responses
and timeouts are distinct from import failures. An unavailable AI provider does
not remove the calculated dashboard or change provider automatically.

References: [Gemini models](https://ai.google.dev/gemini-api/docs/models),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output),
[generateContent API](https://ai.google.dev/api/generate-content).
