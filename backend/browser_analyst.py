"""Bounded, request-owned analysis runs. Only model text crosses back from the browser."""
from collections import OrderedDict
import json
import secrets
import threading
import time

from backend.analyst_agent import AnalystRun
from backend.analyst_datasets import DATASETS
from backend.ai_providers import resolve_model
from backend.request_scope import OWNER


class BrowserRuns:
    def __init__(self, max_items=4, ttl=600):
        self.items = OrderedDict()
        self.lock = threading.Lock()
        self.max_items, self.ttl = max_items, ttl

    def _expire(self):
        for key in list(self.items):
            if time.monotonic() >= self.items[key]['run'].deadline:
                del self.items[key]

    def _packet(self, key, entry):
        # Send the browser a model prompt or a finished result; the analysis state stays in this cache.
        request = entry['run'].inference()
        if request is None:
            self.items.pop(key, None)
            return {'status': 'complete', 'result': entry['run'].result}
        if len(json.dumps(request).encode()) > 128 * 1024:
            self.items.pop(key, None)
            raise ValueError('This local analysis context is too large. Use fewer columns or a new conversation.')
        entry['step'] = secrets.token_urlsafe(24)
        # A new one-use token is issued for every step, so stale browser replies cannot advance a run twice.
        return {'status': 'model_required', 'runId': key, 'step': entry['step'], 'inference': request}

    def start(self, payload):
        # An explicit provider prevents accidental cloud dispatch through this path.
        if payload.get('provider') != 'browser_ollama':
            raise ValueError('Choose Local Ollama via browser.')
        client = resolve_model('browser_ollama', payload.get('model'))
        with self.lock:
            self._expire()
            owner = OWNER.get()
            # One pending question per session; replacing it frees prompt memory.
            for key in list(self.items):
                if self.items[key]['owner'] == owner:
                    del self.items[key]
            run = AnalystRun(payload, client, lifetime=self.ttl)
            key = secrets.token_urlsafe(24)
            entry = {'owner': owner, 'run': run}
            self.items[key] = entry
            while len(self.items) > self.max_items:
                self.items.popitem(last=False)
            return self._packet(key, entry)

    def advance(self, payload):
        key = payload.get('runId')
        with self.lock:
            self._expire()
            entry = self.items.get(key) if isinstance(key, str) else None
            if entry is None or entry['owner'] != OWNER.get():
                raise ValueError('This local analysis expired or is unavailable. Ask the question again.')
            DATASETS.get(entry['run'].dataset_id)
            # Ownership/expiry is checked again between model turns, not just when the question begins.
            step = payload.get('step')
            if not isinstance(step, str) or not secrets.compare_digest(step, entry['step']):
                raise ValueError('This analysis step was already used or is out of order.')
            # Consume once even if a model reply is malformed. Clients cannot replay SQL steps.
            entry['step'] = ''
            entry['run'].accept(payload.get('output'))
            return self._packet(key, entry)

    def cancel(self, payload):
        # Treat cancellation as idempotent, while refusing to delete another session's pending run.
        with self.lock:
            key = payload.get('runId')
            if isinstance(key, str) and key in self.items and self.items[key]['owner'] == OWNER.get():
                del self.items[key]
            return {'status': 'cancelled'}

    def discard_owner(self, prefix):
        with self.lock:
            for key, entry in list(self.items.items()):
                if entry['owner'].startswith(prefix):
                    del self.items[key]


BROWSER_RUNS = BrowserRuns()
