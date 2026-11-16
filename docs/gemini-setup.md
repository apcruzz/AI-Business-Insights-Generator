# Gemini overview in the existing business assistant

The dashboard markup and styles match the team's main at `451b54e`.
Google Gemini is another answer mode in the existing Business assistant dropdown.
No new overview panel, charts, navigation or layout is added. After a dataset
is loaded, selecting Gemini generates an automatic overview as the first
assistant message in the existing conversation. Press **Ask** for follow-ups.
Groq, server Ollama, browser Ollama and Calculated answers remain available.

## Windows PowerShell

Install the merged requirements and build as described in the project README.
Stop an older Python backend with Ctrl+C before restarting it. Run from the
repository root:

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

Open **http://127.0.0.1:8765**. Load a fictional sample or your file, review the
mapping, and open Business assistant. On smaller screens use the existing
Assistant tab. Choose **Gemini 3.5 Flash-Lite · Google (cloud)** and ask a question.
**Gemini 3.8 Flash · Google (cloud)** remains an alternative model choice.
The automatic overview, questions, answers and supporting calculations use the
existing conversation UI. The overview is an assistant message; it does not
invent a question from you.

If Gemini is unavailable in the dropdown, use **AI settings → Refresh AI options**
after restarting Python with the key. The Python backend must hold the key;
the frontend does not load it. The backend does not automatically load `.env`.

For Vite development, keep Python running on port 8765 and run `npm.cmd run dev`
in a second terminal. The built app can be served by Python directly.

## Data and calculations

Gemini receives the question, relevant recent conversation, column names/sample
values and calculation results. Calculations operate on all rows matching the
current filters through the existing restricted read-only query engine. Missing
data, owner/session scopes and provider-specific conversations keep the existing
rules. Numeric checks reduce unsupported figures but do not prove every answer.

New data, filters or a different Gemini model use a separate overview and reset
the follow-up conversation. Completed overviews are cached in this browser
session, so returning to the same selection reuses its overview. Chart changes
and page navigation do not generate another overview. Fast filter changes are
debounced, and late replies from a previous selection are ignored.

An overview failure is shown in the existing assistant conversation. You can
still ask a question, or use the existing **New conversation** button to retry
that failed overview. Errors do not trigger automatic retries or provider
fallback. Starting a new conversation after a successful overview reuses the
overview as context for a fresh chat. Other answer providers keep manual Ask
behavior. Review supporting calculations.

API project quotas, model access and billing apply independently of a Gemini app
subscription. Keep keys in the Python process or deployment secrets, outside
frontend variables and source control. Unit tests use fictional fixtures and
mock providers; they do not make live cloud inference requests.
