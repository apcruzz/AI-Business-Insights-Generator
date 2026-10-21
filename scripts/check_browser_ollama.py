"""Optional macOS Chrome + installed Ollama integration check using fictional rows.

Install test-only Playwright first: .venv/bin/python -m pip install playwright
Uses an isolated headless Chrome profile, ephemeral HTTPS on 127.0.0.1:9443, and
existing Ollama on 11434. Does not change Ollama settings or download models.
This local-origin check does NOT verify a public-origin Chrome permission prompt.
"""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='llama3:latest')
    args = parser.parse_args()
    os.environ.update(APP_ENV='production', PUBLIC_ORIGIN='https://127.0.0.1:9443', GROQ_API_KEY='synthetic-test-only')
    from werkzeug.security import generate_password_hash
    os.environ['DEMO_USERS_JSON'] = json.dumps({'browser-test': generate_password_hash('fictional-test-password', method='pbkdf2:sha256:600000')})
    from backend.production import create_app
    from playwright.sync_api import sync_playwright, expect
    from werkzeug.serving import make_server, WSGIRequestHandler

    class QuietHandler(WSGIRequestHandler):
        def log_request(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix='browser-ollama-check-') as temp:
        temp = Path(temp)
        key, cert = temp / 'key.pem', temp / 'cert.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key),
                        '-out', str(cert), '-days', '1', '-subj', '/CN=127.0.0.1'], check=True, capture_output=True)
        source = temp / 'fictional.csv'
        source.write_text('Date,Product_Name,Net_Sales,Gross_Profit\n2026-01-01,Tea,100,30\n2026-02-01,Tea,40,8\n2026-02-02,Coffee,20,2\n2026-03-01,Tea,80,16\n')
        server = make_server('127.0.0.1', 9443, create_app(), threaded=True,
                             ssl_context=(str(cert), str(key)), request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch('backend.groq_client.GROQ_HTTP.open', side_effect=AssertionError('Cloud inference prohibited in browser-local test')), \
                 patch('backend.ollama_client.LOCAL_HTTP.open', side_effect=AssertionError('Server Ollama access prohibited')), sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
                print('Chrome:', browser.version, flush=True)
                context = browser.new_context(ignore_https_errors=True,
                    http_credentials={'username':'browser-test', 'password':'fictional-test-password'}, viewport={'width':1440, 'height':1100})
                page = context.new_page()
                page.set_default_timeout(20000)
                local_requests, backend_requests, errors = [], [], []
                page.on('request', lambda request: (local_requests if request.url.startswith('http://127.0.0.1:11434') else backend_requests).append(request.url.split('?')[0]))
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(os.environ['PUBLIC_ORIGIN'])
                page.wait_for_selector('#inspectButton')
                page.wait_for_timeout(500)
                assert not local_requests, 'Page load must not contact localhost Ollama'
                page.locator('#upload').set_input_files(str(source))
                page.locator('#inspectButton').click()
                page.wait_for_selector('#mappingPanel:not([hidden])')
                page.locator('#buildButton').click()
                page.wait_for_selector('#kpiPanel:not([hidden])')
                page.locator('#dashboardButton').click()
                page.locator('#loadSelectedCharts').click()
                page.wait_for_selector('#dashboardMain:not([hidden])')
                assert not local_requests, 'Dashboard load must not contact localhost Ollama'
                page.screenshot(path='/tmp/browser-ollama-dashboard.png', full_page=True)
                page.locator('#connectBrowserOllama').click()
                expect(page.locator("#browserOllamaStatus")).to_have_text(re.compile(r"^Connected.*"), timeout=25000)
                page.select_option('#localModel', 'browser_ollama:' + args.model)
                print('PASS: production HTTPS UI, upload, KPI selection, no automatic local connection, explicit model discovery', flush=True)
                questions = [
                    'Which product generated the highest revenue?',
                    'Which product has the lowest gross profit margin?',
                    'What month had the lowest sales?',
                    'How can this business improve profitability?',
                    'Why did revenue decrease compared with the previous month?',
                    'What other information is needed to make a better recommendation?',
                ]
                results = []
                for question in questions:
                    if question.startswith('Why did'):
                        # Make the previous-month question unambiguous and exercise UI filters.
                        page.locator('#to').fill('2026-02-28')
                        page.locator('#to').dispatch_event('change')
                    page.locator('#insightQuestion').fill(question)
                    page.locator('#askButton').click()
                    expect(page.locator("#askButton")).to_be_enabled(timeout=640000)
                    text = page.locator('#insightAnswer').inner_text()
                    evidence = page.locator('#analystEvidence').text_content()
                    latest = text.rsplit('You: ', 1)[-1]
                    if question.startswith('Which product generated'):
                        assert '220' in latest and 'Tea' in latest, latest
                    if question.startswith('Which product has'):
                        assert 'Coffee' in latest and '10' in latest, latest
                    if question.startswith('What month'):
                        assert 'February' in latest or '2026-02' in latest, latest
                    if question.startswith('How can'):
                        assert not re.search(r'(?:30(?:\.0+)?%\s+for\s+Tea|Margin Percent for Tea is 30)', latest, re.I), latest
                    if question.startswith('Why did'):
                        assert '3 selected rows' in evidence and '60' in evidence and '-40' in evidence, evidence
                        # A causal question may honestly state missing evidence without repeating figures.
                        assert any(word in latest.lower() for word in ('cause', 'causal', 'cannot', 'missing', 'factors')), latest
                        assert not re.search(r'decreased by (?:\$)?20(?:\.0+)?%? from January', latest, re.I), latest
                    results.append({'question':question, 'text':latest, 'evidence':evidence})
                    print(json.dumps(results[-1]), flush=True)
                    if 'Local Ollama via browser' not in text or 'could not finish' in text or 'Choose Calculated answers to continue' in text:
                        raise AssertionError('Local workflow did not finish: ' + text[-1000:])
                assert any('/api/chat' in path for path in local_requests)
                assert not any(path.endswith('/api/analyst') for path in backend_requests)
                assert not errors, errors
                page.locator('#disconnectBrowserOllama').click()
                assert page.locator('#localModel').input_value() == ''
                assert page.locator('#browserOllamaStatus').inner_text().startswith('Disconnected')
                print('PASS: six real local-model questions, evidence rendering, no server/cloud inference, disconnect', flush=True)
                browser.close()
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()


if __name__ == '__main__':
    main()
