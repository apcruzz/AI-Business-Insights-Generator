# Stores recent exchanges in memory; used by analyst_agent to resolve follow-up questions.
"""Bounded, local conversation memory, isolated by dataset, filters and model."""
from backend.request_scope import OWNER
from collections import OrderedDict
import copy
import json
import secrets
import threading
import time


class ConversationCache:
    # Cap conversations and guard shared cache operations with a lock.
    def __init__(self, ttl=3600, max_items=32):
        self.ttl, self.max_items = ttl, max_items
        self.items = OrderedDict()
        self.lock = threading.Lock()

    # Resume only when dataset, filters, and model match; otherwise create an empty conversation.
    def open(self, token, dataset_id, filters, model):
        scope = (OWNER.get(), dataset_id, json.dumps(filters, sort_keys=True), model)
        with self.lock:
            now = time.monotonic()
            # Expire idle conversations before attempting to reuse a token.
            for key in list(self.items):
                if now - self.items[key]['updated'] > self.ttl:
                    del self.items[key]
            if isinstance(token, str) and token in self.items and self.items[token]['scope'] == scope:
                entry = self.items[token]
                entry['updated'] = now
                self.items.move_to_end(token)
                # Give this request a snapshot so later cache changes do not modify its history.
                return token, copy.deepcopy(entry['turns'])
            token = secrets.token_urlsafe(24)
            self.items[token] = {'scope': scope, 'updated': now, 'turns': []}
            while len(self.items) > self.max_items:
                self.items.popitem(last=False)
            return token, []

    # Save a completed exchange with its evidence, keeping at most four recent turns.
    def append(self, token, question, answer, evidence):
        with self.lock:
            if token in self.items and self.items[token]['scope'][0] == OWNER.get():
                entry = self.items[token]
                entry['turns'].append({'question': question, 'answer': answer, 'evidence': evidence})
                entry['turns'] = entry['turns'][-4:]
                # Trim older exchanges to keep subsequent model prompts manageable.
                while len(json.dumps(entry['turns'])) > 18000 and len(entry['turns']) > 1:
                    entry['turns'].pop(0)
                # Large calculations need not fill the conversational prompt.
                if len(json.dumps(entry['turns'])) > 18000:
                    entry['turns'][-1]['evidence'] = evidence[-1:]
                entry['updated'] = time.monotonic()

    def discard_owner(self, prefix):
        with self.lock:
            for key, entry in list(self.items.items()):
                if entry['scope'][0].startswith(prefix):
                    del self.items[key]


# One cache is shared by analyst requests until the Python process exits.
CONVERSATIONS = ConversationCache()
