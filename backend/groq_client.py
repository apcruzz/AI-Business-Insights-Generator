"""Server-only Groq transport for structured data-analyst actions."""
import json
import os
import re
import urllib.error
import urllib.request

from backend.config import GROQ_MODEL, GROQ_CHAT_URL


class GroqError(RuntimeError):
    """Browser-safe provider error, with optional redacted diagnostics for the CLI."""
    def __init__(self, message, status=502, diagnostic=None, retryable_output=False):
        super().__init__(message)
        self.status = status
        # Only the synthetic-data CLI check displays this; HTTP responses use str(error).
        self.diagnostic = diagnostic
        self.retryable_output = retryable_output


def bad_request_error(detail, key):
    """Classify a rejected request without exposing uploaded values or provider prose."""
    if not isinstance(detail, dict):
        detail = {}
    code = detail.get('code')
    diagnostic = safe_diagnostic(detail, key)
    # Only explicit generation errors permit one bounded correction in the analyst loop.
    # Request-size, schema/configuration, authentication, and quota failures are not retried.
    if code in ('json_validate_failed', 'tool_use_failed'):
        return GroqError(
            f'Groq could not produce a valid analysis response (HTTP 400; {code}). No unverified answer was used. Please try the question again.',
            diagnostic=diagnostic, retryable_output=True,
        )
    if code in ('context_length_exceeded', 'context_window_exceeded'):
        return GroqError(
            'Groq reports that the analysis context is too large (HTTP 400; context_length_exceeded). Start a new conversation; if it persists, use a file with fewer unrelated columns.',
            diagnostic=diagnostic,
        )
    # Known request-field names are safe to display; arbitrary provider messages are not.
    param = detail.get('param')
    parameter = None
    for known in ('response_format', 'messages', 'max_completion_tokens', 'reasoning_effort',
                  'include_reasoning', 'temperature', 'model'):
        if isinstance(param, str) and (param == known or param.startswith(known + '.') or param.startswith(known + '[')):
            parameter = known
            break
    if parameter:
        return GroqError(
            f'Groq rejected the {parameter} request setting (HTTP 400). Share this setting name when troubleshooting; shortening the question may not resolve it.',
            diagnostic=diagnostic,
        )
    return GroqError(
        'Groq rejected this analysis request (HTTP 400; unclassified). The cause is not available in this message. Your API key does not need to be changed based on this error alone.',
        diagnostic=diagnostic,
    )


def safe_diagnostic(detail, key):
    """Bound provider validation details and redact credentials before CLI display."""
    if not isinstance(detail, dict):
        return None
    parts = []
    for field in ('code', 'param', 'message'):
        value = detail.get(field)
        if not isinstance(value, str):
            continue
        value = value.replace(key, '[redacted]') if key else value
        value = re.sub(r'gsk_[A-Za-z0-9_-]+', '[redacted]', value)
        value = re.sub(r'(?i)bearer\s+\S+', 'Bearer [redacted]', value)
        value = ' '.join(value.split())
        value = ''.join(character for character in value if character.isprintable())[:500]
        parts.append(f'{field}: {value}')
    return '; '.join(parts) or None


def configured():
    # Only expose a boolean to discovery; credentials never enter browser responses.
    return bool(os.environ.get('GROQ_API_KEY', '').strip())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward credentials or uploaded data to a redirected host.
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


GROQ_HTTP = urllib.request.build_opener(NoRedirect())


def chat(model, messages, *, format, timeout=60, num_predict=1200):
    """Return one structured action; SQL execution stays in the local backend."""
    if model != GROQ_MODEL:
        raise ValueError('Choose GPT-OSS 120B for the Groq provider.')
    key = os.environ.get('GROQ_API_KEY', '').strip()
    if not key:
        raise ValueError('Set GROQ_API_KEY on the backend and restart it to enable Groq.')
    # Use the same action schema as Ollama, with Groq's strict JSON-schema format.
    # No built-in browsing/code tools: all calculations use the restricted local tool.
    body = {
        'model': model, 'messages': messages, 'stream': False,
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'analyst_action', 'strict': True, 'schema': format,
        }},
        'temperature': 0, 'reasoning_effort': 'medium', 'include_reasoning': False,
        'max_completion_tokens': max(2048, num_predict),
    }
    request = urllib.request.Request(
        GROQ_CHAT_URL, data=json.dumps(body, allow_nan=False).encode(),
        # Groq's gateway rejects Python's default urllib User-Agent before authentication.
        # Identify our application explicitly, without impersonating a browser or SDK.
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                 'Accept': 'application/json', 'User-Agent': 'FreeBusinessDashboard/1.0'},
    )
    try:
        with GROQ_HTTP.open(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # Do not echo provider bodies, which can contain prompts or credential details.
        status, retry = error.code, error.headers.get('Retry-After', '')
        # Read only a bounded diagnostic body; expose fixed messages for known error codes.
        try:
            raw_error = error.read(4096)
        except OSError:
            raw_error = b''
        finally:
            error.close()
        error_code, detail = None, {}
        try:
            detail = json.loads(raw_error).get('error', {})
            if isinstance(detail, dict):
                error_code = detail.get('code')
        except (ValueError, AttributeError):
            pass
        if status == 429:
            delay = f' Try again in {retry} seconds.' if retry.isdigit() and len(retry) <= 6 else ' Try again later.'
            raise GroqError('Groq usage limit reached.' + delay + ' Check your Groq account limits or choose another answer mode.', 429) from None
        if status == 401:
            raise GroqError('Groq rejected the API key (HTTP 401). Set a valid GROQ_API_KEY in the terminal that starts the backend, then stop and restart that backend.') from None
        if status == 403:
            if error_code in ('model_permission_blocked_org', 'model_permission_blocked_project'):
                scope = 'organization' if error_code == 'model_permission_blocked_org' else 'project'
                raise GroqError(f'Groq blocked GPT-OSS 120B in your {scope} model permissions (HTTP 403). Ask the {scope} administrator to allow openai/gpt-oss-120b in Groq Settings → Limits.') from None
            if b'error code: 1010' in raw_error.lower():
                raise GroqError('Groq\'s gateway rejected this connection before API authentication (HTTP 403). Check network access or contact Groq support; this does not establish that the API key is invalid.') from None
            raise GroqError('Groq denied access (HTTP 403). Check your Groq account/model permissions and network restrictions. This response does not establish that the API key is invalid.') from None
        if status == 413:
            raise GroqError('This conversation is too large for your Groq limits. Start a new conversation or narrow the dashboard filters.') from None
        if status == 400:
            raise bad_request_error(detail, key) from None
        raise GroqError('Groq is unavailable right now. Try again later or choose another answer mode.') from None
    except (TimeoutError, OSError):
        raise GroqError('Could not reach Groq in time. Check your internet connection and try again.') from None
    except (ValueError, TypeError):
        raise GroqError('Groq returned an unreadable response. Please try again.') from None

    # Truncated/refused responses must not masquerade as a verified answer or burn retries.
    try:
        choice = result['choices'][0]
        answer = choice['message'].get('content')
        if choice.get('finish_reason') == 'length':
            raise GroqError('Groq reached the response limit. Break the question into smaller steps and try again.')
        if not isinstance(answer, str) or not answer.strip():
            raise GroqError('Groq returned no analysis. Rephrase the question and try again.')
        return answer.strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise GroqError('Groq returned an unreadable response. Please try again.') from None
