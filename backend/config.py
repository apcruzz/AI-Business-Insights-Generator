"""Shared backend configuration for local paths and service limits."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SAMPLES = ROOT / "data" / "samples"

UPLOAD_LIMIT_BYTES = 20 * 1024 * 1024
OLLAMA_URL = "http://127.0.0.1:11434"
