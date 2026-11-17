"""Compact reviews remain checked, scoped, and bounded when a provider stalls."""
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pandas as pd

from backend import gemini_client, ollama_client
from backend.ai_providers import AnalystModel
from backend.analyst_agent import AnalystRun, analyze_overview, analyze_question
from backend.analyst_conversations import ConversationCache
from backend.analyst_datasets import DatasetCache
from backend.analyst_overview import OVERVIEW_SCHEMA
from backend.analyst_query import QueryTool
from backend.normalizer import normalize


ANSWER = json.dumps({'action': 'answer', 'sql': '', 'answer':
                     'Net sales are 70. Recommend reviewing Coffee and checking costs before a promotion.'})


class FastOverviewTests(unittest.TestCase):
    def setUp(self):
        self.cache, self.conversations = DatasetCache(), ConversationCache()
        source = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-02-01'],
                               'Product': ['Tea', 'Coffee', 'Tea'], 'Revenue': [10, 40, 20],
                               **{f'Unrelated private field {i}': ['unneeded source example'] * 3 for i in range(25)}})
        mapping = {'Date': 'Date', 'Product_Name': 'Product', 'Net_Sales': 'Revenue'}
        normalized = normalize(source, mapping, 'Cafe', 'USD')
        normalized['filename'] = 'fictional.csv'
        self.key = self.cache.put(source, normalized, mapping)
        self.payload = {'provider': 'gemini', 'model': gemini_client.GEMINI_MODEL,
                        'datasetId': self.key, 'filters': {}}
        for handle in (patch('backend.analyst_agent.DATASETS', self.cache),
                       patch('backend.analyst_agent.CONVERSATIONS', self.conversations),
                       patch.dict(os.environ, {'GEMINI_API_KEY': 'fictional-key'})):
            handle.start()
            self.addCleanup(handle.stop)

    def run_overview(self):
        return AnalystRun({**self.payload, 'task': 'overview'}, AnalystModel('gemini', gemini_client.GEMINI_MODEL))

    def test_review_prompt_avoids_raw_column_samples_and_the_sql_planner(self):
        overview = self.run_overview()
        chat = AnalystRun({**self.payload, 'question': 'What is in the data?'}, overview.client)
        compact, full = json.dumps(overview.messages), json.dumps(chat.messages)
        self.assertLess(len(compact), len(full) / 2)
        self.assertNotIn('unneeded source example', compact)
        self.assertIn('unneeded source example', full)
        self.assertNotIn('Allowed SQL functions', compact)
        self.assertEqual(overview.evidence[0]['rows'][0][:2], [3, 70])
        self.assertEqual(overview.inference()['format'], OVERVIEW_SCHEMA)
        self.assertEqual(chat.inference()['format']['properties']['action']['enum'], ['query', 'answer', 'unavailable'])

    def test_one_valid_narration_finishes_and_seeds_a_scoped_conversation(self):
        with patch.object(gemini_client, 'chat', return_value=ANSWER) as send:
            result = analyze_overview(self.payload)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(len(self.conversations.items[result['conversationId']]['turns']), 1)
        self.assertEqual(result['evidence'][0]['rows'][0][:2], [3, 70])

    def test_aggregates_share_one_temporary_table_with_only_reviewed_columns(self):
        with patch('backend.analyst_agent.QueryTool', wraps=QueryTool) as factory:
            run = self.run_overview()
        self.assertEqual(factory.call_count, 1)
        columns = set(factory.call_args.args[0].columns)
        self.assertEqual(columns, {'Date', 'Product_Name', 'Net_Sales'})
        self.assertEqual(len(run.evidence), 3)
        self.assertEqual(run.evidence[0]['rows'][0][:2], [3, 70])

    def test_measurement_and_verification_actions_do_not_waste_a_correction(self):
        for advice in ('Verify product costs before testing a promotion.',
                       'Measure product costs to establish gross profit.',
                       'Check coverage before changing staffing.',
                       'Compare costs before changing prices.'):
            with self.subTest(advice=advice):
                run = self.run_overview()
                run.accept(json.dumps({'action': 'answer', 'sql': '', 'answer': 'Net sales are 70. ' + advice}))
                self.assertEqual(run.result['status'], 'answered')
                self.assertEqual(run.attempts, 1)

    def test_rankings_alone_still_do_not_satisfy_a_request_for_next_steps(self):
        run = self.run_overview()
        run.accept(json.dumps({'action': 'answer', 'sql': '', 'answer': 'Coffee has 40 in sales and Tea has 30.'}))
        self.assertIsNone(run.result)
        self.assertIn('practical actions', run.messages[-1]['content'])

    def test_temporary_table_closes_even_if_a_calculation_fails(self):
        with patch('backend.analyst_agent.QueryTool') as factory:
            factory.return_value.run.side_effect = ValueError('Synthetic query failure')
            with self.assertRaisesRegex(ValueError, 'Synthetic query failure'):
                self.run_overview()
            factory.return_value.close.assert_called_once()

    def test_model_cannot_add_sql_rounds_to_a_precalculated_review(self):
        run = self.run_overview()
        evidence = list(run.evidence)
        with patch.object(run, 'query') as query:
            run.accept(json.dumps({'action': 'query', 'sql': 'SELECT SUM(Net_Sales) FROM sales', 'answer': ''}))
            query.assert_not_called()
        self.assertEqual(run.evidence, evidence)
        run.accept(json.dumps({'action': 'answer', 'sql': '', 'answer': 'Net sales are 99999. Review costs.'}))
        self.assertIsNone(run.inference())
        self.assertEqual(run.result['status'], 'incomplete')
        self.assertNotIn('99999', run.result['answer'])
        self.assertEqual(self.conversations.items[run.token]['turns'], [])

    def test_transient_timeout_retries_once_on_the_same_model_without_fallback(self):
        timeout = gemini_client.connection_error(TimeoutError())
        with patch.object(gemini_client, 'chat', side_effect=[timeout, ANSWER]) as send, \
             patch('backend.analyst_agent.time.sleep') as sleep, \
             patch('backend.groq_client.chat') as groq, patch.object(ollama_client, 'chat') as local:
            result = analyze_overview(self.payload)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(send.call_count, 2)
        self.assertTrue(all(call.args[0] == self.payload['model'] for call in send.call_args_list))
        self.assertTrue(all(0 < call.kwargs['timeout'] <= 25 for call in send.call_args_list))
        sleep.assert_called_once()
        groq.assert_not_called()
        local.assert_not_called()

    def test_repeated_timeouts_stop_without_saving_a_fictional_success(self):
        with patch.object(gemini_client, 'chat', side_effect=gemini_client.connection_error(TimeoutError())) as send, \
             patch('backend.analyst_agent.time.sleep'), self.assertRaises(gemini_client.GeminiError) as error:
            analyze_overview(self.payload)
        self.assertEqual(error.exception.status, 504)
        self.assertEqual(send.call_count, 2)
        self.assertTrue(all(not item['turns'] for item in self.conversations.items.values()))

    def test_expired_retry_budget_does_not_start_another_request(self):
        clock = [100.0]
        def late_timeout(*args, **kwargs):
            clock[0] += 66
            raise gemini_client.connection_error(TimeoutError())
        with patch('backend.analyst_agent.time.monotonic', side_effect=lambda: clock[0]), \
             patch.object(gemini_client, 'chat', side_effect=late_timeout) as send, \
             patch('backend.analyst_agent.time.sleep') as sleep, self.assertRaises(gemini_client.GeminiError):
            analyze_overview(self.payload)
        self.assertEqual(send.call_count, 1)
        sleep.assert_not_called()

    def test_authentication_quota_validation_and_manual_chat_are_not_retried(self):
        for overview, error in ((True, gemini_client.GeminiError('Authentication failed.')),
                                (True, gemini_client.GeminiError('Quota exceeded.', 429)),
                                (True, gemini_client.GeminiError('Output was not usable.')),
                                (False, gemini_client.connection_error(TimeoutError()))):
            with self.subTest(overview=overview, error=str(error)), \
                 patch.object(gemini_client, 'chat', side_effect=error) as send, \
                 patch('backend.analyst_agent.time.sleep') as sleep, self.assertRaises(gemini_client.GeminiError):
                (analyze_overview if overview else analyze_question)({**self.payload, 'question': 'Net sales?'})
            self.assertEqual(send.call_count, 1)
            sleep.assert_not_called()

    def test_top_group_prompt_is_small_but_ui_evidence_still_has_all_query_rows(self):
        from backend.analyst_overview import overview_evidence
        evidence = [{'query': 'SELECT Product_Name FROM sales GROUP BY Product_Name',
                     'columns': ['dimension', 'net_sales'],
                     'rows': [['A' * 200, 99], ['Tea', 30], ['Coffee', 40], ['Other', 1]]}]
        compact = overview_evidence(evidence)
        self.assertEqual(compact[0]['group'], 'Product_Name')
        self.assertEqual(compact[0]['rows'], [['Tea', 30], ['Coffee', 40]])
        self.assertTrue(compact[0]['additionalGroupsOmitted'])
        self.assertEqual(len(evidence[0]['rows']), 4)


class OverviewTransportTests(unittest.TestCase):
    def test_gemini_uses_model_supported_reasoning_and_shorter_output_budget(self):
        for model, thinking in [('gemini-3.5-flash-lite', 'minimal'), ('gemini-3.8-flash', 'low')]:
            reply = io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': ANSWER}]}}]}).encode())
            with self.subTest(model=model), patch.dict(os.environ, {'GEMINI_API_KEY': 'fictional-key'}), \
                 patch.object(gemini_client.GEMINI_HTTP, 'open', return_value=reply) as send:
                gemini_client.chat(model, [], format=OVERVIEW_SCHEMA, overview=True, num_predict=450, timeout=25)
            config = json.loads(send.call_args.args[0].data)['generationConfig']
            self.assertEqual(config['thinkingConfig']['thinkingLevel'], thinking)
            self.assertFalse(config['thinkingConfig']['includeThoughts'])
            self.assertEqual(config['maxOutputTokens'], 2048)
            self.assertEqual(config['responseFormat']['text']['schema'], OVERVIEW_SCHEMA)

    def test_only_transient_network_and_server_errors_are_retryable(self):
        for code in (400, 401, 403, 404, 429, 500, 502, 503, 504):
            error = HTTPError('https://example.invalid', code, 'private', {}, io.BytesIO(b'private response'))
            with self.subTest(code=code), patch.dict(os.environ, {'GEMINI_API_KEY': 'fictional-key'}), \
                 patch.object(gemini_client.GEMINI_HTTP, 'open', side_effect=error), \
                 self.assertRaises(gemini_client.GeminiError) as caught:
                gemini_client.chat(gemini_client.GEMINI_MODEL, [], format=OVERVIEW_SCHEMA, overview=True)
            self.assertEqual(caught.exception.retryable, code in (500, 502, 503, 504))
            self.assertNotIn('private', str(caught.exception))
        self.assertTrue(gemini_client.connection_error(URLError(TimeoutError())).retryable)
        self.assertFalse(gemini_client.connection_error(URLError('unrecognized network error')).retryable)

    def test_server_ollama_keeps_manual_chat_capacity_and_uses_smaller_review_context(self):
        for overview, context in ((True, 4096), (False, 8192)):
            with self.subTest(overview=overview), patch.dict(os.environ, {'APP_ENV': 'development'}), \
                 patch.object(ollama_client.LOCAL_HTTP, 'open', return_value=io.BytesIO(json.dumps({'message': {'content': ANSWER}}).encode())) as send:
                ollama_client.chat('llama3.2:3b', [], format=OVERVIEW_SCHEMA, overview=overview, num_predict=450 if overview else 1200)
            body = json.loads(send.call_args.args[0].data)
            self.assertEqual(body['options']['num_ctx'], context)
            self.assertEqual(body['keep_alive'] if overview else body.get('keep_alive'), '5m' if overview else None)


if __name__ == '__main__':
    unittest.main()
