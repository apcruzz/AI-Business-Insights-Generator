"""Explicit Gemini model routing, privacy and complete scoped analyst flows."""
import http.client
from http.server import ThreadingHTTPServer
import io
import json
import os
import socket
import ssl
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pandas as pd

from backend import gemini_client
from backend.ai_providers import available_models, resolve_model
from backend.analyst_agent import ACTION_SCHEMA, analyze_overview, analyze_question
from backend.analyst_conversations import ConversationCache
from backend.analyst_datasets import DatasetCache
from backend.normalizer import normalize
from backend.server import Handler, TOKEN

LITE = 'gemini-3.5-flash-lite'
ORIGINAL = 'gemini-3.8-flash'
SECRET = 'synthetic-model-options-key'


def action(answer, sql='', kind='answer'):
    return json.dumps({'action': kind, 'sql': sql, 'answer': answer})


def response(answer):
    return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP',
        'content': {'parts': [{'text': answer}]}}]}).encode())


class GeminiModelOptionTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'GEMINI_API_KEY': SECRET})
        env.start()
        self.addCleanup(env.stop)
        self.cache = DatasetCache()
        self.conversations = ConversationCache()
        source = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-02-01'],
                               'Product': ['Tea', 'Coffee', 'Tea'], 'Revenue': [10, 40, 20]})
        mapping = {'Date': 'Date', 'Product_Name': 'Product', 'Net_Sales': 'Revenue'}
        normalized = normalize(source, mapping, 'Cafe', 'USD')
        normalized['filename'] = 'fictional_model_test.csv'
        self.key = self.cache.put(source, normalized, mapping)
        self.payload = {'provider': 'gemini', 'datasetId': self.key, 'filters': {}}
        for name, value in [('DATASETS', self.cache), ('CONVERSATIONS', self.conversations)]:
            handle = patch('backend.analyst_agent.' + name, value)
            handle.start()
            self.addCleanup(handle.stop)

    def test_each_model_routes_to_its_own_fixed_endpoint_and_supported_settings(self):
        for model in (LITE, ORIGINAL):
            with self.subTest(model=model), patch.object(gemini_client.GEMINI_HTTP, 'open', return_value=response(action('OK'))) as send:
                self.assertEqual(resolve_model('gemini', model).chat([{'role': 'user', 'content': 'Fictional test'}], format=ACTION_SCHEMA), action('OK'))
            request = send.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(request.full_url, f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent')
            self.assertEqual(request.get_header('X-goog-api-key'), SECRET)
            self.assertNotIn(SECRET, request.full_url + request.data.decode())
            config = body['generationConfig']
            self.assertNotIn('candidateCount', config)
            self.assertNotIn('temperature', config)
            self.assertEqual(config['responseFormat']['text']['schema'], ACTION_SCHEMA)
            self.assertEqual(config['thinkingConfig']['thinkingLevel'], 'low')
            self.assertNotIn('tools', body)

    def test_discovery_preserves_both_models_without_inference_or_key_disclosure(self):
        with patch('backend.ai_providers.ollama_client.local_models', return_value=['local:test']), patch.object(gemini_client.GEMINI_HTTP, 'open') as send:
            result = available_models()
        gemini = [option for option in result['options'] if option['provider'] == 'gemini']
        self.assertEqual({item['model'] for item in gemini}, {LITE, ORIGINAL})
        self.assertTrue(all(item['available'] for item in gemini))
        self.assertIn('groq', {item['provider'] for item in result['options']})
        self.assertIn('ollama', {item['provider'] for item in result['options']})
        self.assertEqual(gemini_client.GEMINI_MODEL, ORIGINAL)
        self.assertNotIn(SECRET, json.dumps(result))
        send.assert_not_called()
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}), patch('backend.ai_providers.ollama_client.local_models', return_value=[]):
            options = available_models()['options']
            self.assertTrue(all(not item['available'] for item in options if item['provider'] == 'gemini'))
            for model in (LITE, ORIGINAL):
                with self.assertRaisesRegex(ValueError, 'GEMINI_API_KEY'):
                    resolve_model('gemini', model)

    def test_unknown_models_and_endpoint_injection_are_rejected_before_network(self):
        for model in ('unapproved', 'gemini-3.5-flash-lite/../../other', 'https://other.example', [], None):
            with patch.object(gemini_client.GEMINI_HTTP, 'open') as send:
                with self.assertRaises(ValueError):
                    gemini_client.chat(model, [], format=ACTION_SCHEMA)
                with self.assertRaises(ValueError):
                    resolve_model('gemini', model)
                send.assert_not_called()

    def test_overview_and_followup_chat_work_for_both_explicit_models(self):
        for model in (LITE, ORIGINAL):
            with self.subTest(model=model):
                with patch.object(gemini_client.GEMINI_HTTP, 'open', return_value=response(action('Net sales are 70. Recommend reviewing Coffee and measuring results.'))):
                    overview = analyze_overview({**self.payload, 'model': model})
                self.assertEqual(overview['status'], 'answered')
                self.assertEqual(overview['model'], model)
                self.assertEqual(overview['evidence'][0]['rows'][0][:2], [3, 70])
                with patch.object(gemini_client.GEMINI_HTTP, 'open', return_value=response(action('Coffee recorded 40 in net sales. Review its costs before a promotion.'))):
                    chat = analyze_question({**self.payload, 'model': model, 'overviewId': overview['conversationId'], 'question': 'What supports that recommendation?'})
                self.assertEqual(chat['status'], 'answered')
                self.assertEqual(chat['model'], model)
                self.assertNotEqual(chat['conversationId'], overview['conversationId'])

    def test_model_switch_cannot_reuse_the_other_models_overview_or_conversation(self):
        with patch.object(gemini_client, 'chat', return_value=action('Original model overview marker. Recommend reviewing sales.')):
            overview = analyze_overview({**self.payload, 'model': ORIGINAL})
        calls = [action('', kind='query', sql='SELECT ROUND(SUM(Net_Sales),2) AS net_sales FROM sales'), action('Net sales are 70.')]
        with patch.object(gemini_client, 'chat', side_effect=calls) as send:
            chat = analyze_question({**self.payload, 'model': LITE,
                'overviewId': overview['conversationId'], 'conversationId': overview['conversationId'], 'question': 'Total net sales?'})
        self.assertEqual(chat['status'], 'answered')
        self.assertNotEqual(chat['conversationId'], overview['conversationId'])
        self.assertNotIn('Original model overview marker', json.dumps(send.call_args.args[1]))

    def test_lite_503_does_not_silently_switch_model_or_provider(self):
        error = HTTPError(gemini_client.GEMINI_API_BASE + LITE + ':generateContent', 503, SECRET, {}, io.BytesIO())
        with patch.object(gemini_client.GEMINI_HTTP, 'open', side_effect=error) as send, patch('backend.groq_client.chat') as groq, patch('backend.ollama_client.chat') as local:
            with self.assertRaisesRegex(gemini_client.GeminiError, 'HTTP 503'):
                analyze_overview({**self.payload, 'model': LITE})
        self.assertEqual(send.call_count, 1)
        groq.assert_not_called()
        local.assert_not_called()

    def test_network_error_messages_distinguish_timeouts_and_do_not_echo_details(self):
        errors = [(TimeoutError(SECRET), 504, 'timed out'),
                  (URLError(ssl.SSLCertVerificationError(1, SECRET)), 502, 'certificate'),
                  (ssl.SSLError(1, SECRET), 502, 'TLS'),
                  (URLError(socket.gaierror(11001, SECRET)), 502, 'resolve'),
                  (ConnectionResetError(SECRET), 502, 'interrupted'),
                  (URLError(SECRET), 502, 'network connection')]
        for error, status, wording in errors:
            with self.subTest(error=type(error).__name__), patch.object(gemini_client.GEMINI_HTTP, 'open', side_effect=error):
                with self.assertRaisesRegex(gemini_client.GeminiError, wording) as caught:
                    gemini_client.chat(LITE, [], format=ACTION_SCHEMA)
            self.assertEqual(caught.exception.status, status)
            self.assertNotIn(SECRET, str(caught.exception))

    def test_lite_model_passes_through_local_http_overview_and_chat_routes(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            with patch('backend.ai_providers.ollama_client.local_models', return_value=[]):
                connection.request('GET', '/api/models')
                status = json.loads(connection.getresponse().read())
            self.assertIn(LITE, [item['model'] for item in status['options']])
            for path, extra, text in [('/api/overview', {}, 'Net sales are 70. Recommend reviewing Coffee.'),
                                      ('/api/analyst', {'question': 'What supports that?', 'overviewId': None}, 'Coffee recorded 40. Review costs before a promotion.')]:
                if path == '/api/analyst':
                    extra['overviewId'] = result['conversationId']
                body = {**self.payload, 'model': LITE, **extra}
                with patch.object(gemini_client.GEMINI_HTTP, 'open', return_value=response(action(text))):
                    connection.request('POST', path, json.dumps(body), {'Content-Type': 'application/json', 'X-Dashboard-Token': TOKEN})
                    reply = connection.getresponse()
                    result = json.loads(reply.read())
                self.assertEqual(reply.status, 200, result)
                self.assertEqual(result['status'], 'answered')
                self.assertEqual(result['model'], LITE)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()

    def test_optional_fictional_check_accepts_the_lite_model(self):
        from scripts.check_gemini import main
        fake = {'status': 'answered'}
        with patch('scripts.check_gemini.analyze_overview', return_value=fake) as run, patch('sys.stdout', new_callable=io.StringIO):
            code = main(['--model', LITE])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.args[0]['model'], LITE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
