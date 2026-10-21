"""Shared dashboard API dispatch for local and production servers."""
import json
from backend.data_loader import frame_from_payload
from backend.normalizer import normalize, suggest_mapping
from backend.ollama_client import explain
from backend.ai_providers import available_models
from backend.groq_client import GroqError
from backend.analyst_datasets import DATASETS
from backend.analyst_agent import analyze_question
from backend.browser_analyst import BROWSER_RUNS


def dispatch(path, payload):
    if path == "/api/ollama-start":
        return BROWSER_RUNS.start(payload)
    elif path == "/api/ollama-step":
        return BROWSER_RUNS.advance(payload)
    elif path == "/api/ollama-cancel":
        return BROWSER_RUNS.cancel(payload)
    elif path == "/api/profile":
        # Inspect columns and suggest mappings before analysis.
        frame, name, sheets = frame_from_payload(payload)
        return (
            {
                "filename": name,
                "rows": len(frame),
                "columns": frame.columns.tolist(),
                "sheets": sheets,
                "mapping": suggest_mapping(frame.columns),
                "preview": json.loads(frame.head(5).to_json(orient="records")),
            }
        )
    elif path == "/api/analyze":
        # Normalize the selected sheet/file into dashboard-ready records.
        frame, name, _ = frame_from_payload(payload)
        result = normalize(
            frame,
            payload.get("mapping"),
            payload.get("business", "Other business"),
            payload.get("currency", "USD"),
            payload.get("dateOrder", "month"),
            payload.get("decimal", "dot"),
            line_total_basis=payload.get("lineTotalBasis"),
            modifier_basis=payload.get("modifierBasis", "line"),
        )
        result["filename"] = name
        # Register rows for later questions; a cache limit must not prevent ordinary dashboard use.
        try:
            result["datasetId"] = DATASETS.put(frame, result, payload.get("mapping", {}))
        except ValueError as error:
            result["analystNote"] = str(error)
        return (result)
    # Pass the question, dataset ID, filters, and conversation ID to the SQL analyst.
    elif path == "/api/analyst":
        return (analyze_question(payload))
    elif path == "/api/explain":
        # Optional local AI explanation through Ollama.
        return (explain(payload))
    else:
        return ({"error": "Not found"}, 404)
