# Keeps normalized rows and extra uploaded columns available to future questions by dataset ID.
"""Bounded process-local datasets for the analyst; no uploads are written to disk."""
import os
import secrets
from backend.request_scope import OWNER
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
# A cache entry carries the queryable frame, source-column names, metadata, size, and creation time.
class Dataset:
    frame: pd.DataFrame
    metadata: dict
    source_columns: dict
    size: int
    created: float
    owner: str


class DatasetCache:
    # Set memory/count/age limits and protect shared state from concurrent HTTP requests.
    def __init__(self, max_bytes=None, max_items=4, ttl=3600):
        self.max_bytes = max_bytes or (32 if os.getenv("APP_ENV") == "production" else 128) * 1024 * 1024
        self.max_items, self.ttl = max_items, ttl
        self._items = OrderedDict()
        self._lock = threading.Lock()

    # Combine validated canonical fields with unmapped source fields, then issue an opaque dataset ID.
    def put(self, source, result, mapping):
        frame = pd.DataFrame(result['rows'])
        # Extra uploaded fields remain queryable without changing dashboard records.
        extras = {}
        for i, column in enumerate(source.columns):
            if column not in mapping.values():
                key = str(column) if str(column).casefold() not in {str(c).casefold() for c in frame.columns} else f'source_{i}'
                values = source[column].reset_index(drop=True)
                # Preserve raw values, including currency/date strings; no silent coercion.
                frame[key] = values.where(values.notna(), None).map(lambda v: None if v is None else str(v))
                extras[key] = column
        # Estimate DataFrame memory and reject a single upload larger than the cache budget.
        size = int(frame.memory_usage(index=True, deep=True).sum())
        if size > self.max_bytes:
            raise ValueError('This dataset is too large for AI analysis memory. Calculated answers still work.')
        metadata = {key: result[key] for key in ('filename', 'business', 'currency', 'capabilities', 'warnings')}
        entry = Dataset(frame, metadata, extras, size, time.monotonic(), OWNER.get())
        key = secrets.token_urlsafe(24)
        # Expire old datasets and evict least-recently-used entries before storing this upload.
        with self._lock:
            self._expire()
            while self._items and (len(self._items) >= self.max_items or sum(d.size for d in self._items.values()) + size > self.max_bytes):
                self._items.popitem(last=False)
            self._items[key] = entry
        return key

    # Remove entries older than their lifetime; uploads are not saved to disk.
    def _expire(self):
        for key, entry in list(self._items.items()):
            if time.monotonic() - entry.created > self.ttl:
                del self._items[key]

    # Look up an existing dataset and explain how to recover if it expired or the server restarted.
    def get(self, key):
        with self._lock:
            self._expire()
            entry = self._items.get(key) if isinstance(key, str) else None
            # Knowing a dataset ID is insufficient: the authenticated request must own that cache entry.
            if entry is None or entry.owner != OWNER.get():
                raise ValueError('The AI dataset expired or the server restarted. Build the dashboard again to reload it.')
            self._items.move_to_end(key)
            return entry

    def discard_owner(self, prefix):
        # Prefixes let logout clear one browser, while account deletion clears every session for that user.
        with self._lock:
            for key, entry in list(self._items.items()):
                if entry.owner.startswith(prefix):
                    del self._items[key]


# All requests in this server process share this bounded dataset cache.
DATASETS = DatasetCache()


def select_rows(dataset, filters):
    """Apply the same filters as the browser BEFORE exposing rows to the analyst."""
    if not isinstance(filters, dict) or set(filters) - {'from', 'to', 'category', 'product', 'weekday', 'period'}:
        raise ValueError('Invalid dashboard filters.')
    if any(not isinstance(value, str) or len(value) > 1000 for value in filters.values()):
        raise ValueError('Invalid dashboard filter value.')
    frame, capabilities = dataset.frame, dataset.metadata['capabilities']
    keep = pd.Series(True, index=frame.index)
    # Apply inclusive date boundaries using normalized ISO dates.
    if capabilities['Date']:
        for key, operation in (('from', 'ge'), ('to', 'le')):
            if filters.get(key):
                from datetime import date
                date.fromisoformat(filters[key])
                keep &= getattr(frame['Date'], operation)(filters[key])
    # Match product/category labels exactly, just as the browser filters do.
    for key, field in (('category', 'Category'), ('product', 'Product_Name')):
        if filters.get(key):
            keep &= frame[field] == filters[key]
    # Convert Python weekday numbering to the browser convention: Sunday is zero.
    if filters.get('weekday'):
        if not capabilities['Date'] or filters['weekday'] not in [str(i) for i in range(7)]:
            raise ValueError('Weekday filtering requires valid dates.')
        from datetime import date
        keep &= frame['Date'].map(lambda value: str((date.fromisoformat(value).weekday() + 1) % 7)) == filters['weekday']
    # Use the same hour ranges as dashboard-utils.js period().
    if filters.get('period'):
        ranges = {'overnight': (0, 5), 'morning': (6, 11), 'afternoon': (12, 17), 'evening': (18, 23)}
        if not capabilities['Hour'] or filters['period'] not in ranges:
            raise ValueError('Time-of-day filtering requires valid hours.')
        keep &= frame['Hour'].between(*ranges[filters['period']])
    selected = frame.loc[keep].copy()
    # Synthesized display labels and invalid order IDs are not analytical evidence.
    for capability, columns in {'product':['Product_Name'], 'category':['Category'], 'weather':['Weather'],
                                'employee':['Employee_Name'], 'orders':['Order_Key', 'Transaction_ID']}.items():
        if not capabilities[capability]:
            selected.drop(columns=columns, errors='ignore', inplace=True)
    return selected
