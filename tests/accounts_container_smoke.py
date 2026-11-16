"""Run inside the built image: real Gunicorn account flow, no external network."""
import http.client
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    import psycopg
    assert psycopg.__version__ == '3.3.6'
    assert os.getuid() != 0
    assert Path(os.environ['SSL_CERT_FILE']).is_file()
    assert not Path('/app/.env').exists()
    assert not Path('/app/data/samples/Cafe.csv').exists()
    with tempfile.TemporaryDirectory(prefix='account-smoke-') as temp:
        origin = 'https://127.0.0.1:10014'
        env = {**os.environ, 'APP_ENV': 'production', 'AUTH_MODE': 'accounts', 'PORT': '10014',
               'PUBLIC_ORIGIN': origin, 'DATABASE_URL': 'sqlite:///' + temp + '/users.sqlite3',
               'ALLOW_REGISTRATION': 'true', 'GROQ_API_KEY': 'synthetic-test-only'}
        process = None

        def call(path, value=None, client=None, method=None):
            headers = {}
            if client and client.get('cookie'):
                headers['Cookie'] = '__Host-dashboard=' + client['cookie']
            if value is not None:
                headers.update({'Origin': origin, 'Content-Type': 'application/json',
                                'X-Dashboard-Token': client.get('token', '') if client else ''})
            connection = http.client.HTTPConnection('127.0.0.1', 10014, timeout=45)
            connection.request(method or ('GET' if value is None else 'POST'), path,
                               body=json.dumps(value) if value is not None else None, headers=headers)
            response = connection.getresponse()
            status, raw = response.status, response.read()
            cookie = response.getheader('Set-Cookie')
            if client is not None and cookie:
                parsed = SimpleCookie(); parsed.load(cookie)
                client['cookie'] = parsed['__Host-dashboard'].value
            connection.close()
            if path in ('/', '/index.html'):
                return status, raw
            body = json.loads(raw)
            if client is not None and body.get('token'):
                client['token'] = body['token']
            return status, body

        def start():
            nonlocal process
            process = subprocess.Popen(['gunicorn', '--config', 'gunicorn.conf.py', 'backend.production:create_app()'], env=env)
            for attempt in range(200):
                if process.poll() is not None:
                    raise RuntimeError('Gunicorn account startup failed')
                try:
                    if call('/health')[0] == 200:
                        return
                except OSError:
                    time.sleep(.2)
            raise RuntimeError('Gunicorn health timed out')

        def stop():
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=35)

        try:
            start()
            assert call('/api/models')[0] == 401
            assert call('/')[0] == 200
            alice, bob = {}, {}
            for client, name in ((alice, 'alice'), (bob, 'bob')):
                assert call('/api/auth/session', client=client)[0] == 200
                status, user = call('/api/auth/register', {'username': name, 'password': 'synthetic-smoke-password'}, client)
                assert status == 201, user
            status, profile = call('/api/profile', {'sample': 'Cafe_Demo.csv'}, alice)
            assert status == 200, profile
            status, dataset = call('/api/analyze', {'sample': 'Cafe_Demo.csv', 'mapping': profile['mapping'], 'business': 'Cafe'}, alice)
            assert status == 200, dataset
            key = dataset['datasetId']
            status, packet = call('/api/ollama-start', {'provider': 'browser_ollama', 'model': 'llama3:latest', 'datasetId': key, 'question': 'Total sales?'}, alice)
            assert status == 200, packet
            output = json.dumps({'action': 'query', 'sql': 'SELECT SUM(Net_Sales) AS revenue FROM sales', 'answer': ''})
            value = {'runId': packet['runId'], 'step': packet['step'], 'output': output}
            assert call('/api/ollama-step', value, bob)[0] == 400
            status, packet = call('/api/ollama-step', value, alice)
            assert status == 200, packet
            output = json.dumps({'action': 'unavailable', 'sql': '', 'answer': 'Operating costs are missing.'})
            status, result = call('/api/ollama-step', {'runId': packet['runId'], 'step': packet['step'], 'output': output}, alice)
            assert status == 200 and result['result']['evidence'], result
            # A real process restart preserves identity/sessions but loses business datasets.
            stop(); start()
            assert call('/api/account', client=alice)[0] == 200
            status, missing = call('/api/analyst', {'provider': 'groq', 'model': 'openai/gpt-oss-120b', 'datasetId': key, 'question': 'Sales?'}, alice)
            assert status == 400 and 'expired' in missing['error'], missing
            replay = dict(alice)
            assert call('/api/auth/logout', {}, alice)[0] == 200
            assert call('/api/account', client=replay)[0] == 401
            assert call('/api/account', client=bob)[0] == 200
            assert call('/api/account', {'currentPassword': 'synthetic-smoke-password'}, bob, method='DELETE')[0] == 200
            assert call('/api/account', client=bob)[0] == 401
            assert call('/health')[0] == 200
            print('PASS: non-root Gunicorn, custom PORT, persistent identities/sessions across restart, authenticated uploads, cross-user browser-run denial, SQL evidence, temporary-data loss, logout/deletion, CA bundle, PostgreSQL driver.', flush=True)
        finally:
            stop()


if __name__ == '__main__':
    main()
