"""Gemini routes after the account/UI merge. Synthetic fixtures; no live AI calls."""
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backend import gemini_client
from backend.analyst_conversations import ConversationCache
from backend.analyst_datasets import DatasetCache
from backend.normalizer import normalize
from backend.request_scope import OWNER
from backend.server import Handler, TOKEN

MODEL = 'gemini-3.5-flash-lite'


def answer(text='Net sales are 30. Recommend reviewing the recorded sales.'):
    return json.dumps({'action': 'answer', 'sql': '', 'answer': text})


def calculated_reply(_model, messages, **_options):
    if any(message['content'].startswith(('Verified initial overview calculations', 'Tool result')) for message in messages):
        return answer()
    return json.dumps({'action': 'query', 'sql': 'SELECT ROUND(SUM(Net_Sales), 2) AS net_sales FROM sales', 'answer': ''})


class LocalMergedRouteTests(unittest.TestCase):
    """Exercise the real local handler without opening a network socket."""
    def setUp(self):
        self.cache = DatasetCache()
        source = pd.DataFrame({'Revenue': [10, 20]})
        result = normalize(source, {'Net_Sales': 'Revenue'}, 'Cafe', 'USD')
        result['filename'] = 'fictional.csv'
        self.key = self.cache.put(source, result, {'Net_Sales': 'Revenue'})
        for name, value in [('backend.analyst_agent.DATASETS', self.cache),
                            ('backend.analyst_agent.CONVERSATIONS', ConversationCache())]:
            handle = patch(name, value)
            handle.start()
            self.addCleanup(handle.stop)
        env = patch.dict(os.environ, {'GEMINI_API_KEY': 'fictional-merge-key'})
        env.start()
        self.addCleanup(env.stop)
        self.payload = {'provider': 'gemini', 'model': MODEL, 'datasetId': self.key, 'question': 'Total sales?', 'filters': {}}

    def post(self, path, token=TOKEN):
        handler = object.__new__(Handler)
        raw = json.dumps(self.payload).encode()
        handler.path = path
        handler.headers = {'X-Dashboard-Token': token, 'Content-Length': str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        captured = []
        handler.send_json = lambda body, status=200: captured.append((status, body))
        handler.do_POST()
        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_overview_and_chat_keep_evidence_and_safe_provider_errors(self):
        for path in ('/api/overview', '/api/analyst'):
            with self.subTest(path=path), patch.object(gemini_client, 'chat', side_effect=calculated_reply):
                status, result = self.post(path)
                self.assertEqual(status, 200)
                self.assertEqual(result['status'], 'answered')
                if path.endswith('overview'):
                    self.assertEqual(result['evidence'][0]['rows'][0], [2, 30])
            for code in (429, 502, 504):
                with patch.object(gemini_client, 'chat', side_effect=gemini_client.GeminiError('Safe provider error.', code)):
                    self.assertEqual(self.post(path), (code, {'error': 'Safe provider error.'}))

    def test_invalid_token_does_not_call_a_provider(self):
        with patch.object(gemini_client, 'chat') as send:
            status, _ = self.post('/api/overview', token='wrong')
            self.assertNotEqual(status, 200)
            send.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('flask') and importlib.util.find_spec('defusedxml'),
                     'Install requirements.txt for account HTTP integration tests.')
class AccountGeminiMergeTests(unittest.TestCase):
    def setUp(self):
        from backend.production import create_app
        self.temp = tempfile.TemporaryDirectory(prefix='gemini-account-merge-')
        self.addCleanup(self.temp.cleanup)
        self.origin = 'https://127.0.0.1:9445'
        env = patch.dict(os.environ, {'APP_ENV': 'production', 'AUTH_MODE': 'accounts',
            'PUBLIC_ORIGIN': self.origin, 'ALLOW_REGISTRATION': 'true',
            'DATABASE_URL': 'sqlite:///' + str(Path(self.temp.name) / 'fictional.sqlite3'),
            'GEMINI_API_KEY': 'fictional-merge-key'})
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app()
        self.client = self.app.test_client()
        self.password = 'fictional-account-password'
        self.register(self.client, 'alice')
        source = {'filename': 'fictional.csv', 'file': base64.b64encode(b'Revenue\n10\n20\n').decode(),
                  'mapping': {'Net_Sales': 'Revenue'}, 'business': 'Cafe', 'currency': 'USD'}
        result = self.post('/api/analyze', source)
        self.assertEqual(result.status_code, 200, result.json)
        self.payload = {'provider': 'gemini', 'model': MODEL, 'datasetId': result.json['datasetId'],
                        'filters': {}, 'question': 'Total sales?'}
        self.scope = OWNER.get()

    def session(self, client=None):
        return (client or self.client).get('/api/auth/session', base_url=self.origin).json

    def post(self, path, body, client=None, headers=None):
        client = client or self.client
        headers = headers if headers is not None else {'Origin': self.origin, 'X-Dashboard-Token': self.session(client)['token']}
        return client.post(path, json=body, base_url=self.origin, headers=headers)

    def register(self, client, name):
        response = self.post('/api/auth/register', {'username': name, 'displayName': name,
                                                   'password': self.password}, client=client)
        self.assertEqual(response.status_code, 201, response.json)

    def test_authenticated_overview_and_seeded_chat_use_the_same_account_scope(self):
        with patch.object(gemini_client, 'chat', side_effect=calculated_reply):
            review = self.post('/api/overview', self.payload)
            self.assertEqual(review.status_code, 200, review.json)
            self.assertEqual(review.json['evidence'][0]['rows'][0], [2, 30])
            reply = self.post('/api/analyst', {**self.payload, 'overviewId': review.json['conversationId']})
        self.assertEqual(reply.status_code, 200, reply.json)
        self.assertEqual(reply.json['status'], 'answered')
        self.assertNotEqual(review.json['conversationId'], reply.json['conversationId'])
        self.assertEqual(OWNER.get(), self.scope)

    def test_authentication_origin_and_session_token_apply_to_overviews(self):
        anonymous = self.app.test_client()
        with patch.object(gemini_client, 'chat') as send:
            self.assertEqual(self.post('/api/overview', self.payload, client=anonymous).status_code, 401)
            self.assertEqual(self.post('/api/overview', self.payload, headers={'Origin': self.origin}).status_code, 403)
            wrong = {'Origin': 'https://other.example', 'X-Dashboard-Token': self.session()['token']}
            self.assertEqual(self.post('/api/overview', self.payload, headers=wrong).status_code, 403)
            send.assert_not_called()

    def test_overviews_share_the_existing_chat_rate_limit(self):
        with patch('backend.account_http.dispatch', return_value={'status': 'answered'}) as dispatch:
            for path in ['/api/overview', '/api/analyst'] * 3:
                result = self.post(path, self.payload)
                self.assertEqual(result.status_code, 200, result.json)
            result = self.post('/api/overview', self.payload)
            self.assertEqual(result.status_code, 429)
            self.assertIn('Retry-After', result.headers)
            self.assertEqual(dispatch.call_count, 6)

    def test_provider_errors_preserve_status_without_fallback(self):
        for path in ('/api/overview', '/api/analyst'):
            for code in (429, 502, 504):
                with patch.object(gemini_client, 'chat', side_effect=gemini_client.GeminiError('Safe Gemini message.', code)), \
                     patch('backend.groq_client.chat') as groq, patch('backend.ollama_client.chat') as local:
                    result = self.post(path, self.payload)
                self.assertEqual(result.status_code, code, result.json)
                self.assertEqual(result.json, {'error': 'Safe Gemini message.'})
                groq.assert_not_called()
                local.assert_not_called()

    def test_dataset_and_overview_access_do_not_cross_accounts_or_sessions(self):
        with patch.object(gemini_client, 'chat', return_value=answer()):
            review = self.post('/api/overview', self.payload)
        self.assertEqual(review.status_code, 200, review.json)
        bob, other_device = self.app.test_client(), self.app.test_client()
        self.register(bob, 'bob')
        login = self.post('/api/auth/login', {'username': 'alice', 'password': self.password}, client=other_device)
        self.assertEqual(login.status_code, 200, login.json)
        with patch.object(gemini_client, 'chat') as send:
            for client in (bob, other_device):
                denied = self.post('/api/overview', self.payload, client=client)
                self.assertEqual(denied.status_code, 400, denied.json)
            self.assertEqual(self.post('/api/auth/logout', {}).status_code, 200)
            self.assertEqual(self.post('/api/overview', self.payload).status_code, 401)
            send.assert_not_called()
        from backend.analyst_conversations import CONVERSATIONS
        self.assertNotIn(review.json['conversationId'], CONVERSATIONS.items)


if __name__ == '__main__':
    unittest.main(verbosity=2)
