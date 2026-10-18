# Shared settings imported by the loader, HTTP server, and Ollama transport.
"""Shared backend configuration for local paths and service limits."""
from __future__ import annotations

from pathlib import Path

# Resolve paths from this file, so launching from another directory still finds assets.
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SAMPLES = ROOT / "data" / "samples"

# Limit decoded uploads and keep Ollama requests on this computer.
UPLOAD_LIMIT_BYTES = 20 * 1024 * 1024
OLLAMA_URL = "http://127.0.0.1:11434"

# Groq is opt-in; its API key is read only by the backend from the process environment.
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
