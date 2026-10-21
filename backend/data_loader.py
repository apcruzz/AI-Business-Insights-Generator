# Called by /api/profile and /api/analyze; returns a DataFrame, filename, and worksheet names.
"""Read uploaded/sample CSV and spreadsheet files into pandas."""
from __future__ import annotations

import base64
import csv
import io
import os
import zipfile
from defusedxml import ElementTree
from pathlib import Path

import pandas as pd

from backend.config import SAMPLES, UPLOAD_LIMIT_BYTES


def frame_from_payload(payload):
    """Load a sample/uploaded CSV or spreadsheet into a pandas DataFrame."""
    if not isinstance(payload, dict):
        raise ValueError("Submit a JSON object.")
    hosted = os.getenv("APP_ENV") == "production"
    upload_limit = min(UPLOAD_LIMIT_BYTES, 2 * 1024 * 1024) if hosted else UPLOAD_LIMIT_BYTES
    max_rows, max_columns = (10000, 60) if hosted else (100000, 200)
    name = str(payload.get("filename", ""))
    if len(name) > 255:
        raise ValueError("Filename is too long.")
    if payload.get("sample"):
        # Samples are read from the local data/samples folder by filename only.
        allowed = {p.name: p for p in SAMPLES.glob("*.csv")}
        if payload["sample"] not in allowed:
            raise ValueError("Unknown sample dataset.")
        if hosted and not payload["sample"].endswith("_Demo.csv"):
            raise ValueError("Only fictional demo samples are available on the hosted service.")
        source = allowed[payload["sample"]]
        raw, name = source.read_bytes(), source.name
    # Decode the browser upload into bytes in memory; malformed base64 becomes a user-facing error.
    else:
        try:
            raw = base64.b64decode(payload.get("file", ""), validate=True)
        except Exception:
            raise ValueError("The upload could not be read.") from None
    if not raw or len(raw) > upload_limit:
        raise ValueError(f"Choose a nonempty file no larger than {upload_limit // (1024 * 1024)} MB.")
    suffix = Path(name).suffix.lower()
    sheets = []
    # Excel files can contain several sheets, so the UI lets the user choose one.
    if suffix in {".xlsx", ".xls"}:
        if suffix == '.xlsx':
            # Bound ZIP expansion before openpyxl sees shared strings or workbook XML.
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    infos = archive.infolist()
                    if len(infos) > 256 or sum(i.file_size for i in infos) > (12 if hosted else 100) * 1024 * 1024:
                        raise ValueError("Workbook expands beyond the allowed size.")
                    if any(i.flag_bits & 1 for i in infos):
                        raise ValueError("Encrypted workbooks are unsupported.")
                    # Inspect dimensions by streaming actual cell records, not trusting dimension metadata.
                    if hosted:
                        for info in infos:
                            if info.filename.startswith('xl/worksheets/') and info.filename.endswith('.xml'):
                                rows = cells = 0
                                with archive.open(info) as xml:
                                    for event, element in ElementTree.iterparse(xml, events=('end',)):
                                        tag = element.tag.rsplit('}', 1)[-1]
                                        if tag == 'c':
                                            ref = element.attrib.get('r', '')
                                            column = 0
                                            for char in ref:
                                                if char.isalpha():
                                                    column = column * 26 + ord(char.upper()) - 64
                                            if column > max_columns:
                                                raise ValueError('Use at most 60 worksheet columns.')
                                            cells += 1
                                            if cells > max_columns:
                                                raise ValueError("Use at most 60 columns per worksheet.")
                                        elif tag == 'row':
                                            rows += 1
                                            cells = 0
                                            if rows > max_rows + 1:
                                                raise ValueError("Use at most 10,000 rows per worksheet.")
                                        element.clear()
            except zipfile.BadZipFile:
                raise ValueError("Invalid XLSX workbook.") from None
        if suffix == '.xls' and hosted:
            import xlrd
            legacy = xlrd.open_workbook(file_contents=raw, on_demand=True)
            try:
                for sheet_index in range(legacy.nsheets):
                    sheet_info = legacy.sheet_by_index(sheet_index)
                    if sheet_info.nrows > max_rows + 1 or sheet_info.ncols > max_columns:
                        raise ValueError("Use at most 10,000 rows and 60 columns per worksheet.")
                    legacy.unload_sheet(sheet_index)
            finally:
                legacy.release_resources()
        book = pd.ExcelFile(io.BytesIO(raw))
        sheets = book.sheet_names
        sheet = payload.get("sheet") or sheets[0]
        if sheet not in sheets:
            raise ValueError("Choose a worksheet from this workbook.")
        frame = book.parse(sheet, dtype=object, nrows=max_rows + 1)
        book.close()
    elif suffix == ".csv":
        # Try common encodings and let pandas infer the delimiter.
        csv_separator = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                if hosted:
                    # Reject wide/long tables before pandas allocates a DataFrame.
                    text = raw.decode(encoding)
                    try:
                        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t|:')
                    except csv.Error:
                        dialect = csv.excel
                    csv_separator = dialect.delimiter
                    rows = csv.reader(io.StringIO(text), dialect)
                    nonempty = 0
                    for values in rows:
                        if not values:
                            continue
                        nonempty += 1
                        if len(values) > max_columns or nonempty > max_rows + 1:
                            raise ValueError('Use at most 10,000 rows and 60 columns.')
                        if nonempty == 1 and len({v.strip() for v in values}) != len(values):
                            raise ValueError('Column names must be unique.')
                frame = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=csv_separator, engine="python", dtype=object, nrows=max_rows + 1)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Save the CSV with UTF-8 encoding and try again.")
    else:
        raise ValueError("Upload a CSV, XLSX, or XLS file.")
    # Remove empty rows and validate table size and unique headers before mapping.
    if len(frame) > max_rows:
        raise ValueError(f"Use at most {max_rows:,} rows.")
    frame = frame.dropna(how="all").reset_index(drop=True)
    frame.columns = [str(c).strip() for c in frame.columns]
    if not len(frame) or len(frame) > max_rows or len(frame.columns) > max_columns:
        raise ValueError(f"Use a data table with 1–{max_rows:,} rows and at most {max_columns} columns.")
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError("Column names must be unique.")
    if hosted and int(frame.memory_usage(index=True, deep=True).sum()) > 12 * 1024 * 1024:
        raise ValueError("Table needs too much memory for the hosted demo. Use fewer rows or columns.")
    return frame, name, sheets
