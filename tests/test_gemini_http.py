"""Local HTTP and provider boundary checks without file parsers or external AI."""
import http.client
import importlib.util
from http.server import ThreadingHTTPServer
import json
import os
import threading
import unittest
from unittest.mock import patch

import pandas as pd
from backend import gemini_client
from backend.analyst_datasets import DatasetCache
from backend.normalizer import normalize
from backend.server import Handler, TOKEN


class GeminiHTTPTests(unittest.TestCase):
    def setUp(self):
        cache = DatasetCache()
        source = pd.DataFrame({'Revenue': [10, 40, 20]})
        result = normalize(source, {'Net_Sales': 'Revenue'}, 'Cafe', 'USD')
        result['filename'] = 'synthetic.csv'
        self.key = cache.put(source, result, {'Net_Sales': 'Revenue'})
        dataset_patch = patch('backend.analyst_agent.DATASETS', cache)
        dataset_patch.start()
        self.addCleanup(dataset_patch.stop)
        env = patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-http-key'})
        env.start()
        self.addCleanup(env.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, path='/api/overview', payload=None, token=TOKEN):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        self.addCleanup(connection.close)
        body = {'provider': 'gemini', 'model': gemini_client.GEMINI_MODEL,
                'datasetId': self.key, 'filters': {}} if payload is None else payload
        connection.request('POST', path, json.dumps(body), {'Content-Type': 'application/json', 'X-Dashboard-Token': token})
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def test_overview_route_uses_existing_token_and_returns_evidence(self):
        reply = json.dumps({'action': 'answer', 'sql': '', 'answer': 'Net sales are 70. Recommend reviewing the recorded sales.'})
        with patch.object(gemini_client, 'chat', return_value=reply):
            status, result = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['evidence'][0]['rows'][0], [3, 70])
        with patch.object(gemini_client, 'chat') as send:
            denied, _ = self.post(token='wrong-token')
        self.assertNotEqual(denied, 200)
        send.assert_not_called()

    def test_overview_and_chat_return_the_provider_error_status_without_fallback(self):
        for path in ('/api/overview', '/api/analyst'):
            for status in (429, 502, 504):
                with self.subTest(path=path, status=status), patch.object(gemini_client, 'chat', side_effect=gemini_client.GeminiError('Safe Gemini message.', status)):
                    result_status, body = self.post(path, {'provider': 'gemini', 'model': gemini_client.GEMINI_MODEL,
                        'datasetId': self.key, 'filters': {}, 'question': 'Total sales?'})
                self.assertEqual(result_status, status)
                self.assertEqual(body, {'error': 'Safe Gemini message.'})
                self.assertNotIn('synthetic-http-key', json.dumps(body))

    def test_discovery_exposes_only_configuration_and_missing_key_is_actionable(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}), patch('backend.ai_providers.ollama_client.local_models', return_value=[]), patch.object(gemini_client.GEMINI_HTTP, 'open') as send:
            connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
            self.addCleanup(connection.close)
            connection.request('GET', '/api/models')
            body = json.loads(connection.getresponse().read())
            self.assertFalse(body['geminiConfigured'])
            self.assertFalse(next(item for item in body['options'] if item['provider'] == 'gemini')['available'])
            status, error = self.post()
        self.assertEqual(status, 400)
        self.assertIn('Python backend', error['error'])
        send.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('flask') and importlib.util.find_spec('defusedxml'),
                     'Install requirements.txt to run the hosted HTTP checks.')
class GeminiHostedHTTPTests(unittest.TestCase):
    def setUp(self):
        import base64
        from werkzeug.security import generate_password_hash
        from backend.production import create_app
        self.origin = 'https://gemini-test.example'
        password = 'synthetic-test-password'
        users = json.dumps({'test-user': generate_password_hash(password, method='pbkdf2:sha256:600000')})
        env = patch.dict(os.environ, {'APP_ENV': 'production', 'PUBLIC_ORIGIN': self.origin,
                                     'DEMO_USERS_JSON': users, 'GEMINI_API_KEY': 'synthetic-hosted-key'})
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app()
        self.client = self.app.test_client()
        self.auth = {'Authorization': 'Basic ' + base64.b64encode(('test-user:' + password).encode()).decode()}
        self.token = self.client.get('/api/session', base_url=self.origin, headers=self.auth).json['token']
        self.headers = {**self.auth, 'Origin': self.origin, 'X-Dashboard-Token': self.token}
        data = {'filename': 'synthetic.csv', 'file': base64.b64encode(b'Revenue\n10\n20\n').decode(),
                'mapping': {'Net_Sales': 'Revenue'}, 'business': 'Cafe', 'currency': 'USD'}
        uploaded = self.post('/api/analyze', data)
        self.assertEqual(uploaded.status_code, 200)
        self.payload = {'provider': 'gemini', 'model': gemini_client.GEMINI_MODEL,
                        'datasetId': uploaded.json['datasetId'], 'filters': {}}

    def post(self, path, body, **options):
        return self.client.post(path, base_url=self.origin, headers=options.get('headers', self.headers), json=body)

    def test_hosted_overview_requires_login_origin_and_session_token(self):
        with patch.object(gemini_client, 'chat') as send:
            self.assertEqual(self.post('/api/overview', self.payload, headers={}).status_code, 401)
            self.assertEqual(self.post('/api/overview', self.payload, headers=self.auth).status_code, 403)
            self.assertEqual(self.post('/api/overview', self.payload, headers={**self.headers, 'Origin': 'https://other.example'}).status_code, 403)
            send.assert_not_called()
        reply = json.dumps({'action': 'answer', 'sql': '', 'answer': 'Net sales are 30. Recommend reviewing the recorded sales.'})
        with patch.object(gemini_client, 'chat', return_value=reply):
            result = self.post('/api/overview', self.payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['evidence'][0]['rows'][0], [2, 30])
        self.assertNotIn('synthetic-hosted-key', json.dumps(result.json))

    def test_hosted_overview_uses_the_ai_rate_limit(self):
        reply = json.dumps({'action': 'answer', 'sql': '', 'answer': 'Net sales are 30. Recommend reviewing sales.'})
        with patch.object(gemini_client, 'chat', return_value=reply) as send:
            for _ in range(6):
                self.assertEqual(self.post('/api/overview', self.payload).status_code, 200)
            self.assertEqual(self.post('/api/overview', self.payload).status_code, 429)
            self.assertEqual(send.call_count, 6)

    def test_hosted_provider_error_preserves_status_and_does_not_fall_back(self):
        with patch.object(gemini_client, 'chat', side_effect=gemini_client.GeminiError('Gemini quota reached.', 429)), patch('backend.groq_client.chat') as groq:
            result = self.post('/api/overview', self.payload)
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.json, {'error': 'Gemini quota reached.'})
        groq.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
