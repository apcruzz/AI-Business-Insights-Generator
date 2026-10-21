"""Optional Chrome UI regression check with fictional uploads and mocked AI.

Run npm run build first, then .venv/bin/python -m scripts.check_dashboard_ui.
Requires test-only Playwright and an installed Chrome. Never contacts a real AI
provider or changes local Ollama settings. Screenshots go to /tmp/dashboard-ui-*.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from unittest.mock import patch


def main():
    from playwright.sync_api import sync_playwright, expect
    from werkzeug.security import generate_password_hash
    from werkzeug.serving import make_server, WSGIRequestHandler

    origin = 'https://127.0.0.1:9444'
    password = 'fictional-ui-check-password'
    os.environ.update(APP_ENV='production', PUBLIC_ORIGIN=origin,
                      GROQ_API_KEY='synthetic-test-only', DEMO_USERS_JSON=json.dumps({
                          'ui-test': generate_password_hash(password, method='pbkdf2:sha256:600000')}))
    from backend.production import create_app

    class QuietHandler(WSGIRequestHandler):
        def log_request(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix='dashboard-ui-check-') as temp:
        temp = Path(temp)
        key, cert = temp / 'key.pem', temp / 'cert.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1',
                        '-subj', '/CN=127.0.0.1'], check=True, capture_output=True)
        source = temp / 'fictional.csv'
        source.write_text('Date,Product_Name,Category,Quantity,Net_Sales,Gross_Profit\n'
                          '2026-01-01,Tea,Drinks,10,100,30\n'
                          '2026-02-01,Tea,Drinks,4,40,8\n'
                          '2026-02-02,Cookie,Food,5,20,2\n'
                          '2026-03-01,Tea,Drinks,8,80,16\n')
        server = make_server('127.0.0.1', 9444, create_app(), threaded=True,
                             ssl_context=(str(cert), str(key)), request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch('backend.groq_client.GROQ_HTTP.open', side_effect=AssertionError('Real cloud inference prohibited')), \
                 patch('backend.ollama_client.LOCAL_HTTP.open', side_effect=AssertionError('Server Ollama access prohibited')), sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
                context = browser.new_context(ignore_https_errors=True,
                    http_credentials={'username': 'ui-test', 'password': password},
                    viewport={'width': 1440, 'height': 900})
                page = context.new_page()
                errors, local_requests = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def fake_local(route):
                    local_requests.append(route.request.url)
                    assert route.request.url.endswith('/api/tags'), 'No real model inference in this UI check'
                    route.fulfill(json={'models': [{'name': 'ui-test:local'}]},
                                  headers={'Access-Control-Allow-Origin': origin})

                page.route('http://127.0.0.1:11434/**', fake_local)
                page.goto(origin)
                page.locator('#upload').set_input_files(str(source))
                page.locator('#inspectButton').click()
                page.locator('#buildButton').click()
                expect(page.locator('#chartChooser')).to_be_visible()
                assert page.locator('#kpiPanel').evaluate('(el) => el.compareDocumentPosition(document.getElementById("chartChoices")) & Node.DOCUMENT_POSITION_FOLLOWING')
                page.locator('input[name="kpi"][value="netSales"]').check()
                page.locator('input[name="kpi"][value="units"]').check()
                assert page.locator('input[name="chartChoice"]:checked').count() == 3
                assert page.locator('input[name="chartChoice"]:disabled').count() > 0
                page.screenshot(path='/tmp/dashboard-ui-customize.png')
                page.locator('#loadSelectedCharts').click()
                expect(page.locator('#overviewCards .card')).to_have_count(2)
                assert 'Units sold' in page.locator('#overviewCards').inner_text()
                assert page.locator('[data-question]').count() == 0
                assert not local_requests, 'Page load/upload must not contact Ollama'

                # Reopening restores committed choices; Escape discards pending edits.
                page.locator('#chooseCharts').click()
                expect(page.locator('input[name="kpi"][value="units"]')).to_be_checked()
                page.locator('input[name="kpi"][value="units"]').uncheck()
                page.locator('input[name="chartChoice"]:checked').first.uncheck()
                page.keyboard.press('Escape')
                expect(page.locator('#chooseCharts')).to_be_focused()
                page.locator('#chooseCharts').click()
                expect(page.locator('input[name="kpi"][value="units"]')).to_be_checked()
                assert page.locator('input[name="chartChoice"]:checked').count() == 3
                page.locator('input[name="kpi"][value="units"]').uncheck()
                page.locator('#loadSelectedCharts').click()
                expect(page.locator('#overviewCards .card')).to_have_count(1)
                page.locator('#category').select_option('Drinks')
                expect(page.locator('#overviewCards .card')).to_have_count(1)
                page.locator('#reset').click()
                page.locator('#chooseCharts').click()
                page.locator('input[name="kpi"][value="netSales"]').uncheck()
                page.locator('#loadSelectedCharts').click()
                assert page.locator('#overviewCards .card').count() > 1, 'All unchecked must use defaults'

                # Real calculated answer, then a long mocked cloud answer with evidence.
                page.locator('#insightQuestion').fill('Which product leads sales?')
                page.locator('#askButton').click()
                expect(page.locator('#insightAnswer')).to_contain_text('Calculated answer')
                page.screenshot(path='/tmp/dashboard-ui-desktop.png', full_page=True)
                original_height = page.locator('.compactAssistant').bounding_box()['height']
                assert original_height == 300
                page.route('**/api/analyst', lambda route: route.fulfill(json={
                    'conversationId': 'mock-ui-only', 'mode': 'Groq', 'model': 'mock-ui-only',
                    'answer': '\n\n'.join(['Long answer with fictional calculations.'] * 50),
                    'selectedRows': 4, 'evidence': [{'columns': ['Revenue'], 'rows': [[240]],
                        'query': 'SELECT SUM(Net_Sales) AS Revenue FROM sales', 'truncated': False}]}))
                page.select_option('#localModel', 'groq:openai/gpt-oss-120b')
                expect(page.locator('#aiModeSummary')).to_contain_text('Groq cloud')
                page.locator('#insightQuestion').fill('Summarize this business')
                page.locator('#askButton').click()
                expect(page.locator('#insightAnswer')).to_contain_text('mock-ui-only')
                assert page.locator('.compactAssistant').bounding_box()['height'] == original_height
                assert page.locator('.conversationViewport').evaluate('(el) => el.scrollHeight > el.clientHeight')
                page.locator('#analystEvidence > details > summary').click()
                expect(page.locator('#analystEvidence table')).to_be_visible()
                assert page.locator('.compactAssistant').bounding_box()['height'] == original_height

                page.locator('#openAiSettings').click()
                expect(page.locator('#aiDataNotice')).to_contain_text('sent to Groq')
                page.locator('.ollamaSetup > summary').click()
                expect(page.locator('.ollamaSetup pre').first).to_be_visible()
                page.locator('#refreshModels').click()
                expect(page.locator('#refreshModels')).to_be_enabled()
                assert not local_requests, 'Settings/refresh must not silently connect to Ollama'
                page.locator('#connectBrowserOllama').click()
                expect(page.locator('#browserOllamaStatus')).to_have_text(re.compile(r'^Connected.*'))
                page.locator('#closeAiSettings').click()
                expect(page.locator('#openAiSettings')).to_be_focused()
                page.select_option('#localModel', 'browser_ollama:ui-test:local')
                page.locator('#openAiSettings').click()
                page.locator('#disconnectBrowserOllama').click()
                page.keyboard.press('Escape')
                assert page.locator('#localModel').input_value() == ''

                for width, height in [(1366, 768), (1024, 768), (768, 1024), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.locator('.compactAssistant').bounding_box()['height'] == (320 if width <= 850 else 300)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Horizontal overflow at {width}'
                    page.locator('#openAiSettings').click()
                    assert page.locator('#aiSettings').bounding_box()['width'] <= width
                    page.keyboard.press('Escape')
                    page.locator('#chooseCharts').click()
                    page.locator('#loadSelectedCharts').scroll_into_view_if_needed()
                    expect(page.locator('#loadSelectedCharts')).to_be_in_viewport()
                    page.keyboard.press('Escape')
                    page.screenshot(path=f'/tmp/dashboard-ui-{width}.png', full_page=True)
                assert not errors, errors
                print('PASS: upload → combined KPI/chart dialog; save/cancel/defaults; calculated chat; long mocked AI + evidence; settings/connect/disconnect; responsive layout and keyboard focus.')
                print('Chrome:', browser.version)
                browser.close()
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()


if __name__ == '__main__':
    main()
