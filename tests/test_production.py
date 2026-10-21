"""HTTP boundary tests; all cloud responses use synthetic, mocked provider data."""
import base64
import io
import json
import os
import threading
import unittest
import zipfile
from unittest.mock import patch

import pandas as pd
from werkzeug.security import generate_password_hash

from backend import groq_client
from backend.config import GROQ_MODEL
from backend.production import create_app
from backend.server import TOKEN

ORIGIN = 'https://demo.example'


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.users = json.dumps({name: generate_password_hash('synthetic-test-password', method='pbkdf2:sha256:600000') for name in ('alice', 'bob')})

    def setUp(self):
        env = patch.dict(os.environ, {'APP_ENV': 'production', 'PUBLIC_ORIGIN': ORIGIN,
                                     'DEMO_USERS_JSON': self.users, 'GROQ_API_KEY': 'synthetic-key'})
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app()
        self.alice, self.bob = self.app.test_client(), self.app.test_client()

    def headers(self, name='alice', **extra):
        value = base64.b64encode((name + ':synthetic-test-password').encode()).decode()
        return {'Authorization': 'Basic ' + value, **extra}

    def get(self, client, path, name='alice'):
        return client.get(path, base_url=ORIGIN, headers=self.headers(name))

    def token(self, client, name='alice'):
        return self.get(client, '/api/session', name).json['token']

    def post(self, client, path, payload, name='alice', token=None, origin=ORIGIN):
        token = token or self.token(client, name)
        return client.post(path, base_url=ORIGIN, headers=self.headers(name, Origin=origin, **{'X-Dashboard-Token': token}), json=payload)

    def payload(self, excel=False):
        frame = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02'], 'Revenue': [10, 20]})
        if excel:
            stream = io.BytesIO()
            frame.to_excel(stream, index=False, sheet_name='Sales')
            raw, name = stream.getvalue(), 'sales.xlsx'
        else:
            raw, name = frame.to_csv(index=False).encode(), 'sales.csv'
        return {'filename': name, 'file': base64.b64encode(raw).decode(),
                'mapping': {'Date': 'Date', 'Net_Sales': 'Revenue'}, 'business': 'Cafe'}

    def upload(self, client, name='alice', excel=False):
        response = self.post(client, '/api/analyze', self.payload(excel), name)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['datasetId']

    def question(self, key, **extra):
        return {'provider': 'groq', 'model': GROQ_MODEL, 'datasetId': key, 'question': 'Total sales?', **extra}

    def test_startup_fails_closed(self):
        for change in ({'DEMO_USERS_JSON': '{}'}, {'DEMO_USERS_JSON': '{"team":"plaintext"}'},
                       {'PUBLIC_ORIGIN': 'http://demo.example'}, {'APP_ENV': 'development'}):
            with patch.dict(os.environ, change), self.assertRaises(RuntimeError):
                create_app()

    def test_health_public_everything_else_authenticated(self):
        client = self.app.test_client()
        self.assertEqual(client.get('/health').status_code, 200)
        for path in ('/', '/api/session', '/api/models', '/assets/missing.js', '/api/analyst'):
            response = client.get(path, base_url=ORIGIN)
            self.assertEqual(response.status_code, 401)
            self.assertIn('WWW-Authenticate', response.headers)
        with self.get(self.alice, '/') as page:
            self.assertEqual(page.status_code, 200)
        response = self.get(self.alice, '/api/session')
        self.assertNotEqual(response.json['token'], TOKEN)
        cookie = response.headers['Set-Cookie']
        for part in ('Secure', 'HttpOnly', 'SameSite=Strict', '__Host-demo'):
            self.assertIn(part, cookie)
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        with patch('backend.ollama_client.LOCAL_HTTP.open') as network:
            models = self.get(self.alice, '/api/models')
            self.assertTrue(models.json['groqConfigured'])
            self.assertEqual(models.json['models'], [])
            network.assert_not_called()
        self.assertNotIn('synthetic-key', models.get_data(as_text=True))

    def test_csrf_origin_shared_token_and_host_rejected(self):
        token = self.token(self.alice)
        for wrong in (TOKEN, 'wrong', self.token(self.bob, 'bob')):
            self.assertEqual(self.post(self.alice, '/api/profile', self.payload(), token=wrong).status_code, 403)
        self.assertEqual(self.post(self.alice, '/api/profile', self.payload(), token=token, origin='https://evil.example').status_code, 403)
        self.assertEqual(self.alice.get('/', base_url='https://evil.example', headers=self.headers()).status_code, 400)

    def test_csv_xlsx_profile_and_analyze(self):
        for excel in (False, True):
            response = self.post(self.alice, '/api/profile', self.payload(excel))
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['rows'], 2)
            self.upload(self.alice, excel=excel)
        for sample in ('Grocery_Demo.csv', 'Ice_Cream_Demo.csv'):
            self.assertEqual(self.post(self.alice, '/api/profile', {'sample': sample}).status_code, 200)
        self.assertEqual(self.post(self.alice, '/api/profile', {'sample': 'Cafe.csv'}).status_code, 400)

    def test_dataset_and_conversation_cannot_cross_users_or_browsers(self):
        key = self.upload(self.alice)
        query = json.dumps({'action': 'query', 'sql': 'SELECT SUM(Net_Sales) AS revenue FROM sales', 'answer': ''})
        answer = json.dumps({'action': 'answer', 'sql': '', 'answer': 'Selected sales total USD 30.'})
        with patch.object(groq_client, 'chat', side_effect=[query, answer]):
            first = self.post(self.alice, '/api/analyst', self.question(key))
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(first.json['evidence'][0]['rows'], [[30.0]])
        with patch.object(groq_client, 'chat') as chat:
            for client, name in ((self.bob, 'bob'), (self.app.test_client(), 'alice')):
                denied = self.post(client, '/api/analyst', self.question(key, conversationId=first.json['conversationId']), name)
                self.assertEqual(denied.status_code, 400)
                self.assertIn('expired', denied.json['error'])
            chat.assert_not_called()
        bkey = self.upload(self.bob, 'bob')
        unavailable = json.dumps({'action': 'unavailable', 'sql': '', 'answer': 'Costs are missing.'})
        with patch.object(groq_client, 'chat', return_value=unavailable) as chat:
            second = self.post(self.bob, '/api/analyst', self.question(bkey, conversationId=first.json['conversationId']), 'bob')
            self.assertNotEqual(second.json['conversationId'], first.json['conversationId'])
            self.assertNotIn('Previous conversation', json.dumps(chat.call_args.args[1]))

    def test_restart_session_loss_and_dataset_expiry(self):
        key = self.upload(self.alice)
        token = self.token(self.alice)
        restarted = create_app().test_client()
        result = self.post(restarted, '/api/analyst', self.question(key), token=token)
        self.assertEqual(result.status_code, 403)
        with patch.object(groq_client, 'chat') as chat:
            missing = self.post(self.alice, '/api/analyst', self.question('no-longer-cached'))
            self.assertIn('expired', missing.json['error'])
            chat.assert_not_called()

    def test_upload_rejections_and_body_limit(self):
        for payload in ({'filename': 'a.csv', 'file': '!!!!'}, {'filename': 'a.exe', 'file': 'eA=='}, [],
                        {'filename': 'a.xlsx', 'file': 'eA=='}):
            self.assertEqual(self.post(self.alice, '/api/profile', payload).status_code, 400)
        large = {'filename': 'a.csv', 'file': 'a' * (self.app.config['MAX_CONTENT_LENGTH'] + 1)}
        self.assertEqual(self.post(self.alice, '/api/profile', large).status_code, 413)
        too_many = {'filename': 'a.csv', 'file': base64.b64encode(('Revenue\n' + '1\n' * 10001).encode()).decode()}
        self.assertEqual(self.post(self.alice, '/api/profile', too_many).status_code, 400)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xl/sharedStrings.xml', b'x' * (13 * 1024 * 1024))
        bomb = {'filename': 'bomb.xlsx', 'file': base64.b64encode(stream.getvalue()).decode()}
        response = self.post(self.alice, '/api/profile', bomb)
        self.assertEqual(response.status_code, 400)
        self.assertIn('expands', response.json['error'])

    def test_work_limit_keeps_health_responsive(self):
        worker = self.app.test_client()
        worker_token = self.token(worker)
        token = self.token(self.bob, 'bob')
        entered, release = threading.Event(), threading.Event()
        responses = []

        def slow_dispatch(path, payload):
            entered.set()
            release.wait(5)
            return {'rows': 1}

        with patch('backend.production.dispatch', side_effect=slow_dispatch):
            thread = threading.Thread(target=lambda: responses.append(self.post(worker, '/api/profile', {}, token=worker_token)))
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.app.test_client().get('/health').status_code, 200)
                busy = self.post(self.bob, '/api/profile', {}, 'bob', token=token)
                self.assertEqual(busy.status_code, 429)
            finally:
                release.set()
                thread.join(5)
            self.assertEqual(responses[0].status_code, 200)

    def test_ai_question_rate_limit(self):
        key = self.upload(self.alice)
        token = self.token(self.alice)
        reply = json.dumps({'action': 'unavailable', 'sql': '', 'answer': 'Costs are missing.'})
        with patch.object(groq_client, 'chat', return_value=reply) as chat:
            for attempt in range(6):
                self.assertEqual(self.post(self.alice, '/api/analyst', self.question(key), token=token).status_code, 200)
            limited = self.post(self.alice, '/api/analyst', self.question(key), token=token)
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(chat.call_count, 6)
            self.assertIn('Retry-After', limited.headers)

    def test_limits_and_groq_failure_are_explicit(self):
        key = self.upload(self.alice)
        with patch.object(groq_client, 'chat', side_effect=groq_client.GroqError('Groq usage limit reached.', 429)):
            response = self.post(self.alice, '/api/analyst', self.question(key))
            self.assertEqual(response.status_code, 429)
            self.assertIn('Groq usage', response.json['error'])
        with patch.object(self.app.extensions['demo_limits'], 'allow', return_value=False):
            self.assertEqual(self.get(self.alice, '/api/models').status_code, 429)
        self.assertEqual(self.post(self.alice, '/api/explain', {}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
