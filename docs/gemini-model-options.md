# Gemini Flash-Lite option

The model dropdown now offers **Gemini 3.5 Flash-Lite · Google (cloud)** and
**Gemini 3.8 Flash · Google (cloud)**. Both use the same server-side
`GEMINI_API_KEY`. Groq, local Ollama, browser Ollama and calculated answers
remain available. There is no automatic provider or model fallback.

Flash-Lite completed the user's tiny comparison request in 891 ms. That result
establishes a successful small generation request for that model and project
at that time. It does not establish the response time, correctness or success
of a complete business overview or conversation.

## Use Flash-Lite

Stop and restart the Python backend after installing this update, using the
existing hidden-key startup command in `START_HERE.txt`. Open a fresh dashboard
at http://127.0.0.1:8765, load the file again and review the mapping. The team's
prototype stores uploaded datasets in Python memory, so restarting clears
those dataset references.

Under **AI overview and recommendations → AI provider / answer mode**, select
**Gemini 3.5 Flash-Lite · Google (cloud)**. If the option is missing, open
**AI settings → Refresh AI options**. The overview starts after explicit model
selection. Ask a follow-up in **Business assistant** when it finishes.

The existing React bundle reads model choices from the backend. This update
requires no frontend source changes, frontend rebuild or dependency changes.

Changing models resets the visible chat and uses a separate overview and
conversation scope. A failure stays attributed to the selected model; it does
not silently send the question to a different model or provider.

## What remains checked

Both Gemini models use the same backend-owned overview prompt, filtered-row
calculations, restricted read-only query tool, numeric consistency checks,
supporting evidence and scoped conversation storage. These checks reduce
unsupported answers; they do not prove every interpretation or recommendation.

This update also retains the Date repair. Backend template wording cannot
require an unmapped source field in every overview calculation. Date coverage,
profit and orders are calculated from reviewed normalized fields, while
questions explicitly naming raw source columns retain their existing checks.

The Gemini request uses supported sampling/candidate defaults and keeps the
structured action schema and low thinking level for both models. Timeouts,
certificate failures, DNS errors and other connection failures now have
different fixed messages. Provider error bodies and credentials remain hidden.

## Optional live check with fictional data

In a terminal where `GEMINI_API_KEY` is set, run from the project folder:

```powershell
& .\.venv\Scripts\python.exe -B -m scripts.check_gemini --model gemini-3.5-flash-lite
```

This runs the full overview engine on fictional data and can make multiple
generation requests within the existing bounded analyst loop. It uses API
project quota and sends no uploaded business files. It is optional and does
not run during installation or the normal unit tests.

References: [Flash-Lite model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
[thinking levels](https://ai.google.dev/gemini-api/docs/thinking),
[request settings](https://ai.google.dev/gemini-api/docs/troubleshooting).
