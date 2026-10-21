"""Run inside the runtime image: real Gunicorn, custom PORT, no external services."""
import base64
import http.client
import json
import os
from pathlib import Path
import subprocess
import time
from werkzeug.security import generate_password_hash


def main():
    assert os.getuid() != 0, 'Container must run unprivileged'
    assert not Path('/app/data/samples/Cafe.csv').exists()
    assert not Path('/app/.env').exists()
    password = 'fictional-container-test-password'
    env = {**os.environ, 'APP_ENV': 'production', 'PORT': '10013',
           'PUBLIC_ORIGIN': 'https://demo.example',
           'DEMO_USERS_JSON': json.dumps({'smoke': generate_password_hash(password, method='pbkdf2:sha256:600000')})}
    process = subprocess.Popen(['gunicorn', '--config', 'gunicorn.conf.py', 'backend.production:create_app()'], env=env)
    authorization = 'Basic ' + base64.b64encode(('smoke:' + password).encode()).decode()

    def call(path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', 10013, timeout=30)
        connection.request('GET' if body is None else 'POST', path, body=body,
                           headers={'Host': 'demo.example', **(headers or {})})
        response = connection.getresponse()
        status, response_headers, raw = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, response_headers, raw

    try:
        for attempt in range(150):
            if process.poll() is not None:
                raise RuntimeError('Gunicorn failed to start')
            try:
                if call('/health')[0] == 200:
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('Health endpoint did not start')
        assert call('/api/session')[0] == 401
        status, headers, body = call('/api/session', headers={'Authorization': authorization})
        assert status == 200
        token = json.loads(body)['token']
        cookie = headers['Set-Cookie'].split(';')[0]
        authenticated = {'Authorization': authorization, 'Cookie': cookie}
        status, _, page = call('/', headers=authenticated)
        assert status == 200 and b'/assets/' in page
        payload = json.dumps({'sample': 'Cafe_Demo.csv'})
        post_headers = {**authenticated, 'Origin': 'https://demo.example',
                        'X-Dashboard-Token': token, 'Content-Type': 'application/json'}
        status, _, profile = call('/api/profile', payload, post_headers)
        assert status == 200, profile
        profile = json.loads(profile)
        payload = json.dumps({'sample': 'Cafe_Demo.csv', 'mapping': profile['mapping'], 'business': 'Cafe'})
        status, _, result = call('/api/analyze', payload, post_headers)
        assert status == 200 and json.loads(result)['datasetId'], result
        dataset_id = json.loads(result)['datasetId']
        payload = json.dumps({'provider':'browser_ollama', 'model':'llama3.2:3b', 'datasetId':dataset_id, 'question':'What information is missing?'})
        status, _, packet = call('/api/ollama-start', payload, post_headers)
        assert status == 200, packet
        packet = json.loads(packet)
        payload = json.dumps({'runId':packet['runId'], 'step':packet['step'], 'output':json.dumps({'action':'query', 'sql':'SELECT SUM(Net_Sales) AS revenue FROM sales', 'answer':''})})
        status, _, packet = call('/api/ollama-step', payload, post_headers)
        assert status == 200, packet
        packet = json.loads(packet)
        payload = json.dumps({'runId':packet['runId'], 'step':packet['step'], 'output':json.dumps({'action':'unavailable', 'sql':'', 'answer':'Operating costs are not supplied.'})})
        status, _, completed = call('/api/ollama-step', payload, post_headers)
        assert status == 200 and json.loads(completed)['result']['evidence'], completed
        status, _, models = call('/api/models', headers=authenticated)
        assert status == 200 and json.loads(models)['models'] == []
        assert call('/health')[0] == 200
        print('PASS: non-root image, synthetic samples only, Gunicorn custom PORT, health, authentication, CSRF, static UI, profile/analyze, browser-mediated SQL steps, hosted server-Ollama exclusion', flush=True)
    finally:
        process.terminate()
        process.wait(timeout=35)


if __name__ == '__main__':
    main()
