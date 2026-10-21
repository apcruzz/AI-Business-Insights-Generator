"""Account HTTP/storage tests; SQLite fixtures by default, real PostgreSQL optionally.

ACCOUNT_TEST_DATABASE_URL must point at a disposable database when supplied.
Tests use random usernames and no real credentials, files, or model inference.
"""
import base64
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from backend.accounts import AccountStore, AccountUnavailable, token_hash
from backend.analyst_datasets import DATASETS
from backend.analyst_conversations import CONVERSATIONS
from backend.browser_analyst import BROWSER_RUNS
from backend.config import GROQ_MODEL
from backend.production import create_app
from backend.server import TOKEN

ORIGIN = 'https://127.0.0.1:9445'
PASSWORD = 'fictional-account-password'


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='accounts-test-')
        self.addCleanup(self.temp.cleanup)
        self.database = os.getenv('ACCOUNT_TEST_DATABASE_URL', 'sqlite:///' + str(Path(self.temp.name) / 'users.sqlite3'))
        self.env = patch.dict(os.environ, {'APP_ENV': 'production', 'AUTH_MODE': 'accounts',
            'PUBLIC_ORIGIN': ORIGIN, 'DATABASE_URL': self.database, 'ALLOW_REGISTRATION': 'true',
            'GROQ_API_KEY': 'synthetic-test-only'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app()
        self.store = self.app.extensions['account_store']
        self.prefix = 't' + uuid.uuid4().hex[:10]
        self.alice, self.bob = self.app.test_client(), self.app.test_client()
        self.created = []
        self.addCleanup(self.remove_created_users)

    def remove_created_users(self):
        with self.store.transaction() as connection:
            for name in self.created:
                self.store.execute(connection, 'DELETE FROM dashboard_users WHERE username = ?', (name,))

    def get(self, client, path):
        return client.get(path, base_url=ORIGIN)

    def bootstrap(self, client):
        response = self.get(client, '/api/auth/session')
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def request(self, client, path, value, method='POST', csrf=None, origin=ORIGIN):
        csrf = csrf if csrf is not None else self.bootstrap(client)['token']
        return client.open(path, method=method, base_url=ORIGIN, headers={
            'Origin': origin, 'X-Dashboard-Token': csrf}, json=value)

    def register(self, client, name='alice', password=PASSWORD):
        name = self.prefix + name
        response = self.request(client, '/api/auth/register', {'username': name, 'displayName': name, 'password': password})
        self.assertEqual(response.status_code, 201, response.json)
        self.created.append(name)
        return response

    def login(self, client, name='alice', password=PASSWORD):
        return self.request(client, '/api/auth/login', {'username': self.prefix + name, 'password': password})

    def raw_cookie(self, response):
        cookie = SimpleCookie()
        cookie.load(response.headers['Set-Cookie'])
        return cookie['__Host-dashboard'].value

    def upload(self, client):
        value = {'filename': 'fictional.csv', 'file': base64.b64encode(b'Date,Revenue\n2026-01-01,10\n2026-01-02,20\n').decode(),
                 'mapping': {'Date': 'Date', 'Net_Sales': 'Revenue'}, 'business': 'Cafe'}
        response = self.request(client, '/api/analyze', value)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['datasetId']

    def question(self, key):
        return {'provider': 'groq', 'model': GROQ_MODEL, 'datasetId': key, 'question': 'Total sales?'}

    def test_startup_requires_persistent_storage_and_valid_configuration(self):
        for change in ({'DATABASE_URL': ''}, {'DATABASE_URL': 'sqlite:///relative.sqlite'},
                       {'DATABASE_URL': 'sqlite:////tmp/not-created.sqlite', 'PUBLIC_ORIGIN': 'https://public.example'},
                       {'PUBLIC_ORIGIN': 'http://public.example'}, {'ALLOW_REGISTRATION': 'maybe'}, {'AUTH_MODE': 'unknown'}):
            with patch.dict(os.environ, change), self.assertRaises(RuntimeError):
                create_app()

    def test_public_login_shell_never_exposes_dashboard_apis_or_basic_auth(self):
        with self.get(self.alice, '/') as page:
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'/assets/', page.data)
            self.assertIn("connect-src 'self' http://127.0.0.1:11434", page.headers['Content-Security-Policy'])
        self.assertEqual(self.get(self.alice, '/health').status_code, 200)
        for path in ('/api/session', '/api/models', '/api/account', '/api/users'):
            response = self.get(self.alice, path)
            self.assertEqual(response.status_code, 401, path)
            self.assertNotIn('WWW-Authenticate', response.headers)
        for method in ('POST', 'PATCH', 'DELETE'):
            self.assertEqual(self.request(self.alice, '/api/account', {}, method=method).status_code, 401)

    def test_registration_csrf_origin_content_type_and_session_fixation(self):
        initial = self.get(self.alice, '/api/auth/session')
        raw = self.raw_cookie(initial)
        csrf = initial.json['token']
        for wrong in ('', TOKEN, self.bootstrap(self.bob)['token']):
            self.assertEqual(self.request(self.alice, '/api/auth/register', {}, csrf=wrong).status_code, 403)
        self.assertEqual(self.request(self.alice, '/api/auth/register', {}, csrf=csrf, origin='https://evil.example').status_code, 403)
        self.assertEqual(self.alice.get('/', base_url='https://evil.example').status_code, 400)
        text = self.alice.post('/api/auth/register', base_url=ORIGIN, headers={'Origin': ORIGIN, 'X-Dashboard-Token': csrf}, data='{}', content_type='text/plain')
        self.assertEqual(text.status_code, 415)
        response = self.register(self.alice)
        self.assertNotEqual(self.raw_cookie(response), raw)
        self.assertNotEqual(response.json['token'], csrf)
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'):
            self.assertIn(flag, response.headers['Set-Cookie'])
        self.assertEqual(self.request(self.alice, '/api/profile', {}, csrf=csrf).status_code, 403)

    def test_registration_read_and_duplicate_names_do_not_expose_secrets(self):
        result = self.register(self.alice)
        user = result.json['user']
        me = self.get(self.alice, '/api/account').json['user']
        self.assertEqual(me, user)
        self.assertEqual(set(me), {'id', 'username', 'displayName', 'createdAt'})
        self.assertNotIn(PASSWORD, json.dumps(me))
        with self.store.transaction() as connection:
            row = self.store.execute(connection, 'SELECT password_hash FROM dashboard_users WHERE id = ?', (me['id'],)).fetchone()
            self.assertTrue(row['password_hash'].startswith('pbkdf2:sha256:600000$'))
            self.assertNotIn(PASSWORD, row['password_hash'])
            session = self.store.execute(connection, 'SELECT token_hash FROM dashboard_sessions WHERE user_id = ?', (me['id'],)).fetchone()
            self.assertEqual(session['token_hash'], token_hash(self.raw_cookie(result)))
            self.assertNotEqual(session['token_hash'], self.raw_cookie(result))
        duplicate = self.request(self.bob, '/api/auth/register', {'username': user['username'].upper(), 'password': PASSWORD})
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotIn('password_hash', duplicate.get_data(as_text=True))

    def test_invalid_registration_and_mass_assignment_are_rejected(self):
        with patch.object(self.app.extensions['account_limits'], 'allow', return_value=True):
            for value in ({'username': 'ab', 'password': PASSWORD}, {'username': 'user@example.com', 'password': PASSWORD},
                          {'username': self.prefix, 'password': 'short'}, {'username': self.prefix, 'password': PASSWORD, 'role': 'admin'},
                          {'username': self.prefix, 'password': PASSWORD, 'id': 'another-user'},
                          {'username': self.prefix, 'password': PASSWORD, 'displayName': ['invalid']}):
                self.assertEqual(self.request(self.alice, '/api/auth/register', value).status_code, 400)

    def test_login_failures_are_generic_and_logout_revokes_cookie_and_cache(self):
        response = self.register(self.alice)
        raw = self.raw_cookie(response)
        key = self.upload(self.alice)
        fresh = self.app.test_client()
        missing = self.login(fresh, 'missing')
        wrong = self.login(fresh, password='incorrect')
        self.assertEqual((missing.status_code, missing.json), (wrong.status_code, wrong.json))
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.login(fresh).status_code, 200)
        result = self.request(self.alice, '/api/auth/logout', {})
        self.assertEqual(result.status_code, 200)
        self.assertIn('Max-Age=0', result.headers['Set-Cookie'])
        self.assertIsNone(self.store.session(raw))
        self.assertNotIn(key, DATASETS._items)
        self.assertEqual(self.get(self.alice, '/api/account').status_code, 401)
        self.assertEqual(self.get(fresh, '/api/account').status_code, 200)

    def test_dataset_conversation_and_browser_runs_cannot_cross_accounts_or_devices(self):
        self.register(self.alice)
        self.register(self.bob, 'bob')
        other_device = self.app.test_client()
        self.assertEqual(self.login(other_device).status_code, 200)
        key = self.upload(self.alice)
        action = json.dumps({'action': 'unavailable', 'sql': '', 'answer': 'Costs are missing.'})
        with patch('backend.groq_client.chat', return_value=action):
            first = self.request(self.alice, '/api/analyst', self.question(key))
        self.assertEqual(first.status_code, 200, first.json)
        packet = self.request(self.alice, '/api/ollama-start', {'provider': 'browser_ollama', 'model': 'llama3:latest', 'datasetId': key, 'question': 'Sales?'})
        self.assertEqual(packet.status_code, 200, packet.json)
        with patch('backend.groq_client.chat') as chat:
            for client in (self.bob, other_device):
                value = {**self.question(key), 'conversationId': first.json['conversationId']}
                self.assertEqual(self.request(client, '/api/analyst', value).status_code, 400)
                self.assertEqual(self.request(client, '/api/ollama-step', {'runId': packet.json['runId'], 'step': packet.json['step'], 'output': action}).status_code, 400)
            chat.assert_not_called()

    def test_profile_update_requires_password_rotates_sessions_and_discards_data(self):
        self.register(self.alice)
        other = self.app.test_client()
        self.assertEqual(self.login(other).status_code, 200)
        key = self.upload(self.alice)
        value = {'username': self.prefix + 'renamed', 'displayName': '<b>Display name</b>', 'currentPassword': 'wrong'}
        wrong = self.request(self.alice, '/api/account', value, method='PATCH')
        self.assertEqual(wrong.status_code, 400)
        value['currentPassword'] = PASSWORD
        result = self.request(self.alice, '/api/account', value, method='PATCH')
        self.created.append(value['username'])
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.get(self.alice, '/api/account').json['user']['username'], value['username'])
        self.assertEqual(self.get(other, '/api/account').status_code, 401)
        self.assertNotIn(key, DATASETS._items)
        self.assertEqual(self.request(self.alice, '/api/analyst', self.question(key)).status_code, 400)

    def test_password_change_rejects_old_password_and_stale_sessions(self):
        first = self.register(self.alice)
        old_user = self.store.session(self.raw_cookie(first))
        other = self.app.test_client()
        self.assertEqual(self.login(other).status_code, 200)
        new_password = 'fictional-new-account-password'
        response = self.request(self.alice, '/api/account', {'currentPassword': PASSWORD, 'newPassword': new_password}, method='PATCH')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.get(other, '/api/account').status_code, 401)
        self.assertEqual(self.login(other).status_code, 401)
        self.assertEqual(self.login(other, password=new_password).status_code, 200)
        with self.assertRaises(ValueError):
            self.store.create_session(old_user)

    def test_own_account_only_and_duplicate_update_is_atomic(self):
        alice = self.register(self.alice).json['user']
        bob = self.register(self.bob, 'bob').json['user']
        for method in ('PATCH', 'DELETE'):
            attack = {'id': alice['id'], 'currentPassword': PASSWORD}
            self.assertEqual(self.request(self.bob, '/api/account', attack, method=method).status_code, 400)
        self.assertEqual(self.request(self.bob, '/api/account/' + alice['id'], {}, method='DELETE').status_code, 404)
        duplicate = self.request(self.bob, '/api/account', {'username': alice['username'], 'currentPassword': PASSWORD}, method='PATCH')
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.get(self.bob, '/api/account').json['user'], bob)
        self.assertEqual(self.get(self.alice, '/api/account').json['user'], alice)

    def test_delete_revokes_all_sessions_purges_memory_and_recreated_name_has_new_id(self):
        result = self.register(self.alice)
        user_id = result.json['user']['id']
        self.register(self.bob, 'bob')
        other = self.app.test_client()
        self.assertEqual(self.login(other).status_code, 200)
        key = self.upload(self.alice)
        packet = self.request(self.alice, '/api/ollama-start', {'provider': 'browser_ollama', 'model': 'llama3:latest', 'datasetId': key, 'question': 'Sales?'})
        self.assertEqual(packet.status_code, 200)
        self.assertEqual(self.request(self.alice, '/api/account', {'currentPassword': 'wrong'}, method='DELETE').status_code, 400)
        deleted = self.request(self.alice, '/api/account', {'currentPassword': PASSWORD}, method='DELETE')
        self.assertEqual(deleted.status_code, 200, deleted.json)
        self.assertEqual(self.get(other, '/api/account').status_code, 401)
        self.assertEqual(self.get(self.bob, '/api/account').status_code, 200)
        self.assertNotIn(key, DATASETS._items)
        self.assertNotIn(packet.json['runId'], BROWSER_RUNS.items)
        self.assertFalse(any(entry['scope'][0].startswith('account:' + user_id + ':') for entry in CONVERSATIONS.items.values()))
        recreated = self.register(self.alice).json['user']
        self.assertNotEqual(recreated['id'], user_id)

    def test_accounts_and_sessions_survive_app_restart_and_expired_sessions_fail(self):
        registered = self.register(self.alice)
        raw = self.raw_cookie(registered)
        restarted = create_app().test_client()
        restarted.set_cookie('__Host-dashboard', raw, domain='127.0.0.1')
        response = self.get(restarted, '/api/account')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['user'], registered.json['user'])
        with self.store.transaction() as connection:
            self.store.execute(connection, 'UPDATE dashboard_sessions SET expires_at = ? WHERE token_hash = ?', (int(time.time()) - 1, token_hash(raw)))
        self.assertEqual(self.get(self.alice, '/api/models').status_code, 401)
        self.assertFalse(self.bootstrap(self.alice)['authenticated'])

    def test_registration_can_close_without_disabling_existing_logins(self):
        self.register(self.alice)
        with patch.dict(os.environ, {'ALLOW_REGISTRATION': 'false'}):
            client = create_app().test_client()
            self.assertFalse(self.bootstrap(client)['registrationOpen'])
            self.assertEqual(self.request(client, '/api/auth/register', {}).status_code, 403)
            self.assertEqual(self.login(client).status_code, 200)

    def test_rate_limits_run_before_password_work_and_health_stays_accessible(self):
        for name in ('one', 'two', 'three'):
            self.register(self.app.test_client(), name)
        with patch.object(self.store, 'register') as register:
            limited = self.request(self.bob, '/api/auth/register', {'username': self.prefix + 'four', 'password': PASSWORD})
            self.assertEqual(limited.status_code, 429)
            self.assertIn('Retry-After', limited.headers)
            register.assert_not_called()
        with patch.object(self.store, 'authenticate', return_value=None) as authenticate:
            for attempt in range(5):
                self.assertEqual(self.login(self.alice).status_code, 401)
            self.assertEqual(self.login(self.alice).status_code, 429)
            self.assertEqual(authenticate.call_count, 5)
        self.assertEqual(self.get(self.alice, '/health').status_code, 200)

    def test_database_failure_fails_closed_without_exposing_credentials(self):
        self.register(self.alice)
        with patch.object(self.store, 'session', side_effect=AccountUnavailable('Account storage is temporarily unavailable. Try again shortly.')):
            response = self.get(self.alice, '/api/account')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(self.database, response.get_data(as_text=True))
            self.assertEqual(self.get(self.alice, '/health').status_code, 200)

    def test_revoked_session_is_rechecked_after_acquiring_analysis_lock(self):
        registered = self.register(self.alice)
        entry = self.store.session(self.raw_cookie(registered))
        csrf = self.bootstrap(self.alice)['token']
        with patch.object(self.store, 'session', side_effect=[entry, None]), patch('backend.account_http.dispatch') as dispatch:
            response = self.request(self.alice, '/api/analyze', {}, csrf=csrf)
            self.assertEqual(response.status_code, 401)
            dispatch.assert_not_called()

    def test_external_postgres_requires_verified_tls_even_with_weaker_url_options(self):
        with patch('psycopg.connect') as connect:
            AccountStore('postgresql://fictional:unused@db.example/test?sslmode=disable', ORIGIN)
        self.assertEqual(connect.call_args.kwargs['sslmode'], 'verify-full')
        self.assertEqual(connect.call_args.kwargs['sslrootcert'], 'system')
        self.assertIsNone(connect.call_args.kwargs['prepare_threshold'])

    def test_account_database_is_not_available_to_business_sql(self):
        self.register(self.alice)
        key = self.upload(self.alice)
        packet = self.request(self.alice, '/api/ollama-start', {'provider': 'browser_ollama', 'model': 'llama3:latest', 'datasetId': key, 'question': 'Sales?'})
        sql = json.dumps({'action': 'query', 'sql': 'SELECT username, password_hash FROM dashboard_users', 'answer': ''})
        result = self.request(self.alice, '/api/ollama-step', {'runId': packet.json['runId'], 'step': packet.json['step'], 'output': sql})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertIn('toolError', json.dumps(result.json))
        self.assertNotIn('pbkdf2:sha256:', json.dumps(result.json))

    def test_logout_and_deletion_wait_for_analysis_to_finish(self):
        self.register(self.alice)
        lock = self.app.extensions['account_work']
        lock.acquire()
        try:
            self.assertEqual(self.request(self.alice, '/api/auth/logout', {}).status_code, 429)
            self.assertEqual(self.request(self.alice, '/api/account', {'currentPassword': PASSWORD}, method='DELETE').status_code, 429)
        finally:
            lock.release()
        self.assertEqual(self.get(self.alice, '/api/account').status_code, 200)


if __name__ == '__main__':
    unittest.main()
