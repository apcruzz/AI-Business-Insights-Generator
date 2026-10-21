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

                # Profile update rotates the session and reloads without leaving dataset data behind.
                page.locator('#accountButton').click()
                expect(page.locator('#profileUsername')).to_have_value('browser.analyst')
                page.locator('#profileDisplayName').fill('<b>Fictional name</b>')
                page.locator('#profileCurrentPassword').fill('incorrect-password')
                page.locator('#profileForm button').click()
                expect(page.get_by_role('alert')).to_have_text('Current password is incorrect.')
                page.locator('#profileCurrentPassword').fill(password)
                page.screenshot(path='/tmp/accounts-ui-settings.png', full_page=True)
                page.locator('#profileForm button').click()
                expect(page.locator('#inspectButton')).to_be_visible()
                expect(page.locator('#dashboardMain')).to_be_hidden()
                page.locator('#accountButton').click()
                expect(page.locator('#profileDisplayName')).to_have_value('<b>Fictional name</b>')
                assert page.locator('#accountDialog b').count() == 0

                new_password = 'fictional-updated-password'
                page.locator('#passwordCurrent').fill(password)
                page.locator('#passwordNew').fill(new_password)
                page.locator('#passwordConfirm').fill(new_password)
                page.locator('#passwordForm button').click()
                expect(page.locator('#inspectButton')).to_be_visible()
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
                expect(page.locator('#inspectButton')).to_be_visible()

                for width, height in [(1366, 768), (1024, 768), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Workspace overflow at {width}'
                    page.locator('#accountButton').click()
                    assert page.locator('#accountDialog').bounding_box()['width'] <= width
                    page.screenshot(path=f'/tmp/accounts-ui-settings-{width}.png')
                    page.keyboard.press('Escape')
                    expect(page.locator('#accountButton')).to_be_focused()

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
                print('PASS: registration/password validation, sign-in, dashboard/sample/calculated answers, profile update, password change, sign-out, deletion, responsive account dialog, no token storage or implicit Ollama access.')
                browser.close()
        finally:
            server.shutdown()
            thread.join(5)
            server.server_close()


if __name__ == '__main__':
    main()
