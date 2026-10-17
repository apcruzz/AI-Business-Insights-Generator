# Called by /api/profile and /api/analyze; returns a DataFrame, filename, and worksheet names.
"""Read uploaded/sample CSV and spreadsheet files into pandas."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pandas as pd

from backend.config import SAMPLES, UPLOAD_LIMIT_BYTES


def frame_from_payload(payload):
    """Load a sample/uploaded CSV or spreadsheet into a pandas DataFrame."""
    name = str(payload.get("filename", ""))
    if payload.get("sample"):
        # Samples are read from the local data/samples folder by filename only.
        allowed = {p.name: p for p in SAMPLES.glob("*.csv")}
        if payload["sample"] not in allowed:
            raise ValueError("Unknown sample dataset.")
        source = allowed[payload["sample"]]
        raw, name = source.read_bytes(), source.name
    # Decode the browser upload into bytes in memory; malformed base64 becomes a user-facing error.
    else:
        try:
            raw = base64.b64decode(payload.get("file", ""), validate=True)
        except Exception:
            raise ValueError("The upload could not be read.") from None
    if not raw or len(raw) > UPLOAD_LIMIT_BYTES:
        raise ValueError("Choose a nonempty file smaller than 20 MB.")
    suffix = Path(name).suffix.lower()
    sheets = []
    # Excel files can contain several sheets, so the UI lets the user choose one.
    if suffix in {".xlsx", ".xls"}:
        book = pd.ExcelFile(io.BytesIO(raw))
        sheets = book.sheet_names
        sheet = payload.get("sheet") or sheets[0]
        if sheet not in sheets:
            raise ValueError("Choose a worksheet from this workbook.")
        frame = book.parse(sheet, dtype=object)
    elif suffix == ".csv":
        # Try common encodings and let pandas infer the delimiter.
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                frame = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=None, engine="python", dtype=object)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Save the CSV with UTF-8 encoding and try again.")
    else:
        raise ValueError("Upload a CSV, XLSX, or XLS file.")
    # Remove empty rows and validate table size and unique headers before mapping.
    frame = frame.dropna(how="all").reset_index(drop=True)
    frame.columns = [str(c).strip() for c in frame.columns]
    if not len(frame) or len(frame) > 100000 or len(frame.columns) > 200:
        raise ValueError("Use a data table with 1–100,000 rows and at most 200 columns.")
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("Column names must be unique.")
    return frame, name, sheets
