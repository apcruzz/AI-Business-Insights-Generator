"""Real authenticated refresh recovery and browser Llama overviews, with fictional data and mocked local inference."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server, WSGIRequestHandler
from scripts.ui_helpers import navigate


def main():
    origin, password = 'https://127.0.0.1:9448', 'fictional-workspace-password'
    os.environ.update(APP_ENV='production', AUTH_MODE='demo', PUBLIC_ORIGIN=origin, GEMINI_API_KEY='',
                      GROQ_API_KEY='synthetic-test-only', DEMO_USERS_JSON=json.dumps({
                          'ui-test': generate_password_hash(password, method='pbkdf2:sha256:600000')}))
    from backend.production import create_app
    from backend.analyst_datasets import DATASETS

    class Quiet(WSGIRequestHandler):
        def log_request(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix='workspace-ui-') as temp:
        temp = Path(temp)
        key, cert = temp / 'key.pem', temp / 'cert.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key),
                        '-out', str(cert), '-days', '1', '-subj', '/CN=127.0.0.1'], check=True, capture_output=True)
        source = temp / 'fictional.csv'
        source.write_text('Date,Product_Name,Category,Net_Sales,Extra\n2026-01-01,Tea,Drinks,10,Fictional extra\n'
                          '2026-01-02,Coffee,Drinks,40,Fictional extra\n2026-01-03,Tea,Drinks,20,Fictional extra\n')
        server = make_server('127.0.0.1', 9448, create_app(), threaded=True,
                             ssl_context=(str(cert), str(key)), request_handler=Quiet)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch('backend.groq_client.GROQ_HTTP.open', side_effect=AssertionError('No real cloud inference')), \
                 patch('backend.ollama_client.LOCAL_HTTP.open', side_effect=AssertionError('No server Ollama')), sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
                options = {'ignore_https_errors': True, 'http_credentials': {'username': 'ui-test', 'password': password},
                           'viewport': {'width': 1440, 'height': 900}}
                context = browser.new_context(**options)
                page = context.new_page()
                errors, local, uploads, restores, pending_discovery = [], [], [], [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: uploads.append(request.url) if request.url.endswith('/api/analyze') else None)
                page.on('request', lambda request: restores.append(request.url) if request.url.endswith('/api/workspace-restore') else None)
                # Delay discovery while the user uploads; a new dataset must never be mistaken for old restore state.
                page.route('**/api/models', lambda route: pending_discovery.append(route))

                def ollama(route):
                    local.append(route.request.url)
                    if route.request.url.endswith('/api/tags'):
                        result = {'models': [{'name': 'llama3.2:3b'}]}
                    else:
                        assert route.request.url.endswith('/api/chat')
                        payload = route.request.post_data_json
                        scope = json.loads(payload['messages'][1]['content'])['dataset']['filters']
                        total = 30 if scope.get('product') == 'Tea' else 40 if scope.get('product') == 'Coffee' else 70
                        result = {'message': {'content': json.dumps({'action': 'answer', 'sql': '',
                            'answer': f'Net sales are {total}. Review costs and coverage before making changes.'})}}
                    route.fulfill(json=result, headers={'Access-Control-Allow-Origin': origin})

                page.route('http://127.0.0.1:11434/**', ollama)
                page.goto(origin)
                page.locator('#upload').set_input_files(str(source))
                page.locator('#inspectButton').click()
                page.locator('#buildButton').click()
                page.locator('input[name="kpi"][value="netSales"]').check()
                page.locator('#loadSelectedCharts').click()
                pending_discovery.pop().continue_()
                page.unroute('**/api/models')
                expect(page.locator('#localModel option[value="groq:openai/gpt-oss-120b"]')).to_be_enabled()
                assert not restores, 'Initial discovery must not restore the dataset just uploaded in this page'
                page.locator('#previewFilterButton').click()
                page.locator('#product').select_option('Tea')
                page.locator('#previewFilterButton').click()
                page.locator('.chartTypeSelect[data-chart-type="trend"]').first.select_option('bar')
                with page.expect_response('**/api/workspace-save') as saved:
                    navigate(page, 'detailNav')
                assert saved.value.ok, saved.value.status
                reference = page.evaluate('sessionStorage.getItem("business-insights-workspace-v1")')
                assert reference and len(reference) == 32
                assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 1')
                assert not local
                page.reload()
                expect(page.locator('#detailPage')).to_be_visible()
                expect(page.locator('#datasetTable tbody tr')).to_have_count(2)
                expect(page.locator('#product')).to_have_value('Tea')
                assert len(uploads) == 1, 'Refresh must not upload or reanalyze the original file'
                navigate(page, 'overviewNav')
                expect(page.locator('#overviewCards .card')).to_have_count(1)
                expect(page.locator('.chartTypeSelect[data-chart-type="trend"]').first).to_have_value('bar')
                expect(page.locator('#overviewCards .value')).to_have_text('$30.00')
                expect(page.locator('#chartChooser')).to_be_hidden()
                page.locator('#previewAccountButton').click()
                expect(page.locator('#accountPage')).to_be_visible()
                page.reload()
                expect(page).to_have_url(origin + '/#account')
                expect(page.locator('#accountPage')).to_be_visible()
                navigate(page, 'overviewNav')
                expect(page.locator('#overviewCards .value')).to_have_text('$30.00')

                page.locator('#openAiSettings').click()
                page.locator('#connectBrowserOllama').click()
                expect(page.locator('#browserOllamaStatus')).to_contain_text('Connected')
                page.locator('#closeAiSettings').click()
                with page.expect_response('**/api/workspace-save'):
                    page.locator('#localModel').select_option('browser_ollama:llama3.2:3b')
                    expect(page.locator('#insightAnswer')).to_contain_text('Automatic overview')
                    expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 30.')
                expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(0)
                expect(page.locator('#insightAnswer .chatMessage--assistant')).to_have_count(1)
                assert len([url for url in local if url.endswith('/api/chat')]) == 1
                navigate(page, 'detailNav')
                navigate(page, 'overviewNav')
                assert len([url for url in local if url.endswith('/api/chat')]) == 1, 'Navigation must reuse the completed overview'
                before = len(local)
                page.reload()
                expect(page.locator('#overviewAssistant')).to_be_visible()
                expect(page.locator('#product')).to_have_value('Tea')
                expect(page.locator('#localModel')).to_have_value('')
                expect(page.locator('#browserOllamaStatus')).to_contain_text('Reconnect Local Ollama explicitly')
                assert len(local) == before, 'Refresh must never reconnect to localhost silently'
                page.locator('#openAiSettings').click()
                page.locator('#connectBrowserOllama').click()
                expect(page.locator('#browserOllamaStatus')).to_contain_text('Connected')
                page.locator('#closeAiSettings').click()
                expect(page.locator('#localModel')).to_have_value('browser_ollama:llama3.2:3b')
                expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 30.')
                page.locator('#insightQuestion').fill('Total net sales?')
                page.locator('#askButton').click()
                expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(1)
                expect(page.locator('#insightAnswer .chatMessage--assistant')).to_have_count(2)
                expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 30.')
                expect(page.locator('#askButton')).to_be_enabled()
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('#previewAssistantTab').click()
                expect(page.locator('#askButton')).to_be_in_viewport(ratio=1)
                page.screenshot(path='/tmp/dashboard-ui-local-overview-restored.png')

                other_context = browser.new_context(**options)
                other = other_context.new_page()
                other.goto(origin)
                other.evaluate('(id) => sessionStorage.setItem("business-insights-workspace-v1", id)', reference)
                other.reload()
                expect(other.locator('#setupStatus')).to_contain_text('previous dataset expired')
                expect(other.locator('#dashboardMain')).to_be_hidden()
                assert other.evaluate('sessionStorage.length === 0')
                # Included samples use the same recovery mechanism as uploads.
                other.select_option('#sample', 'Cafe_Demo.csv')
                other.locator('#inspectButton').click()
                other.locator('#buildButton').click()
                with other.expect_response('**/api/workspace-save'):
                    other.locator('#loadSelectedCharts').click()
                other.reload()
                expect(other.locator('#overview')).to_be_visible()
                expect(other.locator('#previewSidebarDataset')).to_have_text('Cafe_Demo.csv')
                other_context.close()
                # A process restart/eviction must give recovery instructions, never another user's rows.
                with DATASETS._lock:
                    DATASETS._items.clear()
                page.reload()
                expect(page.locator('#setupStatus')).to_contain_text('previous dataset expired')
                expect(page.locator('#dashboardMain')).to_be_hidden()
                assert page.evaluate('sessionStorage.length === 0')
                assert not errors, errors
                browser.close()
                print('PASS: CSV and sample refresh recovery, filters/KPIs/charts/page, opaque tab reference, cross-session denial, expiry recovery; automatic local Llama overview and follow-ups, deduplication, mobile layout, explicit reconnect and no cloud/server-local inference. Local model responses were mocked.')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
