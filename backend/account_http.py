"""Cookie-authenticated account CRUD with persistent identity and session-scoped datasets."""
from collections import OrderedDict
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from backend.accounts import AccountConflict, AccountStore, AccountUnavailable, SESSION_SECONDS, public_user
from backend.api import dispatch
from backend.ai_providers import available_models
from backend.analyst_datasets import DATASETS
from backend.analyst_conversations import CONVERSATIONS
from backend.browser_analyst import BROWSER_RUNS
from backend.config import DIST
from backend.groq_client import GroqError
from backend.production import WindowLimits
from backend.request_scope import OWNER

COOKIE = '__Host-dashboard'
UNSAFE = {'POST', 'PATCH', 'DELETE', 'PUT'}


def create_account_app():
    origin = os.getenv('PUBLIC_ORIGIN', '').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError('PUBLIC_ORIGIN must be the exact https:// website origin.')
    if not (DIST / 'index.html').is_file():
        raise RuntimeError('Build the React frontend before production startup.')
    if os.getenv('ALLOW_REGISTRATION', 'true') not in ('true', 'false'):
        raise RuntimeError('ALLOW_REGISTRATION must be true or false.')
    registration_open = os.getenv('ALLOW_REGISTRATION', 'true') == 'true'
    store = AccountStore(os.getenv('DATABASE_URL', ''), origin)
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
    limits, work, auth_work = WindowLimits(), threading.BoundedSemaphore(1), threading.BoundedSemaphore(1)
    anonymous, anonymous_lock = OrderedDict(), threading.Lock()
    app.extensions.update(account_store=store, account_limits=limits, account_work=work)

    def error(message, status):
        response = jsonify(error=message)
        response.status_code = status
        if status == 429:
            response.headers['Retry-After'] = '60'
        return response

    def owner(user, sid):
        return f"account:{user['id']}:{sid}"

    def purge(prefix):
        # No locks are held across caches; the work semaphore serializes mutation with analysis.
        BROWSER_RUNS.discard_owner(prefix)
        CONVERSATIONS.discard_owner(prefix)
        DATASETS.discard_owner(prefix)

    def payload(allowed):
        value = request.get_json()
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError('Submit only the fields shown in this form.')
        return value

    @app.before_request
    def protect():
        if request.path == '/health' and request.method in ('GET', 'HEAD'):
            return None
        if request.host != parsed.netloc:
            return error('Unexpected host.', 400)
        if not limits.allow('requests-global', 240):
            return error('Request limit reached. Try again shortly.', 429)
        g.user, g.csrf, g.cookie = None, None, None
        public_shell = request.method in ('GET', 'HEAD') and (request.path in ('/', '/index.html') or request.path.startswith('/assets/'))
        if public_shell:
            return None
        raw = request.cookies.get(COOKIE, '')
        now = time.monotonic()
        with anonymous_lock:
            for key, entry in list(anonymous.items()):
                if now - entry['created'] > 900:
                    del anonymous[key]
            anonymous_entry = anonymous.get(raw)
        entry = None if anonymous_entry else store.session(raw)
        if entry:
            g.user, g.csrf, g.session_id, g.raw_session = entry, entry['csrf'], entry['token_hash'], raw
            g.owner_token = OWNER.set(owner(entry, entry['token_hash']))
        elif anonymous_entry:
            g.csrf = anonymous_entry['csrf']
        public_get = request.method in ('GET', 'HEAD') and (request.path in ('/', '/index.html', '/api/auth/session') or request.path.startswith('/assets/'))
        auth_post = request.method == 'POST' and request.path in ('/api/auth/login', '/api/auth/register')
        if not g.user and not public_get and not auth_post:
            return error('Sign in to continue.', 401)
        if request.method in UNSAFE:
            if request.headers.get('Origin') != origin:
                return error('Use this website to submit requests.', 403)
            if not g.csrf or not secrets.compare_digest(request.headers.get('X-Dashboard-Token', ''), g.csrf):
                return error('Your session expired. Reload the page and sign in again.', 403)
            if request.mimetype != 'application/json':
                return error('Submit a JSON request.', 415)
        if auth_post:
            if request.content_length and request.content_length > 4096:
                return error('Account form is too large.', 413)
            key, count = ('registration', 3) if request.path.endswith('register') else ('sign-in', 12)
            if not limits.allow(key, count):
                return error('Too many account attempts. Wait a minute and try again.', 429)
        if g.user:
            name = g.user['id']
            if not limits.allow(('user', name), 90):
                return error('Your request limit reached. Try again shortly.', 429)
            if request.method in UNSAFE:
                browser_step = request.path in ('/api/ollama-step', '/api/ollama-cancel')
                if not limits.allow(('browser-step' if browser_step else 'post', name), 60 if browser_step else 20):
                    return error('Upload/question limit reached. Try again shortly.', 429)
                if request.path in ('/api/analyst', '/api/ollama-start') and not limits.allow(('ai', name), 6):
                    return error('AI question limit reached. Try again shortly.', 429)

    @app.after_request
    def headers(response):
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
            'Strict-Transport-Security': 'max-age=31536000',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://127.0.0.1:11434; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        if getattr(g, 'cookie', None):
            response.set_cookie(COOKIE, g.cookie, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite='Strict', path='/')
        if getattr(g, 'clear_cookie', False):
            response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='Strict')
        return response

    @app.teardown_request
    def clear_scope(exception):
        if hasattr(g, 'owner_token'):
            OWNER.reset(g.owner_token)

    @app.get('/health')
    def health():
        # An identity-provider outage must not create a Render restart loop.
        return jsonify(status='ok')

    @app.get('/')
    @app.get('/index.html')
    def index():
        return send_from_directory(DIST, 'index.html')

    @app.get('/assets/<path:name>')
    def assets(name):
        return send_from_directory(DIST / 'assets', name)

    @app.get('/api/auth/session')
    def auth_session():
        if not g.csrf:
            raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            with anonymous_lock:
                anonymous[raw] = {'csrf': csrf, 'created': time.monotonic()}
                while len(anonymous) > 64:
                    anonymous.popitem(last=False)
            g.csrf, g.cookie = csrf, raw
        return jsonify(authMode='accounts', authenticated=bool(g.user), user=public_user(g.user) if g.user else None,
                       token=g.csrf, registrationOpen=registration_open)

    def signed_in(user):
        raw, csrf = store.create_session(user, request.cookies.get(COOKIE))
        with anonymous_lock:
            anonymous.pop(request.cookies.get(COOKIE), None)
        g.cookie = raw
        return jsonify(user=public_user(user), token=csrf)

    @app.post('/api/auth/register')
    def register():
        if not registration_open:
            return error('Registration is currently closed.', 403)
        if g.user:
            return error('Sign out before creating another account.', 409)
        if not auth_work.acquire(blocking=False):
            return error('Account service is busy. Try again shortly.', 429)
        try:
            result = signed_in(store.register(payload({'username', 'displayName', 'password'})))
            result.status_code = 201
            return result
        finally:
            auth_work.release()

    @app.post('/api/auth/login')
    def login():
        if not auth_work.acquire(blocking=False):
            return error('Account service is busy. Try again shortly.', 429)
        try:
            value = payload({'username', 'password'})
            name = value.get('username')
            # Missing and existing names use the same bounded password-hash path.
            bucket = name.strip().lower()[:80] if isinstance(name, str) else ''
            if not limits.allow(('sign-in-name', bucket), 5):
                return error('Too many sign-in attempts. Wait a minute and try again.', 429)
            user = store.authenticate(name, value.get('password'))
            if not user:
                return error('Username or password is incorrect.', 401)
            return signed_in(user)
        finally:
            auth_work.release()

    @app.post('/api/auth/logout')
    def logout():
        payload(set())
        if not work.acquire(blocking=False):
            return error('An upload or analysis is running. Wait for it to finish, then sign out.', 429)
        try:
            store.logout(g.raw_session)
            purge(owner(g.user, g.session_id))
            g.clear_cookie = True
            return jsonify(signedOut=True)
        finally:
            work.release()

    @app.get('/api/account')
    def account():
        return jsonify(user=public_user(g.user))

    @app.route('/api/account', methods=['PATCH', 'DELETE'])
    def change_account():
        if request.content_length and request.content_length > 4096:
            return error('Account form is too large.', 413)
        if not limits.allow(('account-change', g.user['id']), 5):
            return error('Too many account changes. Wait a minute and try again.', 429)
        if not work.acquire(blocking=False):
            return error('An upload or analysis is running. Wait for it to finish, then change your account.', 429)
        try:
            if request.method == 'DELETE':
                value = payload({'currentPassword'})
                store.delete(g.user, value.get('currentPassword'))
                purge(f"account:{g.user['id']}:")
                g.clear_cookie = True
                return jsonify(deleted=True)
            value = payload({'username', 'displayName', 'currentPassword', 'newPassword'})
            user = store.update(g.user, value)
            purge(f"account:{g.user['id']}:")
            # The UI reloads after an update, clearing data and context from the revoked session.
            return signed_in(user)
        finally:
            work.release()

    @app.get('/api/session')
    def session():
        return jsonify(token=g.csrf, temporaryStorage=True, hosted=True, uploadLimitBytes=2 * 1024 * 1024)

    @app.get('/api/models')
    def models():
        return jsonify(available_models())

    @app.post('/api/<action>')
    def api(action):
        if action not in ('profile', 'analyze', 'analyst', 'explain', 'ollama-start', 'ollama-step', 'ollama-cancel'):
            return error('Not found.', 404)
        if action == 'explain':
            return error('Local Ollama is available only in local development.', 400)
        if not work.acquire(blocking=False):
            return error('The service is busy. Try again shortly.', 429)
        try:
            if not store.session(g.raw_session):
                return error('Sign in to continue.', 401)
            value = request.get_json()
            if not isinstance(value, dict):
                raise ValueError('Submit a JSON object.')
            return jsonify(dispatch('/api/' + action, value))
        finally:
            work.release()

    @app.errorhandler(Exception)
    def failure(exc):
        if isinstance(exc, AccountUnavailable):
            return error(str(exc), 503)
        if isinstance(exc, AccountConflict):
            return error(str(exc), 409)
        if isinstance(exc, GroqError):
            return error(str(exc), exc.status)
        if isinstance(exc, ValueError):
            return error(str(exc), 400)
        if isinstance(exc, HTTPException):
            return error('Request rejected: ' + exc.name, exc.code)
        return error('Unable to complete this request. Try again shortly.', 500)

    return app
