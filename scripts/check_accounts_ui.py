"""Chrome account-flow check with a disposable local DB and fictional data.

Install test-only Playwright, run npm run build, then run this module. No external
database, real users, or model inference is used. Screenshots go to /tmp/accounts-ui-*.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch
from scripts.ui_helpers import navigate, check_header, check_menu


def main():
    from playwright.sync_api import sync_playwright, expect
    from werkzeug.serving import make_server, WSGIRequestHandler

    class QuietHandler(WSGIRequestHandler):
        def log_request(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix='accounts-ui-') as temp:
        temp = Path(temp)
        origin = 'https://127.0.0.1:9446'
        os.environ.update(APP_ENV='production', AUTH_MODE='accounts', PUBLIC_ORIGIN=origin,
                          DATABASE_URL='sqlite:///' + str(temp / 'accounts.sqlite3'),
                          ALLOW_REGISTRATION='true', GROQ_API_KEY='synthetic-test-only')
        from backend.production import create_app
        key, cert = temp / 'key.pem', temp / 'cert.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=127.0.0.1'],
                       check=True, capture_output=True)
        app = create_app()
        server = make_server('127.0.0.1', 9446, app, threaded=True,
                             ssl_context=(str(cert), str(key)), request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch('backend.groq_client.GROQ_HTTP.open', side_effect=AssertionError('No real cloud inference')), \
                 patch('backend.ollama_client.LOCAL_HTTP.open', side_effect=AssertionError('No server Ollama')), sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
                context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 900})
                page = context.new_page()
                errors, local_requests = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: local_requests.append(request.url) if request.url.startswith('http://127.0.0.1:11434') else None)
                password = 'fictional-browser-password'
                page.goto(origin)
                expect(page.locator('#authTitle')).to_have_text('Welcome back')
                assert page.locator('#dashboardMain').count() == 0
                assert not local_requests
                page.screenshot(path='/tmp/accounts-ui-sign-in.png', full_page=True)
                page.get_by_role('button', name='Create account', exact=True).click()
                page.locator('#registerDisplayName').fill('Fictional Analyst')
                page.locator('#authUsername').fill('browser.analyst')
                page.locator('#authPassword').fill(password)
                page.locator('#confirmRegistrationPassword').fill('does-not-match-password')
                page.locator('#authSubmit').click()
                expect(page.get_by_role('alert')).to_have_text('Passwords do not match.')
                page.locator('#confirmRegistrationPassword').fill(password)
                page.screenshot(path='/tmp/accounts-ui-register.png', full_page=True)
                page.locator('#authSubmit').click()
                expect(page.locator('#inspectButton')).to_be_visible()
                expect(page.locator('#accountButton')).to_be_visible()
                assert not local_requests

                page.select_option('#sample', 'Cafe_Demo.csv')
                page.locator('#inspectButton').click()
                page.locator('#buildButton').click()
                page.locator('#loadSelectedCharts').click()
                expect(page.locator('#dashboardMain')).to_be_visible()
                page.locator('#insightQuestion').fill('What are total sales?')
                page.locator('#askButton').click()
                expect(page.locator('#insightAnswer')).to_contain_text('Calculated answer')
                page.screenshot(path='/tmp/accounts-ui-dashboard.png', full_page=True)
                assert not local_requests

                # Account is a normal route. Navigation preserves the dataset and chat.
                transcript = page.locator('#insightAnswer').inner_text()
                navigate(page, 'previewNav')
                for width, height in [(1440, 900), (1024, 768), (390, 568)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    check_header(page)
                    expect(page.locator('#previewAccountButton')).to_be_in_viewport(ratio=1)
                    page.locator('#previewAccountButton').click()
                    expect(page).to_have_url(origin + '/#account')
                    expect(page.locator('#accountPage')).to_be_visible()
                    expect(page.locator('#profileUsername')).to_have_value('browser.analyst')
                    check_menu(page, expect)
                    assert page.locator('#accountDialog').count() == 0
                    check_header(page)
                    page.go_back()
                    expect(page.locator('#previewSidebar')).to_be_visible()
                    expect(page.locator('#insightAnswer')).to_have_text(transcript)
                page.set_viewport_size({'width': 1440, 'height': 900})
                page.screenshot(path='/tmp/accounts-ui-overview-preview.png', full_page=True)
                navigate(page, 'detailNav')
                for width, height in [(1366, 768), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    check_header(page)
                    page.locator('#accountButton').click()
                    expect(page.locator('#accountPage')).to_be_visible()
                    check_header(page)
                    navigate(page, 'detailNav')
                    expect(page.locator('#datasetTable tbody tr')).not_to_have_count(0)
                page.set_viewport_size({'width': 1440, 'height': 900})
                navigate(page, 'overviewNav')

                # Profile update rotates the session and reloads without leaving dataset data behind.
                page.locator('#accountButton').click()
                expect(page.locator('#profileUsername')).to_have_value('browser.analyst')
                page.locator('#profileDisplayName').fill('<b>Fictional name</b>')
                page.locator('#profileCurrentPassword').fill('incorrect-password')
                page.locator('#profileForm button').click()
                expect(page.get_by_role('alert')).to_have_text('Current password is incorrect.')
                page.locator('#profileCurrentPassword').fill(password)
                page.screenshot(path='/tmp/accounts-ui-settings.png', full_page=True)
                with page.expect_navigation(wait_until='load'):
                    page.locator('#profileForm button').click()
                expect(page.locator('#accountPage')).to_be_visible()
                expect(page.locator('#dashboardMain')).to_be_hidden()
                expect(page.locator('#profileDisplayName')).to_have_value('<b>Fictional name</b>')
                assert page.locator('#accountPage b').count() == 0

                new_password = 'fictional-updated-password'
                page.locator('#passwordCurrent').fill(password)
                page.locator('#passwordNew').fill(new_password)
                page.locator('#passwordConfirm').fill(new_password)
                with page.expect_navigation(wait_until='load'):
                    page.locator('#passwordForm button').click()
                expect(page.locator('#accountPage')).to_be_visible()
                page.locator('#accountButton').click()
                page.locator('#signOutButton').click()
                expect(page.locator('#authTitle')).to_have_text('Welcome back')
                assert page.locator('#dashboardMain').count() == 0
                assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
                page.locator('#authUsername').fill('browser.analyst')
                page.locator('#authPassword').fill(password)
                page.locator('#authSubmit').click()
                expect(page.get_by_role('alert')).to_have_text('Username or password is incorrect.')
                page.locator('#authPassword').fill(new_password)
                page.locator('#authSubmit').click()
                expect(page.locator('#accountPage')).to_be_visible()

                for width, height in [(1366, 768), (1024, 768), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    page.locator('#accountButton').click()
                    expect(page.locator('#accountPage')).to_be_visible()
                    check_header(page)
                    assert page.locator('#accountPage').bounding_box()['width'] <= width
                    page.screenshot(path=f'/tmp/accounts-ui-settings-{width}.png', full_page=True)
                    page.reload()
                    expect(page.locator('#profileUsername')).to_have_value('browser.analyst')
                    check_header(page)
                    navigate(page, 'setupNav')
                    expect(page.locator('#inspectButton')).to_be_visible()
                    check_header(page)

                page.locator('#accountButton').click()
                page.locator('#deleteCurrentPassword').fill(new_password)
                expect(page.locator('#deleteAccountForm button')).to_be_disabled()
                page.locator('#confirmAccountDeletion').check()
                page.locator('#deleteAccountForm button').click()
                expect(page.locator('#authTitle')).to_have_text('Welcome back')
                page.locator('#authUsername').fill('browser.analyst')
                page.locator('#authPassword').fill(new_password)
                page.locator('#authSubmit').click()
                expect(page.get_by_role('alert')).to_have_text('Username or password is incorrect.')
                page.screenshot(path='/tmp/accounts-ui-sign-in-mobile.png', full_page=True)
                assert not errors, errors
                assert not local_requests
                print('PASS: registration/password validation, sign-in, dashboard/sample/calculated answers, profile update, password change, sign-out, deletion, persistent account page and fixed headers, no token storage or implicit Ollama access.')
                browser.close()
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()


if __name__ == '__main__':
    main()
