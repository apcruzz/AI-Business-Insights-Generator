"""Hosted WSGI entry point with explicit persistent-account or invited-demo authentication."""
import json
import os
import secrets
import threading
import time
from collections import OrderedDict
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash

from backend.api import dispatch
from backend.ai_providers import available_models
from backend.config import DIST, UPLOAD_LIMIT_BYTES
from backend.groq_client import GroqError
from backend.request_scope import OWNER


class WindowLimits:
    """Bounded process-local fixed windows; no untrusted proxy/IP headers."""
    def __init__(self):
        self.items = OrderedDict()
        self.lock = threading.Lock()

    def allow(self, key, limit, seconds=60):
        # Update each bucket atomically; eviction also bounds memory when many distinct keys arrive.
        with self.lock:
            now = time.monotonic()
            start, count = self.items.get(key, (now, 0))
            if now - start >= seconds:
                start, count = now, 0
            self.items[key] = (start, count + 1)
            self.items.move_to_end(key)
            while len(self.items) > 512:
                self.items.popitem(last=False)
            return count < limit


def create_app():
    # Select the explicit hosted authentication mode; never silently start an unauthenticated service.
    if os.getenv('APP_ENV') != 'production':
        raise RuntimeError('Production entry point requires APP_ENV=production.')
    mode = os.getenv('AUTH_MODE', 'demo')
    if mode == 'accounts':
        from backend.account_http import create_account_app
        return create_account_app()
    if mode != 'demo':
        raise RuntimeError('AUTH_MODE must be accounts or demo.')
    try:
        users = json.loads(os.environ['DEMO_USERS_JSON'])
        # Invited-demo credentials are per-person password hashes, not the local process-wide API token.
        if not isinstance(users, dict) or not 1 <= len(users) <= 20:
            raise ValueError()
        for name, value in users.items():
            if not isinstance(name, str) or not name or len(name) > 80:
                raise ValueError()
            if not isinstance(value, str) or not value.startswith('pbkdf2:sha256:600000$') or len(value.split('$')) != 3:
                raise ValueError()
            if not value.split('$')[1] or len(value.split('$')[2]) != 64:
                raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('Set DEMO_USERS_JSON to individual PBKDF2 password hashes; see README.') from None
    origin = os.environ.get('PUBLIC_ORIGIN', '').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError('PUBLIC_ORIGIN must be the exact https:// demo origin.')
    if not (DIST / 'index.html').is_file():
        raise RuntimeError('Build the React frontend before production startup.')
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = int(min(UPLOAD_LIMIT_BYTES, 2 * 1024 * 1024) * 1.5)
    sessions, session_lock = OrderedDict(), threading.Lock()
    limits = WindowLimits()
    # Limit expensive upload/analysis work to one request while other threads can answer health checks.
    work = threading.BoundedSemaphore(1)
    # Exposed only for deterministic isolation/rate-limit tests, never as HTTP routes.
    app.extensions['demo_limits'] = limits

    def error(message, status):
        response = jsonify(error=message)
        response.status_code = status
        if status == 429:
            response.headers['Retry-After'] = '60'
        return response

    @app.before_request
    def protect():
        if request.path == '/health' and request.method in ('GET', 'HEAD'):
            return None
        if request.host != parsed.netloc:
            return error('Unexpected host.', 400)
        # Avoid expensive credential checks on arbitrary volumes of traffic.
        if not limits.allow('requests-global', 240):
            return error('Demo request limit reached. Try again shortly.', 429)
        auth = request.authorization
        name = auth.username if auth and auth.type == 'basic' else None
        password = auth.password if auth and auth.type == 'basic' else None
        if not name or name not in users or not password or len(password) > 256:
            valid = False
        elif not limits.allow('credential-checks', 120):
            return error('Demo authentication limit reached.', 429)
        else:
            valid = check_password_hash(users[name], password)
        if not valid:
            if not limits.allow('auth-failures', 20):
                return error('Too many authentication failures. Try again shortly.', 429)
            response = error('Team credentials required.', 401)
            response.headers['WWW-Authenticate'] = 'Basic realm="Sponsor demo", charset="UTF-8"'
            return response
        if not limits.allow(('user', name), 90):
            return error('Your demo request limit reached.', 429)
        now = time.monotonic()
        sid = request.cookies.get('__Host-demo')
        # Separate browser sessions even when two visitors use the same invited username.
        with session_lock:
            for key in list(sessions):
                if now - sessions[key]['created'] > 3600:
                    del sessions[key]
            entry = sessions.get(sid)
            if entry is None or entry['user'] != name:
                sid = secrets.token_urlsafe(32)
                entry = {'user': name, 'csrf': secrets.token_urlsafe(32), 'created': now}
                sessions[sid] = entry
                while len(sessions) > 64:
                    sessions.popitem(last=False)
            g.sid = sid
            g.csrf = entry['csrf']
        g.owner_token = OWNER.set(name + ':' + sid)
        # This token protects POST requests against CSRF; Basic credentials remain the authentication.
        if request.method == 'POST':
            if request.headers.get('Origin') != origin:
                return error('Use this demo website to submit requests.', 403)
            if not secrets.compare_digest(request.headers.get('X-Dashboard-Token', ''), g.csrf):
                return error('Your session expired. Reload the page and rebuild the dashboard.', 403)
            if request.mimetype != 'application/json':
                return error('Submit a JSON request.', 415)
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
        if hasattr(g, 'sid'):
            response.set_cookie('__Host-demo', g.sid, max_age=3600, secure=True, httponly=True, samesite='Strict', path='/')
        return response

    @app.teardown_request
    def clear_scope(exception):
        # Undo request ownership on both successful and failed requests before the worker is reused.
        if hasattr(g, 'owner_token'):
            OWNER.reset(g.owner_token)

    @app.get('/health')
    def health():
        return jsonify(status='ok')

    @app.get('/')
    @app.get('/index.html')
    def index():
        return send_from_directory(DIST, 'index.html')

    @app.get('/assets/<path:name>')
    def assets(name):
        return send_from_directory(DIST / 'assets', name)

    @app.get('/api/session')
    def session():
        return jsonify(token=g.csrf, temporaryStorage=True, hosted=True, uploadLimitBytes=2 * 1024 * 1024)

    @app.get('/api/auth/session')
    def auth_session():
        return jsonify(authMode='demo', authenticated=True, user=None)

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
            return error('The demo is busy. Try again shortly.', 429)
        try:
            payload = request.get_json()
            if not isinstance(payload, dict):
                raise ValueError('Submit a JSON object.')
            return jsonify(dispatch('/api/' + action, payload))
        except GroqError as exc:
            return error(str(exc), exc.status)
        except ValueError as exc:
            return error(str(exc), 400)
        finally:
            work.release()

    @app.errorhandler(Exception)
    def failure(exc):
        if isinstance(exc, HTTPException):
            return error('Request rejected: ' + exc.name, exc.code)
        # Provider payloads and uploaded cells must never reach HTTP errors or logs.
        return error('Unable to process this file or question. Check its format and try again.', 400)

    return app
