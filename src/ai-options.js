// Keep provider identity separate from the model name used in API requests.
export function answerOptions(status) {
  return [
    {value: "", label: "Calculated answers", available: true, provider: null, model: ""},
    ...(status.options || []).map(option => ({
      ...option,
      value: `${option.provider}:${option.model}`,
      label: option.label + (option.available ? "" : " — API key required"),
    })),
  ];
}

// Preserve explicit choices on refresh. Only the first discovery may prefer a local model.
export function chooseAnswerMode(options, current, initial = false) {
  if (!initial || current) {
    return options.find(option => option.value === current && option.available)?.value || "";
  }
  const local = options.filter(option => option.provider === "ollama" && option.available);
  return (local.find(option => option.model === "llama3:latest") ||
    local.find(option => ["llama3.2", "llama3.2:latest"].includes(option.model)) ||
    local.find(option => option.model.startsWith("llama3.2:")))?.value || "";
}

// Explain where data goes at the point where the user chooses the model.
export function answerModeNotice(option, groqConfigured, hosted = false, geminiConfigured = false) {
  if (option?.provider === "browser_ollama") {
    return "Local Ollama via this browser: AI inference runs on your computer. Uploads, authorized SQL calculations and conversation state still use the dashboard server" + (hosted ? " on Render" : "") + ". Questions, column samples and verified results are sent to your local model. No AI inference requests go to cloud providers in this mode.";
  }
  if (option?.provider === "gemini") {
    return "Google Gemini cloud: selecting this mode generates an initial overview in Business assistant. New data, filters or a different Gemini model use a separate overview; completed overviews are reused in this session. The overview request, questions, recent conversation, column names, sample values, and calculation results are sent to Google. Calculations use the current filters. Google API project quotas and terms apply; a Gemini app subscription does not configure API access.";
  }
  if (option?.provider === "groq") {
    return "Groq cloud: your question, recent conversation, column names, sample values, and calculation results are sent to Groq. Calculations can use all rows matching your filters. Internet is required; Groq account limits apply.";
  }
  const local = option?.provider === "ollama"
    ? "Ollama analyzes your uploaded data on this computer."
    : (hosted ? "Calculated answers run in your browser using dashboard data processed on Render." : "Calculated answers use your mapped dashboard data on this computer.");
  return local + (geminiConfigured ? " Gemini is available when you select it." : " To enable Gemini, set GEMINI_API_KEY on the Python backend and restart it.") + (groqConfigured
    ? " GPT-OSS 120B is also available through Groq cloud when you select it."
    : " To enable GPT-OSS 120B through Groq cloud, configure the backend API key using the README setup steps.");
}
