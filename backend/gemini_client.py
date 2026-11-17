"""Server-only Gemini transport; calculations stay in the restricted local tool."""
import json
import os
import socket
import ssl
import urllib.error
import urllib.request

GEMINI_MODEL = 'gemini-3.8-flash'
# Keep the original model constant for older clients and diagnostics. Model choice
# is explicit per request; discovering options never calls the external provider.
GEMINI_MODELS = {
    'gemini-3.5-flash-lite': 'Gemini 3.5 Flash-Lite · Google (cloud)',
    'gemini-3.8-flash': 'Gemini 3.8 Flash · Google (cloud)',
}
GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models/'
GEMINI_CHAT_URL = f'{GEMINI_API_BASE}{GEMINI_MODEL}:generateContent'
MAX_RESPONSE_BYTES = 256 * 1024


class GeminiError(RuntimeError):
    """Only fixed, browser-safe messages cross the HTTP boundary."""
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def configured():
    return bool(os.environ.get('GEMINI_API_KEY', '').strip())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


GEMINI_HTTP = urllib.request.build_opener(NoRedirect())


def connection_error(error):
    """Distinguish a timeout from DNS/certificate failures without exposing prose."""
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return GeminiError('Python could not verify the HTTPS certificate for the Gemini API. Check the computer\'s trusted certificates or managed network configuration.')
    if isinstance(reason, ssl.SSLError):
        return GeminiError('The Python HTTPS connection to Gemini failed during TLS negotiation. Check the managed network or proxy configuration.')
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return GeminiError('The Gemini request timed out. Try again later or select another Gemini model in AI provider / answer mode.', 504)
    if isinstance(reason, socket.gaierror):
        return GeminiError('Python could not resolve the Gemini API address. Check DNS or the network connection.')
    if isinstance(reason, (ConnectionResetError, ConnectionRefusedError)):
        return GeminiError('The network connection to Gemini was interrupted or refused. Check the connection and try again later.')
    return GeminiError('Python could not complete the network connection to Gemini. Check the connection, proxy or VPN settings.')


def chat(model, messages, *, format, timeout=90, num_predict=1200):
    if not isinstance(model, str) or model not in GEMINI_MODELS:
        raise ValueError('Choose one of the Gemini models listed in AI provider / answer mode.')
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        raise ValueError('Set GEMINI_API_KEY in the terminal that starts the Python backend, then restart that backend.')
    instructions, contents = [], []
    for message in messages:
        role, content = message['role'], message['content']
        if role == 'system':
            instructions.append({'text': content})
            continue
        if role not in ('user', 'assistant') or not isinstance(content, str):
            raise ValueError('Unsupported analyst message.')
        role = 'model' if role == 'assistant' else 'user'
        if contents and contents[-1]['role'] == role:
            contents[-1]['parts'].append({'text': content})
        else:
            contents.append({'role': role, 'parts': [{'text': content}]})
    body = {
        'systemInstruction': {'parts': instructions}, 'contents': contents,
        'generationConfig': {
            # Use supported defaults for Gemini 3 sampling/candidate settings.
            # Leave room for reasoning as well as the bounded analyst action.
            'maxOutputTokens': max(8192, min(num_predict, 16000)),
            'thinkingConfig': {'thinkingLevel': 'low', 'includeThoughts': False},
            'responseFormat': {'text': {'mimeType': 'APPLICATION_JSON', 'schema': format}},
        },
    }
    request = urllib.request.Request(
        f'{GEMINI_API_BASE}{model}:generateContent', data=json.dumps(body, allow_nan=False).encode(),
        headers={'x-goog-api-key': key, 'Content-Type': 'application/json',
                 'Accept': 'application/json', 'User-Agent': 'FreeBusinessDashboard/1.0'},
    )
    try:
        with GEMINI_HTTP.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GeminiError('Gemini returned an oversized response. Try a narrower question.')
        result = json.loads(raw)
    except urllib.error.HTTPError as error:
        status = error.code
        retry = error.headers.get('Retry-After', '')
        error.close()
        if status == 429:
            delay = f' Try again in {retry} seconds.' if retry.isdigit() and len(retry) <= 6 else ' Try again later.'
            raise GeminiError('Gemini quota or usage limit reached.' + delay + ' Check the API project limits or choose another answer mode.', 429) from None
        if status == 401:
            raise GeminiError('Gemini rejected API authentication (HTTP 401). Check GEMINI_API_KEY in the Python backend terminal and restart the backend.') from None
        if status == 403:
            raise GeminiError('Gemini denied access (HTTP 403). Check the API key restrictions, project permissions and model availability.') from None
        if status == 400:
            raise GeminiError('Gemini rejected the request settings or API key (HTTP 400). Check the backend Gemini configuration; no unverified answer was used.') from None
        if status == 404:
            raise GeminiError('The configured Gemini model is unavailable to this API project (HTTP 404). Check model access or choose another answer mode.') from None
        if status == 503:
            raise GeminiError('Gemini is temporarily unavailable (HTTP 503). Try again later or choose another answer mode.') from None
        raise GeminiError('Gemini could not complete the request. Try again later or choose another answer mode.') from None
    except OSError as error:
        raise connection_error(error) from None
    except (ValueError, TypeError):
        raise GeminiError('Gemini returned an unreadable response. No unverified answer was used.') from None
    try:
        if result.get('promptFeedback', {}).get('blockReason'):
            raise GeminiError('Gemini declined this request. Rephrase it or use another answer mode.')
        candidate = result['candidates'][0]
        finish = candidate.get('finishReason')
        if finish == 'MAX_TOKENS':
            raise GeminiError('Gemini reached the response limit. Try a more specific question.')
        if finish != 'STOP':
            raise GeminiError('Gemini did not finish a usable answer. Rephrase the question or try again later.')
        parts = candidate['content']['parts']
        answer = ''.join(part['text'] for part in parts
                         if not part.get('thought') and isinstance(part.get('text'), str)).strip()
        if not answer or len(answer) > 16000:
            raise GeminiError('Gemini returned no usable analyst action. No unverified answer was used.')
        return answer
    except (KeyError, IndexError, TypeError, AttributeError):
        raise GeminiError('Gemini returned an unreadable response. No unverified answer was used.') from None
