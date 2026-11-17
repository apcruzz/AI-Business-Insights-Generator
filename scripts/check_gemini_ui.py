"""Optional browser integration check of automatic Gemini in the unchanged team UI.

Build first, install Playwright separately, then run this script. All APIs are
mocked with fictional data; no model keys or external inference are used.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading

import pandas as pd
from playwright.sync_api import sync_playwright, expect
from backend.normalizer import normalize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', default=shutil.which('chromium') or shutil.which('google-chrome'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-01-03'],
                           'Product': ['Tea', 'Coffee', 'Tea'], 'Revenue': [10, 40, 20], 'Category': ['Drinks'] * 3})
    mapping = {'Date': 'Date', 'Product_Name': 'Product', 'Net_Sales': 'Revenue', 'Category': 'Category'}
    data = normalize(source, mapping, 'Cafe', 'USD')
    data.update(filename='fictional.csv', datasetId='ui-synthetic')
    calls, errors = [], []

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(root / 'dist')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'

    def inference_count():
        return sum(path == '/api/analyst' for path, _ in calls)

    def overview_count():
        return sum(path == '/api/overview' for path, _ in calls)

    try:
        with tempfile.TemporaryDirectory(prefix='gemini-existing-ui-') as temp, sync_playwright() as playwright:
            csv = Path(temp) / 'fictional.csv'
            csv.write_text(source.to_csv(index=False))
            browser = playwright.chromium.launch(executable_path=args.browser, headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('https://**/*', lambda route: route.abort())

            def api(route):
                path = route.request.url.removeprefix(origin)
                payload = route.request.post_data_json if route.request.method == 'POST' else {}
                calls.append((path, payload))
                if path == '/api/auth/session':
                    result = {'authMode': 'local', 'authenticated': True, 'user': None}
                elif path == '/api/session':
                    result = {'token': 'ui-token'}
                elif path == '/api/models':
                    result = {'models': [], 'geminiConfigured': True, 'groqConfigured': True, 'options': [
                        {'provider': 'gemini', 'model': 'gemini-3.5-flash-lite', 'available': True, 'label': 'Gemini Flash-Lite'},
                        {'provider': 'gemini', 'model': 'gemini-3.8-flash', 'available': True, 'label': 'Gemini Flash'},
                        {'provider': 'groq', 'model': 'openai/gpt-oss-120b', 'available': True, 'label': 'Groq'}]}
                elif path == '/api/profile':
                    result = {'filename': 'fictional.csv', 'rows': 3, 'columns': source.columns.tolist(),
                              'sheets': [], 'mapping': mapping, 'preview': source.to_dict(orient='records')}
                elif path == '/api/analyze':
                    result = data
                elif path in ('/api/overview', '/api/analyst'):
                    assert route.request.headers.get('x-dashboard-token') == 'ui-token'
                    assert payload['provider'] == 'gemini'
                    coffee = payload['filters'].get('product') == 'Coffee'
                    if path == '/api/overview' and overview_count() == 2:
                        route.fulfill(status=503, json={'error': 'Synthetic Gemini error (HTTP 503).'})
                        return
                    if path == '/api/analyst':
                        assert payload['overviewId'] == (None if coffee and overview_count() == 2 else 'overview-' + str(overview_count()))
                    total = 40 if coffee else 70
                    result = {'status': 'answered',
                        'conversationId': 'overview-' + str(overview_count()) if path == '/api/overview' else 'chat-coffee' if coffee else 'chat-all',
                        'mode': 'Gemini cloud data analyst', 'model': payload['model'],
                        'selectedRows': 1 if coffee else 3, 'datasetId': 'ui-synthetic',
                        'answer': f'Net sales are {total}. <script>unsafe()</script>',
                        'evidence': [{'query': 'SELECT SUM(Net_Sales) FROM sales', 'columns': ['net_sales'], 'rows': [[total]], 'truncated': False}]}
                else:
                    errors.append('Unexpected API route: ' + path)
                    route.fulfill(status=404, json={'error': 'Unexpected test route.'})
                    return
                route.fulfill(json=result)

            page.route('**/api/**', api)
            page.goto(origin)
            page.locator('#upload').set_input_files(str(csv))
            page.locator('#inspectButton').click()
            expect(page.locator('#mappingPanel')).to_be_visible()
            page.locator('#buildButton').click()
            expect(page.locator('#chartChooser')).to_be_visible()
            page.locator('#loadSelectedCharts').click()
            expect(page.locator('#overviewAssistant')).to_be_visible()
            expect(page.locator('#aiOverviewPanel')).to_have_count(0)
            assert overview_count() == 0 and inference_count() == 0
            page.locator('#localModel').select_option('gemini:gemini-3.5-flash-lite')
            expect(page.locator('#insightAnswer')).to_contain_text('Automatic overview')
            expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 70.')
            expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(0)
            expect(page.locator('#insightAnswer .chatMessage--assistant')).to_have_count(1)
            assert overview_count() == 1 and inference_count() == 0
            page.locator('#insightQuestion').fill('Total net sales?')
            page.locator('#askButton').click()
            expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 70.')
            expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(1)
            expect(page.locator('#insightAnswer .chatMessage--assistant')).to_have_count(2)
            expect(page.locator('#insightAnswer .chatMessage--assistant').last).to_contain_text('Net sales are 70.')
            expect(page.locator('#insightAnswer script')).to_have_count(0)
            assert calls[-1][1]['model'] == 'gemini-3.5-flash-lite'
            page.evaluate("location.hash = '#detailed-dashboard'")
            expect(page.locator('#detailPage')).to_be_visible()
            page.evaluate("location.hash = '#business-overview'")
            expect(page.locator('#overview')).to_be_visible()
            assert overview_count() == 1 and inference_count() == 1
            expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(1)
            page.locator('#previewFilterButton').click()
            page.locator('#product').select_option('Coffee')
            page.locator('#previewFilterButton').click()
            expect(page.locator('#insightAnswer')).to_contain_text('HTTP 503')
            expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(0)
            expect(page.locator('#askButton')).to_be_enabled()
            assert overview_count() == 2 and inference_count() == 1
            page.locator('#insightQuestion').fill('Total net sales?')
            page.locator('#askButton').click()
            expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 40.')
            assert calls[-1][1]['filters']['product'] == 'Coffee'
            page.locator('#newConversation').click()
            expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 40.')
            expect(page.locator('#insightAnswer')).not_to_contain_text('HTTP 503')
            expect(page.locator('#insightAnswer .chatMessage--user')).to_have_count(0)
            assert overview_count() == 3 and inference_count() == 2
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#previewAssistantTab').click()
            expect(page.locator('#overviewAssistant')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.locator('#localModel').select_option('')
            page.locator('#insightQuestion').fill('Total net sales?')
            page.locator('#askButton').click()
            expect(page.locator('#insightAnswer')).to_contain_text('Calculated answer')
            assert overview_count() == 3 and inference_count() == 2
            assert not errors, errors
            browser.close()
            print('PASS: automatic Gemini overview is an assistant-only message in the existing chat; follow-up scope, filters, explicit retry, errors, escaping, navigation, mobile and calculated answers checked. APIs were mocked.')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
