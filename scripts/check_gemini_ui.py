"""Optional Playwright smoke check with mocked APIs; no cloud requests or keys.

Build first. Install Playwright separately, then run:
python -m scripts.check_gemini_ui --browser /path/to/chromium
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
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
                           'Product': ['Tea', 'Coffee', 'Tea'], 'Revenue': [10, 40, 20],
                           'Category': ['Drinks'] * 3})
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
    try:
        with tempfile.TemporaryDirectory(prefix='gemini-ui-') as temp, sync_playwright() as playwright:
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
                if path == '/api/models':
                    result = {'models': [], 'geminiConfigured': True, 'groqConfigured': True, 'options': [
                        {'provider': 'gemini', 'model': 'gemini-3.8-flash', 'available': True, 'label': 'Gemini 3.8 Flash · Google (cloud)'},
                        {'provider': 'groq', 'model': 'openai/gpt-oss-120b', 'available': True, 'label': 'GPT-OSS 120B · Groq (cloud)'}]}
                elif path == '/api/session':
                    result = {'token': 'ui-token'}
                elif path == '/api/profile':
                    result = {'filename': 'fictional.csv', 'rows': 3, 'columns': source.columns.tolist(),
                              'sheets': [], 'mapping': mapping, 'preview': source.to_dict(orient='records')}
                elif path == '/api/analyze':
                    result = data
                elif path in ('/api/overview', '/api/analyst'):
                    assert route.request.headers.get('x-dashboard-token') == 'ui-token'
                    assert 'key' not in json.dumps(payload).lower()
                    count = sum(item[0] == '/api/overview' for item in calls)
                    if path == '/api/overview' and count == 2:
                        route.fulfill(status=503, json={'error': 'Gemini is temporarily unavailable (HTTP 503). Try again later.'})
                        return
                    selected = 1 if payload['filters'].get('product') == 'Coffee' else 3
                    result = {'status': 'answered', 'conversationId': f'overview-{count}' if path == '/api/overview' else 'chat-a',
                              'mode': 'Gemini cloud data analyst' if payload['provider'] == 'gemini' else 'Groq cloud data analyst',
                              'model': payload['model'], 'selectedRows': selected, 'datasetId': 'ui-synthetic',
                              'answer': 'Business overview\nNet sales are 70. Recommend reviewing Coffee and measuring sales. <script>unsafe()</script>',
                              'evidence': [{'query': 'SELECT SUM(Net_Sales) FROM sales', 'columns': ['net_sales'], 'rows': [[70]], 'truncated': False}]}
                else:
                    raise AssertionError('Unexpected API route: ' + path)
                route.fulfill(json=result)

            page.route('**/api/**', api)
            page.goto(origin)
            page.locator('#upload').set_input_files(str(csv))
            page.locator('#inspectButton').click()
            expect(page.locator('#mappingPanel')).to_be_visible()
            page.locator('#buildButton').click()
            expect(page.locator('#chartChooser')).to_be_visible()
            page.locator('#loadSelectedCharts').click()
            expect(page.locator('#aiOverviewTitle')).to_be_visible()
            assert not any(path == '/api/overview' for path, _ in calls), 'Cloud must require selection'
            page.locator('#localModel').select_option('gemini:gemini-3.8-flash')
            expect(page.locator('#overviewAnswer')).to_contain_text('Net sales are 70.')
            assert page.locator('#overviewAnswer script').count() == 0
            assert page.locator('#overviewEvidence').is_visible()
            page.locator('#insightQuestion').fill('What supports that recommendation?')
            page.locator('#askButton').click()
            expect(page.locator('#insightAnswer')).to_contain_text('Net sales are 70.')
            assert calls[-1][1]['overviewId'] == 'overview-1'
            before = sum(path == '/api/overview' for path, _ in calls)
            chart = page.locator('.chartTypeSelect').first
            values = chart.locator('option').evaluate_all('(options) => options.map(o => o.value)')
            if len(values) > 1:
                chart.select_option(values[-1])
            page.locator('#detailNav').click()
            page.locator('#overviewNav').click()
            page.wait_for_timeout(600)
            assert sum(path == '/api/overview' for path, _ in calls) == before
            expect(page.locator('#insightAnswer')).to_contain_text('What supports that recommendation?')
            page.locator('#product').select_option('Coffee')
            expect(page.locator('#overviewStatus')).to_contain_text('HTTP 503')
            expect(page.locator('#retryOverview')).to_be_visible()
            page.locator('#retryOverview').click()
            expect(page.locator('#overviewStatus')).to_contain_text('1 selected rows')
            expect(page.locator('#retryOverview')).to_be_hidden()
            expect(page.locator('#insightAnswer')).to_have_text('')
            page.screenshot(path=str(root.parent / 'tmp' / 'team-gemini-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(root.parent / 'tmp' / 'team-gemini-mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile horizontal overflow'
            page.locator('#localModel').select_option('')
            expect(page.locator('#overviewAnswer')).to_be_hidden()
            expect(page.locator('#askButton')).to_be_enabled()
            assert not errors, errors
            browser.close()
            print('PASS: Gemini selection, initial overview, chat context, escaping, chart/navigation reuse, filter errors, retry, calculated mode and mobile layout. No cloud requests.')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
