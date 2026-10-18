"""Groq contract, error handling, and real dataset/query integration without API calls."""
import base64
import io
import json
import os
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

import pandas as pd

from backend import groq_client
from backend.ai_providers import available_models, resolve_model
from backend.analyst_agent import ACTION_SCHEMA, analyze_question
from backend.analyst_datasets import DatasetCache
from backend.config import GROQ_MODEL, GROQ_CHAT_URL
from backend.data_loader import frame_from_payload
from backend.normalizer import normalize
from backend.server import Handler, TOKEN


def action(kind, sql='', answer=''):
    return json.dumps({'action': kind, 'sql': sql, 'answer': answer})


def response(content, finish_reason='stop'):
    stream = io.BytesIO(json.dumps({'choices': [{'message': {'content': content},
                                               'finish_reason': finish_reason}]}).encode())
    return stream


class GroqTransportTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'GROQ_API_KEY': 'test-secret-never-expose'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_contract_uses_server_key_strict_schema_and_fixed_endpoint(self):
        reply = action('answer', answer='Costs are missing.')
        with patch.object(groq_client.GROQ_HTTP, 'open', return_value=response(reply)) as send:
            self.assertEqual(groq_client.chat(GROQ_MODEL, [{'role': 'user', 'content': 'Question'}], format=ACTION_SCHEMA), reply)
        request = send.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, GROQ_CHAT_URL)
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret-never-expose')
        self.assertEqual(request.get_header('User-agent'), 'FreeBusinessDashboard/1.0')
        self.assertEqual(request.get_header('Accept'), 'application/json')
        self.assertEqual(body['model'], GROQ_MODEL)
        self.assertEqual(body['response_format']['json_schema']['schema'], ACTION_SCHEMA)
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertNotIn('tools', body)
        self.assertNotIn('test-secret', json.dumps(body))
        self.assertFalse(body['include_reasoning'])
        self.assertEqual(send.call_args.kwargs['timeout'], 60)

    def test_credentials_and_model_are_checked_before_network(self):
        with patch.object(groq_client.GROQ_HTTP, 'open') as send:
            with patch.dict(os.environ, {'GROQ_API_KEY': ' '}), self.assertRaisesRegex(ValueError, 'GROQ_API_KEY'):
                groq_client.chat(GROQ_MODEL, [], format=ACTION_SCHEMA)
            with self.assertRaises(ValueError):
                groq_client.chat('unapproved-model', [], format=ACTION_SCHEMA)
            send.assert_not_called()

    def test_provider_errors_are_actionable_and_do_not_echo_upstream_secrets(self):
        for code, message in [(401, 'API key \\(HTTP 401\\)'), (403, 'denied access \\(HTTP 403\\)'), (429, '17 seconds'),
                              (413, 'too large'), (400, 'HTTP 400'), (500, 'unavailable')]:
            error = HTTPError(GROQ_CHAT_URL, code, 'test-secret-never-expose',
                              {'Retry-After': '17'}, io.BytesIO(b'sensitive prompt and key'))
            with self.subTest(code=code), patch.object(groq_client.GROQ_HTTP, 'open', side_effect=error) as send:
                with self.assertRaisesRegex(groq_client.GroqError, message) as caught:
                    groq_client.chat(GROQ_MODEL, [], format=ACTION_SCHEMA)
                self.assertNotIn('test-secret', str(caught.exception))
                self.assertNotIn('sensitive', str(caught.exception))
                self.assertEqual(caught.exception.status, 429 if code == 429 else 502)
                self.assertEqual(send.call_count, 1)

    def test_bad_request_diagnostic_redacts_secrets_and_stays_out_of_browser_error(self):
        body = json.dumps({'error': {
            'code': 'invalid_request_error', 'param': 'response_format',
            'message': 'Unsupported response_format test-secret-never-expose gsk_anotherSecret Bearer another-key',
            'failed_generation': 'private dataset values must not appear',
        }}).encode()
        error = HTTPError(GROQ_CHAT_URL, 400, 'Bad request', {}, io.BytesIO(body))
        with patch.object(groq_client.GROQ_HTTP, 'open', side_effect=error):
            with self.assertRaises(groq_client.GroqError) as caught:
                groq_client.chat(GROQ_MODEL, [], format=ACTION_SCHEMA)
        self.assertIn('response_format', caught.exception.diagnostic)
        self.assertNotIn('Unsupported response_format', str(caught.exception))
        for private in ('test-secret-never-expose', 'gsk_anotherSecret', 'another-key', 'private dataset values'):
            self.assertNotIn(private, caught.exception.diagnostic)
        self.assertLessEqual(len(groq_client.safe_diagnostic({'message': 'x' * 10000}, 'key')), 510)

    def test_request_rejections_distinguish_generation_context_and_settings(self):
        cases = [
            ({'code': 'json_validate_failed'}, 'valid analysis response', True),
            ({'code': 'tool_use_failed'}, 'valid analysis response', True),
            ({'code': 'context_length_exceeded'}, 'context is too large', False),
            ({'param': 'response_format.json_schema'}, 'response_format request setting', False),
            ({'param': 'messages[3].content'}, 'messages request setting', False),
            ({'code': 'unknown_private_code', 'param': 'private_column_name'}, 'unclassified', False),
            ({'code': ['json_validate_failed'], 'param': {}}, 'unclassified', False),
        ]
        for detail, message, retryable in cases:
            error = groq_client.bad_request_error({**detail, 'message': 'private sales data'}, 'test-key')
            self.assertIn(message, str(error))
            self.assertEqual(error.retryable_output, retryable)
            self.assertNotIn('private', str(error))

    def test_connection_check_requires_environment_key_without_network(self):
        from scripts.check_groq import main
        with patch.dict(os.environ, {'GROQ_API_KEY': ''}), patch.object(groq_client.GROQ_HTTP, 'open') as send, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(main(), 1)
            self.assertIn('not set in this terminal', output.getvalue())
            send.assert_not_called()

    def test_gateway_and_model_permission_errors_are_not_mislabeled_as_bad_keys(self):
        bodies = [
            (b'error code: 1010', 'before API authentication'),
            (json.dumps({'error': {'code': 'model_permission_blocked_org', 'message': 'sensitive prompt and key'}}).encode(), 'organization model permissions'),
            (json.dumps({'error': {'code': 'model_permission_blocked_project', 'message': 'sensitive prompt and key'}}).encode(), 'project model permissions'),
            (b'null', 'denied access'),
            (b'{"error": []}', 'denied access'),
        ]
        for body, expected in bodies:
            error = HTTPError(GROQ_CHAT_URL, 403, 'Forbidden', {}, io.BytesIO(body))
            with self.subTest(expected=expected), patch.object(groq_client.GROQ_HTTP, 'open', side_effect=error):
                with self.assertRaisesRegex(groq_client.GroqError, expected) as caught:
                    groq_client.chat(GROQ_MODEL, [], format=ACTION_SCHEMA)
                self.assertNotIn('sensitive', str(caught.exception))
                self.assertNotIn('rejected the API key', str(caught.exception))

    def test_network_invalid_and_truncated_responses_stop_cleanly(self):
        for error in [TimeoutError(), URLError('private network details')]:
            with patch.object(groq_client.GROQ_HTTP, 'open', side_effect=error):
                with self.assertRaisesRegex(groq_client.GroqError, 'reach Groq'):
                    groq_client.chat(GROQ_MODEL, [], format=ACTION_SCHEMA)
        for raw in [io.BytesIO(b'not json'), io.BytesIO(b'{}'), response(None), response('{}', 'length')]:
            with patch.object(groq_client.GROQ_HTTP, 'open', return_value=raw):
                with self.assertRaises(groq_client.GroqError):
                    groq_client.chat(GROQ_MODEL, [], format=ACTION_SCHEMA)

    def test_discovery_and_cloud_selection_do_not_require_ollama_or_contact_groq(self):
        with patch('backend.ai_providers.ollama_client.local_models', side_effect=OSError), patch.object(groq_client.GROQ_HTTP, 'open') as send:
            status = available_models()
            self.assertEqual(status['models'], [])
            self.assertTrue(status['groqConfigured'])
            self.assertTrue(status['options'][0]['available'])
            self.assertNotIn('test-secret', json.dumps(status))
            client = resolve_model('groq', GROQ_MODEL)
            self.assertEqual(client.provider, 'groq')
            send.assert_not_called()
        with patch.dict(os.environ, {'GROQ_API_KEY': ''}), patch('backend.ai_providers.ollama_client.local_models', return_value=['llama3']):
            self.assertFalse(available_models()['options'][-1]['available'])
            self.assertEqual(resolve_model('ollama', 'llama3').provider, 'ollama')
            with self.assertRaisesRegex(ValueError, 'GROQ_API_KEY'):
                resolve_model('groq', GROQ_MODEL)
        for provider, model in [('other', GROQ_MODEL), ('groq', 'unknown'), ('groq', None)]:
            with self.assertRaises(ValueError):
                resolve_model(provider, model)


class GroqAnalystTests(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame({'Date': ['2026-01-01', '2026-02-01', '2026-03-01', '2026-03-01'],
                                    'Revenue': [10, 20, 60, 40], 'Milk Type': ['Oat', 'Oat', 'Oat', 'Whole']})
        self.mapping = {'Date': 'Date', 'Net_Sales': 'Revenue'}
        self.cache = DatasetCache()
        self.environment = patch.dict(os.environ, {'GROQ_API_KEY': 'test-key'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.datasets = patch('backend.analyst_agent.DATASETS', self.cache)
        self.datasets.start()
        self.addCleanup(self.datasets.stop)

    def upload(self, excel=False):
        stream = io.BytesIO()
        if excel:
            self.source.to_excel(stream, index=False, sheet_name='Sales')
        else:
            stream.write(self.source.to_csv(index=False).encode())
        name = 'sales.xlsx' if excel else 'sales.csv'
        source, _, _ = frame_from_payload({'filename': name, 'file': base64.b64encode(stream.getvalue()).decode(), 'sheet': 'Sales'})
        result = normalize(source, self.mapping, 'Cafe')
        result['filename'] = name
        return self.cache.put(source, result, self.mapping)

    def ask(self, key, question, **options):
        return analyze_question({'provider': 'groq', 'model': GROQ_MODEL, 'datasetId': key, 'question': question, **options})

    def test_csv_excel_extra_columns_full_filtered_data_and_followup(self):
        for excel in (False, True):
            key = self.upload(excel)
            replies = [action('query', 'SELECT "Milk Type", SUM(Net_Sales) AS revenue FROM sales GROUP BY "Milk Type"'),
                       action('answer', answer='Oat generated USD 80; Whole generated USD 40.'),
                       action('answer', answer='Oat had higher revenue at USD 80. Demand and price could both contribute; these totals do not establish a cause.')]
            with patch.object(groq_client, 'chat', side_effect=replies) as chat, patch('backend.ai_providers.ollama_client.local_models', side_effect=AssertionError('Groq must be independent')):
                first = self.ask(key, 'Sales by Milk Type?', filters={'from': '2026-02-01'})
                self.assertEqual(first['selectedRows'], 3)
                self.assertEqual(first['status'], 'answered')
                self.assertEqual(first['evidence'][0]['rows'], [['Oat', 80.0], ['Whole', 40.0]])
                self.assertEqual(first['provider'], 'groq')
                second = self.ask(key, 'Why is that higher?', filters={'from': '2026-02-01'}, conversationId=first['conversationId'])
                self.assertEqual(second['conversationId'], first['conversationId'])
                prompt = json.dumps(chat.call_args.args[1])
                self.assertIn('Sales by Milk Type?', prompt)
                self.assertIn('80.0', prompt)

    def test_complex_question_runs_multiple_calculations_and_corrects_unsafe_query(self):
        key = self.upload()
        sql = '''WITH monthly AS (
            SELECT strftime('%Y-%m', Date) AS month, SUM(Net_Sales) AS revenue FROM sales GROUP BY month
        ) SELECT month, revenue, revenue - LAG(revenue) OVER (ORDER BY month) AS change FROM monthly'''
        replies = [action('query', 'DROP TABLE sales'), action('query', sql),
                   action('query', 'SELECT SUM(Net_Sales) AS total FROM sales'),
                   action('answer', answer='March revenue was USD 100, up USD 80 from February. Total sales were USD 130.')]
        with patch.object(groq_client, 'chat', side_effect=replies) as chat:
            result = self.ask(key, 'Compare monthly changes and total revenue.')
            self.assertEqual(result['status'], 'answered')
            self.assertEqual(result['evidence'][0]['rows'][-1], ['2026-03', 100.0, 80.0])
            self.assertEqual(len(result['evidence']), 2)
            self.assertIn('toolError', json.dumps(chat.call_args.args[1]))
            self.assertEqual(self.cache.get(key).frame['Net_Sales'].sum(), 130)

    def test_switching_provider_or_filters_starts_fresh_conversation(self):
        key = self.upload()
        with patch.object(groq_client, 'chat', return_value=action('unavailable', answer='Costs are missing.')):
            first = self.ask(key, 'Profit?')
            changed = self.ask(key, 'Profit?', filters={'from': '2026-02-01'}, conversationId=first['conversationId'])
            self.assertNotEqual(changed['conversationId'], first['conversationId'])
        # Identical model names still cannot carry cloud conversation history into Ollama.
        with patch('backend.ai_providers.ollama_client.local_models', return_value=[GROQ_MODEL]), patch('backend.ai_providers.ollama_client.chat', return_value=action('unavailable', answer='Costs are missing.')) as chat:
            local = analyze_question({'provider': 'ollama', 'model': GROQ_MODEL, 'datasetId': key,
                                      'question': 'Why?', 'conversationId': first['conversationId']})
            self.assertNotEqual(local['conversationId'], first['conversationId'])
            self.assertNotIn('Previous conversation', json.dumps(chat.call_args.args[1]))

    def test_http_rate_limit_is_not_retried_or_converted_into_fake_answer(self):
        payload = {'provider': 'groq', 'model': GROQ_MODEL, 'datasetId': self.upload(), 'question': 'Total sales?'}
        body = json.dumps(payload).encode()
        handler = Handler.__new__(Handler)
        handler.path = '/api/analyst'
        handler.headers = {'X-Dashboard-Token': TOKEN, 'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.send_json = Mock()
        with patch.object(groq_client, 'chat', side_effect=groq_client.GroqError('Groq usage limit reached.', 429)) as chat:
            handler.do_POST()
            handler.send_json.assert_called_once_with({'error': 'Groq usage limit reached.'}, 429)
            self.assertEqual(chat.call_count, 1)
        # A failure releases the query slot so the next question can run.
        with patch.object(groq_client, 'chat', return_value=action('unavailable', answer='Costs are missing.')):
            self.assertEqual(self.ask(payload['datasetId'], 'Profit?')['status'], 'unavailable')

    def test_generation_failure_is_corrected_once_before_query_and_answer(self):
        key = self.upload()
        rejected = groq_client.bad_request_error({'code': 'json_validate_failed'}, 'test-key')
        replies = [rejected, action('query', 'SELECT SUM(Net_Sales) AS revenue FROM sales'),
                   action('answer', answer='Selected sales total USD 130.')]
        with patch.object(groq_client, 'chat', side_effect=replies) as chat:
            result = self.ask(key, 'What were total sales?')
            self.assertEqual(result['status'], 'answered')
            self.assertEqual(result['evidence'][0]['rows'], [[130.0]])
            self.assertEqual(chat.call_count, 3)
            self.assertIn('previous response was rejected', json.dumps(chat.call_args.args[1]))

    def test_repeated_generation_errors_and_other_bad_requests_do_not_loop(self):
        key = self.upload()
        for detail, expected_calls in [({'code': 'tool_use_failed'}, 2),
                                       ({'code': 'context_length_exceeded'}, 1),
                                       ({'param': 'response_format'}, 1), ({}, 1)]:
            error = groq_client.bad_request_error(detail, 'test-key')
            with patch.object(groq_client, 'chat', side_effect=error) as chat:
                with self.assertRaises(groq_client.GroqError):
                    self.ask(key, 'Total sales?')
                self.assertEqual(chat.call_count, expected_calls)


if __name__ == '__main__':
    unittest.main()
