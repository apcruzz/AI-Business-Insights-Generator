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
from scripts.ui_helpers import navigate, check_header, check_menu


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
                check_header(page)
                check_menu(page, expect)
                page.locator('#upload').set_input_files(str(source))
                page.locator('#inspectButton').click()
                expect(page.locator('#mappingPanel')).to_be_visible()
                expect(page.locator('#map_Hour')).to_have_class('missingMapping')
                assert page.locator('#map_Hour').evaluate('(el) => getComputedStyle(el).color') == 'rgb(180, 35, 54)'
                page.select_option('#map_Hour', 'Quantity')
                expect(page.locator('#map_Hour')).not_to_have_class('missingMapping')
                page.select_option('#map_Hour', '')
                tools = [page.locator(selector).bounding_box() for selector in ('#toggleOptionalColumns', '#toggleSourcePreview')]
                assert tools[0]['y'] == tools[1]['y']
                page.locator('#toggleOptionalColumns').click()
                expect(page.locator('#operationalMapping')).to_be_visible()
                assert page.locator('#operationalMapping').evaluate('(el) => el.getBoundingClientRect().top >= document.getElementById("toggleOptionalColumns").getBoundingClientRect().bottom')
                page.locator('#toggleOptionalColumns').click()
                page.locator('#toggleSourcePreview').click()
                expect(page.locator('#preview tbody tr')).to_have_count(4)
                page.screenshot(path='/tmp/dashboard-ui-mapping.png', full_page=True)
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
                highlights = page.locator('.highlightsPanel').bounding_box()
                highlight_items = page.locator('#insightCards').bounding_box()
                assert highlights['y'] + highlights['height'] - highlight_items['y'] - highlight_items['height'] <= 18

                # Detail layout and the complete mapped table share the chart filters.
                navigate(page, 'detailNav')
                expect(page.locator('#detailPage')).to_be_visible()
                expect(page.locator('#datasetTable tbody tr')).to_have_count(4)
                expect(page.locator('#datasetRowCount')).to_have_text('4 of 4 rows')
                assert page.locator('#detailPage').evaluate('(el) => el.lastElementChild.id') == 'datasetTablePanel'
                assert page.locator('#detailCharts .detailChartPanel').count() >= 3
                assert page.locator('#from').bounding_box()['y'] == page.locator('#category').bounding_box()['y']
                page.screenshot(path='/tmp/dashboard-ui-detail.png', full_page=True)
                page.locator('#category').select_option('Drinks')
                expect(page.locator('#datasetRowCount')).to_have_text('3 of 4 rows')
                page.locator('#product').select_option('Cookie')
                expect(page.locator('#datasetTable .tableEmpty')).to_have_text('No rows match these filters.')
                page.locator('#reset').click()
                navigate(page, 'overviewNav')

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
                    navigate(page, 'detailNav')
                    check_detail_workspace(page, expect, width)
                    page.screenshot(path=f'/tmp/dashboard-ui-detail-{width}.png', full_page=True)
                    if width == 390:
                        page.locator('.filters').screenshot(path='/tmp/dashboard-ui-detail-mobile-filters.png')
                        page.locator('#detailCharts .detailChartPanel:visible').first.screenshot(path='/tmp/dashboard-ui-detail-mobile-chart.png')
                    navigate(page, 'overviewNav')

                for width, height in [(1366, 600), (1024, 600), (390, 568), (320, 640)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    navigate(page, 'detailNav')
                    check_detail_workspace(page, expect, width)
                    page.screenshot(path=f'/tmp/dashboard-ui-detail-{width}x{height}.png')
                    navigate(page, 'overviewNav')

                check_overview_preview(page, context, expect, origin, source, local_requests)

                # Pagination reaches every row and resets when filters change.
                page.set_viewport_size({'width': 1440, 'height': 900})
                navigate(page, 'setupNav')
                paginated = temp / 'paginated.csv'
                paginated.write_text('Date,Product_Name,Net_Sales\n' + ''.join(
                    f'2026-01-{index % 28 + 1:02d},{"Tea" if index % 2 else "Coffee"},{index}\n' for index in range(1, 61)))
                page.locator('#upload').set_input_files(str(paginated))
                page.locator('#inspectButton').click()
                page.locator('#buildButton').click()
                page.locator('#loadSelectedCharts').click()
                navigate(page, 'detailNav')
                page.locator('#datasetTableTitle').scroll_into_view_if_needed()
                expect(page.locator('#datasetTable tbody tr')).to_have_count(50)
                assert page.evaluate('document.documentElement.scrollHeight > innerHeight')
                page.screenshot(path='/tmp/dashboard-ui-detail-data-table.png')
                page.locator('#nextDataPage').click()
                expect(page.locator('#datasetTable tbody tr')).to_have_count(10)
                expect(page.locator('#datasetPageStatus')).to_contain_text('Page 2 of 2')
                expect(page.locator('#nextDataPage')).to_be_disabled()
                page.locator('#product').select_option('Tea')
                expect(page.locator('#datasetTable tbody tr')).to_have_count(30)
                expect(page.locator('#datasetPageStatus')).to_contain_text('Page 1 of 1')

                # A richer business demo exercises operational mappings and dense charts.
                navigate(page, 'setupNav')
                page.select_option('#sample', 'Salon_Demo.csv')
                page.locator('#inspectButton').click()
                expect(page.locator('#toggleOptionalColumns')).to_have_attribute('aria-expanded', 'true')
                expect(page.locator('#map_Appointment_ID')).not_to_have_class('missingMapping')
                page.locator('#buildButton').click()
                page.locator('#loadSelectedCharts').click()
                navigate(page, 'detailNav')
                page.select_option('#detailChartSelect', 'bookings')
                expect(page.locator('[data-chart-panel="bookings"]')).to_be_visible()
                page.select_option('#detailChartSelect', 'utilization')
                expect(page.locator('[data-chart-panel="utilization"]')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path='/tmp/dashboard-ui-detail-salon.png', full_page=True)
                assert not errors, errors
                print('PASS: mapping colors/tools; KPI/chart save/cancel/defaults; calculated chat; mocked AI/evidence/settings; fixed shared headers, keyboard hamburger navigation, scrolling detail report, responsive original/preview layouts; shared layout state and dataset changes; filtered full table and pagination; keyboard focus.')
                print('Chrome:', browser.version)
                browser.close()
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()


def check_detail_workspace(page, expect, width):
    """Every chart and table is in the document and reachable by page scrolling."""
    check_header(page)
    options = page.locator('#detailChartSelect option').evaluate_all('(els) => els.map(el => el.value)')
    panels = page.locator('#detailCharts .detailChartPanel:visible')
    visible_ids = set(panels.evaluate_all('(els) => els.map(el => el.dataset.chartPanel)'))
    assert visible_ids == set(options), {'visible': visible_ids, 'options': options, 'body': page.locator('body').get_attribute('class')}
    assert page.locator('.detailViewTabs, .detailChartPagination').count() == 0
    assert page.evaluate('document.documentElement.scrollHeight > innerHeight')
    page.select_option('#detailChartSelect', options[-1])
    expect(page.locator(f'[data-chart-panel="{options[-1]}"]')).to_be_in_viewport()
    assert page.evaluate('scrollY > 0')
    expect(page.locator('#detailTables details[open]')).not_to_have_count(0)
    page.locator('#datasetTableTitle').scroll_into_view_if_needed()
    expect(page.locator('#datasetTableTitle')).to_be_in_viewport()
    page.locator('.datasetPagination').scroll_into_view_if_needed()
    expect(page.locator('.datasetPagination')).to_be_in_viewport()
    check_header(page)
    assert page.locator('#detailPage').evaluate('(el) => el.lastElementChild.id') == 'datasetTablePanel'
    window_top = page.evaluate('scrollY')
    assert window_top > 0
    page.evaluate('window.scrollTo(0, 0)')
    expect(page.locator('#dashboardFilters')).to_be_visible()
    check_header(page)


def check_overview_preview(page, context, expect, origin, source, local_requests):
    """Exercise real uploads, shared state, navigation history, and the alternate layout."""
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.locator('#insightQuestion').fill('Which product leads sales?')
    page.locator('#askButton').click()
    expect(page.locator('#insightAnswer')).to_contain_text('Calculated answer')
    transcript = page.locator('#insightAnswer').inner_text()
    local_count = len(local_requests)
    navigate(page, 'previewNav')
    expect(page).to_have_url(origin + '/#overview-preview')
    expect(page.locator('#previewSidebar')).to_be_visible()
    assert page.locator('.previewChartType, .previewEyebrow, .previewDesignBadge').count() == 0
    assert page.locator('#previewHeader').bounding_box()['height'] <= 76
    check_control_sizes(page)
    expect(page.locator('#overviewCards .card')).to_have_count(4)
    expect(page.locator('#insightAnswer')).to_have_text(transcript)
    assert page.locator('#upload').is_hidden()
    assert page.locator('[data-question]').count() == 0
    assert page.locator('.compactAssistant').bounding_box()['x'] > page.locator('#overviewSlot1').bounding_box()['x']
    page.screenshot(path='/tmp/dashboard-ui-preview-draft.png', full_page=True)
    page.locator('#previewCustomize').click()
    page.keyboard.press('Escape')
    expect(page.locator('#previewCustomize')).to_be_focused()
    page.locator('#previewFilterButton').click()
    page.select_option('#category', 'Drinks')
    expect(page.locator('#overviewCards .card').first.locator('.value')).to_have_text('$220.00')
    expect(page.locator('#previewFilterCount')).to_have_text('1')
    page.select_option('#product', 'Cookie')
    expect(page.locator('#insightCards')).to_contain_text('No sales match')
    expect(page.locator('#overviewCards .card').first.locator('.value')).to_have_text('$0.00')
    page.locator('#reset').click()
    page.locator('#previewFilterButton').click()
    expect(page.locator('#dashboardFilters')).to_be_hidden()
    page.locator('#previewFilterButton').click()
    page.locator('#chooseCharts').click()
    expect(page.locator('#dashboardFilters')).to_be_hidden()
    expect(page.locator('#chartChooser')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#previewCustomize')).to_be_focused()

    # Switching layouts preserves both the pending/finished conversation and chosen mode.
    page.select_option('#localModel', 'groq:openai/gpt-oss-120b')
    page.locator('#insightQuestion').fill('Summarize this business')
    assistant_height = page.locator('.compactAssistant').bounding_box()['height']
    page.locator('#askButton').click()
    expect(page.locator('#insightAnswer')).to_contain_text('mock-ui-only')
    transcript = page.locator('#insightAnswer').inner_text()
    assert page.locator('.compactAssistant').bounding_box()['height'] == assistant_height
    assert page.locator('.conversationViewport').evaluate('(el) => el.scrollHeight > el.clientHeight')
    page.get_by_role('link', name='Original overview').click()
    expect(page.locator('#previewSidebar')).to_be_hidden()
    expect(page.locator('#insightAnswer')).to_have_text(transcript)
    assert page.locator('.compactAssistant').bounding_box()['height'] == 300
    page.go_back()
    expect(page.locator('#previewSidebar')).to_be_visible()
    expect(page.locator('#insightAnswer')).to_have_text(transcript)
    page.locator('#previewAiSettings').click()
    expect(page.locator('#aiSettings')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#previewAiSettings')).to_be_focused()

    for width, height in [(1920, 1080), (1440, 900), (1366, 768), (1280, 800), (1280, 600), (1024, 768), (1024, 600), (768, 1024), (390, 844), (390, 568), (320, 700)]:
        page.set_viewport_size({'width': width, 'height': height})
        check_preview_fit(page, expect, width)
        if width <= 1200:
            page.locator('#previewAssistantTab').click()
        expect(page.locator('#askButton')).to_be_in_viewport(ratio=1)
        assert page.locator('.compactAssistant').bounding_box()['width'] < width
        page.screenshot(path=f'/tmp/dashboard-ui-preview-{width}.png', full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.locator('#previewChangeDataset').click()
    expect(page.locator('#setupPage')).to_be_visible()
    page.locator('#cancelSetup').click()
    expect(page.locator('#previewSidebar')).to_be_visible()
    expect(page.locator('#insightAnswer')).to_have_text(transcript)
    page.get_by_role('link', name='Detailed dashboard', exact=True).click()
    expect(page.locator('#detailPage')).to_be_visible()
    expect(page.locator('#datasetTable tbody tr')).to_have_count(4)
    navigate(page, 'previewNav')
    page.locator('#previewChangeDataset').click()
    page.select_option('#sample', 'Cafe_Demo.csv')
    page.locator('#inspectButton').click()
    page.locator('#buildButton').click()
    page.locator('#loadSelectedCharts').click()
    expect(page.locator('#previewSidebarDataset')).to_have_text('Cafe_Demo.csv')
    expect(page.locator('#insightAnswer')).to_have_text('')
    check_preview_fit(page, expect, 1440)
    page.screenshot(path='/tmp/dashboard-ui-preview-cafe.png', full_page=True)
    assert len(local_requests) == local_count, 'Layout navigation must not connect to Ollama'
    # Selecting many KPIs keeps every card reachable in its bounded region.
    page.locator('#previewCustomize').click()
    all_kpis = page.locator('input[name="kpi"]')
    for choice in all_kpis.all():
        choice.check()
    kpi_count = all_kpis.count()
    page.locator('#loadSelectedCharts').click()
    expect(page.locator('#overviewCards .card')).to_have_count(kpi_count)
    page.locator('#overviewCards .card').last.scroll_into_view_if_needed()
    expect(page.locator('#overviewCards .card').last).to_be_in_viewport(ratio=1)
    check_preview_fit(page, expect, 1440)
    page.set_viewport_size({'width': 390, 'height': 844})
    check_preview_fit(page, expect, 390)
    page.set_viewport_size({'width': 1440, 'height': 900})
    expect(page.locator('#previewWorkspaceTabs')).to_be_hidden()
    page.locator('#previewCustomize').click()
    for choice in page.locator('input[name="kpi"]').all():
        choice.uncheck()
    page.locator('input[name="kpi"][value="netSales"]').check()
    page.locator('input[name="kpi"][value="grossMargin"]').check()
    while page.locator('input[name="chartChoice"]:checked').count():
        page.locator('input[name="chartChoice"]:checked').first.uncheck()
    page.locator('input[name="chartChoice"][value="trend"]').check()
    page.locator('#loadSelectedCharts').click()
    expect(page.locator('#overviewCards .card')).to_have_count(2)
    expect(page.locator('.overviewChartSlot:visible')).to_have_count(1)
    check_preview_fit(page, expect, 1440)
    page.get_by_role('link', name='Original overview').click()
    expect(page.locator('#previewSidebar')).to_be_hidden()
    expect(page.locator('#overviewCards .card')).to_have_count(2)
    expect(page.locator('.overviewChartSlot:visible')).to_have_count(1)

    # A fresh preview URL still goes through normal upload and column confirmation.
    fresh = context.new_page()
    fresh.goto(origin + '/#overview-preview')
    expect(fresh.locator('#setupPage')).to_be_visible()
    fresh.locator('#upload').set_input_files(str(source))
    fresh.locator('#inspectButton').click()
    fresh.locator('#buildButton').click()
    fresh.locator('#loadSelectedCharts').click()
    expect(fresh.locator('#previewSidebar')).to_be_visible()
    # Exercise line, bar, stacked, donut, histogram, heatmap, and ranking layouts
    # using fictional samples with realistic category labels and chart notes.
    for filename in ['Tech_Demo.csv', 'Bakery_Demo.csv', 'Online_Shop_Demo.csv', 'Salon_Demo.csv', 'Repair_Shop_Demo.csv']:
        fresh.set_viewport_size({'width': 1440, 'height': 900})
        fresh.locator('#previewChangeDataset').click()
        fresh.select_option('#sample', filename)
        fresh.locator('#inspectButton').click()
        fresh.locator('#buildButton').click()
        fresh.locator('#loadSelectedCharts').click()
        for width, height in [(1440, 900), (390, 844)]:
            fresh.set_viewport_size({'width': width, 'height': height})
            check_preview_fit(fresh, expect, width)
    fresh.close()


def check_preview_fit(page, expect, width):
    """Verify bounded layout and reachable content, rather than just hiding overflow."""
    def fits():
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Preview horizontal overflow at {width}'
        assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), f'Preview page scrolls at {width}'

    if width <= 1200:
        expect(page.locator('#previewWorkspaceTabs')).to_be_visible()
        page.locator('#previewChartsTab').click()
        choices = page.locator('#previewChartSelect option').count()
        for index in range(choices):
            page.select_option('#previewChartSelect', str(index))
            expect(page.locator('.overviewChartSlot:visible')).to_have_count(1)
            expect(page.locator('.overviewChartSlot:visible')).to_be_in_viewport(ratio=1)
            expect(page.locator('#previewNextChart')).to_be_in_viewport(ratio=1)
            check_preview_plots(page, expect)
            fits()
        if choices > 1:
            page.locator('#previewPreviousChart').click()
            expect(page.locator('#previewNextChart')).to_be_enabled()
        page.locator('#previewChartsTab').focus()
        page.keyboard.press('ArrowRight')
        expect(page.locator('#overviewHighlights')).to_be_visible()
        expect(page.locator('#overviewHighlights')).to_be_in_viewport(ratio=1)
        fits()
        page.keyboard.press('ArrowRight')
        expect(page.locator('#overviewAssistant')).to_be_visible()
        expect(page.locator('#overviewAssistant')).to_be_in_viewport(ratio=1)
        box = page.locator('#askButton').bounding_box()
        if box['y'] + box['height'] > page.viewport_size['height']:
            page.screenshot(path='/tmp/dashboard-ui-preview-fit-failure.png')
            raise AssertionError(f'Preview Ask button clipped at {page.viewport_size}: {box}')
        expect(page.locator('#askButton')).to_be_in_viewport(ratio=1)
        fits()
    else:
        expect(page.locator('#previewWorkspaceTabs')).to_be_hidden()
        for panel in page.locator('.overviewChartSlot:visible, #overviewHighlights, #overviewAssistant').all():
            expect(panel).to_be_in_viewport(ratio=1)
        check_preview_plots(page, expect)
        fits()
    page.locator('#previewFilterButton').click()
    expect(page.locator('#dashboardFilters')).to_be_visible()
    fits()
    if width > 1200:
        for control in ['#previewChangeDataset', '.previewOriginalLink']:
            expect(page.locator(control)).to_be_in_viewport(ratio=1)
    page.locator('#category').focus()
    page.keyboard.press('Escape')
    expect(page.locator('#dashboardFilters')).to_be_hidden()
    expect(page.locator('#previewFilterButton')).to_have_attribute('aria-expanded', 'false')
    check_control_sizes(page)
    fits()


def check_control_sizes(page):
    """Comparable actions have the same text size and control height."""
    controls = page.locator('button:visible:not(.mappingTool)')
    sizes = controls.evaluate_all('els => els.map(el => ({font: getComputedStyle(el).fontSize, height: el.getBoundingClientRect().height}))')
    assert len({item['font'] for item in sizes}) <= 1, sizes
    assert all(abs(item['height'] - (32 if page.viewport_size['width'] <= 760 else 36)) < 1 for item in sizes), sizes


def check_preview_plots(page, expect):
    """Actual-size chart labels and marks occupy the pane, with no SVG clipping."""
    for content in page.locator('.overviewChartSlot:visible .overviewChartContent:not([data-overview-chart="category"]):has(> svg)').all():
        expect(content).to_have_attribute('data-chart-size', re.compile(r'.+'))
        metrics = content.evaluate('''el => {
            const svg = el.querySelector(':scope > svg'), box = svg.getBoundingClientRect(), view = svg.viewBox.baseVal;
            return {scale: box.width / view.width,
                clipped: [...svg.querySelectorAll('text')].filter(text => {
                    const b = text.getBBox();
                    return b.x < -.5 || b.y < -.5 || b.x + b.width > view.width + .5 || b.y + b.height > view.height + .5;
                }).map(text => text.textContent)};
        }''')
        assert abs(metrics['scale'] - 1) < .02, metrics
        assert not metrics['clipped'], metrics


if __name__ == '__main__':
    main()
