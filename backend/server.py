# Connects browser requests to file loading, normalization, dataset caching, and local AI analysis.
"""Local HTTP server for the dashboard browser UI."""
from __future__ import annotations

import argparse
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.config import DIST, ROOT, UPLOAD_LIMIT_BYTES
from backend.data_loader import frame_from_payload
from backend.normalizer import normalize, suggest_mapping
from backend.ollama_client import explain, local_models
from backend.analyst_datasets import DATASETS
from backend.analyst_agent import analyze_question

# One process-wide request token is fetched by dashboard.js before it posts data.
TOKEN = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    """Small local HTTP API for the browser UI."""

    def send_json(self, result, status=200):
        """Send one JSON response back to the browser."""
        body = json.dumps(result, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Serve dashboard files and small read-only API endpoints."""
        # Serve the static dashboard files and lightweight local API endpoints.
        if self.path == "/api/session":
            self.send_json({"token": TOKEN})
        elif self.path == "/api/models":
            try:
                self.send_json({"models": local_models()})
            except Exception:
                self.send_json({"models": [], "message": "Ollama is not running. Calculated insights still work."})
        elif self.path.split("?")[0] == "/" or self.path.split("?")[0] == "/index.html":
            # In production, serve the Vite build. Before building, fall back to the source index.
            source = DIST / "index.html" if (DIST / "index.html").exists() else ROOT / "index.html"
            raw = source.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.split("?")[0].startswith("/assets/") and DIST.exists():
            # Built JavaScript and CSS files live under dist/assets.
            asset = (DIST / self.path.split("?")[0].lstrip("/")).resolve()
            if DIST.resolve() not in asset.parents or not asset.exists():
                self.send_json({"error": "Not found"}, 404)
                return
            raw = asset.read_bytes()
            suffix = asset.suffix.lower()
            content_type = "text/javascript" if suffix == ".js" else "text/css" if suffix == ".css" else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle uploaded data, dashboard analysis, and AI explanations."""
        # All POST actions require the per-process token from /api/session.
        try:
            if self.headers.get("X-Dashboard-Token") != TOKEN:
                raise ValueError("Reload this local dashboard before uploading.")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > UPLOAD_LIMIT_BYTES * 1.5:
                raise ValueError("Upload size exceeds the 20 MB file limit.")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/profile":
                # Inspect columns and suggest mappings before analysis.
                frame, name, sheets = frame_from_payload(payload)
                self.send_json(
                    {
                        "filename": name,
                        "rows": len(frame),
                        "columns": frame.columns.tolist(),
                        "sheets": sheets,
                        "mapping": suggest_mapping(frame.columns),
                        "preview": json.loads(frame.head(5).to_json(orient="records")),
                    }
                )
            elif self.path == "/api/analyze":
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
                self.send_json(result)
            # Pass the question, dataset ID, filters, and conversation ID to the SQL analyst.
            elif self.path == "/api/analyst":
                self.send_json(analyze_question(payload))
            elif self.path == "/api/explain":
                # Optional local AI explanation through Ollama.
                self.send_json(explain(payload))
            else:
                self.send_json({"error": "Not found"}, 404)
        # Return expected validation details, but hide unexpected internal exceptions from the browser.
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, ValueError)
                else "The file or local model could not be read. Check the file format, selected worksheet, and local model setup."
            )
            self.send_json({"error": message}, 400)

    def log_message(self, format, *args):
        """Silence default request logging for privacy and cleaner terminal output."""
        # Do not log uploaded data or questions.
        pass


def main():
    """Start the dashboard as a local-only website on this computer."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    # Bind only to loopback; separate request threads allow the UI to respond during model work.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"Free Business Dashboard: http://127.0.0.1:{args.port}\n"
        "No paid APIs. Uploads stay in memory on this computer. Press Ctrl+C to stop.",
        flush=True,
    )
    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
