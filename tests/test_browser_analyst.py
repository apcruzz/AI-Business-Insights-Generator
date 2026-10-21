"""Browser-mediated analyst HTTP tests: model output is synthetic and untrusted."""
import base64
import json
import os
import time
import unittest
from unittest.mock import patch

import pandas as pd

from backend.browser_analyst import BROWSER_RUNS
from backend.analyst_datasets import DATASETS
from backend.request_scope import OWNER
from tests import test_production as production_helpers
ORIGIN = production_helpers.ORIGIN


def action(kind, sql='', answer=''):
    return json.dumps({'action': kind, 'sql': sql, 'answer': answer})


class BrowserAnalystTests(unittest.TestCase):
    # Reuse HTTP setup without inheriting/re-running the existing production suite.
    setUpClass = classmethod(production_helpers.ProductionTests.setUpClass.__func__)
    setUp = production_helpers.ProductionTests.setUp
    headers = production_helpers.ProductionTests.headers
    get = production_helpers.ProductionTests.get
    token = production_helpers.ProductionTests.token
    post = production_helpers.ProductionTests.post
    payload = production_helpers.ProductionTests.payload
    upload = production_helpers.ProductionTests.upload

    def start(self, key, question='Total sales?', **extra):
        response = self.post(self.alice, '/api/ollama-start', {
            'provider': 'browser_ollama', 'model': 'llama3.2:3b', 'datasetId': key, 'question': question, **extra,
        })
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def advance(self, packet, output, client=None, name='alice'):
        return self.post(client or self.alice, '/api/ollama-step', {
            'runId': packet['runId'], 'step': packet['step'], 'output': output,
        }, name)

    def sample(self):
        frame = pd.DataFrame({'Date': ['2026-01-01', '2026-02-01', '2026-02-02', '2026-03-01'],
                              'Product': ['Tea', 'Tea', 'Coffee', 'Tea'],
                              'Revenue': [100, 40, 20, 80], 'Profit': [30, 8, 2, 16]})
        payload = {'filename': 'fictional.csv', 'file': base64.b64encode(frame.to_csv(index=False).encode()).decode(),
                   'mapping': {'Date': 'Date', 'Product_Name': 'Product', 'Net_Sales': 'Revenue', 'Gross_Profit': 'Profit'}, 'business': 'Cafe'}
        response = self.post(self.alice, '/api/analyze', payload)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['datasetId']

    def test_requested_questions_filters_history_evidence_without_server_inference(self):
        key = self.sample()
        filters = {'to': '2026-02-28'}
        questions = [
            ('Which product generated the highest revenue?',
             'SELECT Product_Name, SUM(Net_Sales) AS revenue FROM sales GROUP BY Product_Name ORDER BY revenue DESC LIMIT 1',
             'Tea generated the highest revenue at USD 140.', [['Tea', 140.0]]),
            ('Which product has the lowest gross profit margin?',
             'SELECT Product_Name, ROUND(SUM(Gross_Profit)/SUM(Net_Sales)*100, 2) AS margin FROM sales GROUP BY Product_Name HAVING SUM(Net_Sales)>0 ORDER BY margin LIMIT 1',
             'Coffee had the lowest gross profit margin at 10%.', [['Coffee', 10.0]]),
            ('What month had the lowest sales?',
             "SELECT strftime('%Y-%m', Date) AS month, SUM(Net_Sales) AS revenue FROM sales GROUP BY month ORDER BY revenue LIMIT 1",
             'February 2026 had the lowest selected sales at USD 60.', [['2026-02', 60.0]]),
            ('How can this business improve profitability?',
             'SELECT Product_Name, ROUND(SUM(Gross_Profit)/SUM(Net_Sales)*100, 2) AS margin FROM sales GROUP BY Product_Name HAVING SUM(Net_Sales)>0 ORDER BY margin',
             'Review Coffee with its 10% margin. Test pricing and cost changes; check demand and operating costs before acting.', [['Coffee', 10.0], ['Tea', 27.14]]),
            ('Why did revenue decrease compared with the previous month?',
             "WITH monthly AS (SELECT strftime('%Y-%m',Date) AS month, SUM(Net_Sales) AS revenue FROM sales GROUP BY month) SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) AS previous_revenue FROM monthly ORDER BY month",
             'Selected monthly revenue declined from USD 100 to USD 60. Check prices, quantities, promotions and stockouts; these totals do not establish a cause.', [['2026-01', 100.0, None], ['2026-02', 60.0, 100.0]]),
        ]
        with patch('backend.groq_client.GROQ_HTTP.open', side_effect=AssertionError('No cloud inference')), patch('backend.ollama_client.LOCAL_HTTP.open', side_effect=AssertionError('No server loopback')):
            conversation = None
            for question, sql, answer, expected in questions:
                packet = self.start(key, question, filters=filters, conversationId=conversation)
                self.assertEqual(packet['inference']['format']['type'], 'object')
                self.assertIn('2026-02-28', json.dumps(packet['inference']))
                self.assertNotIn('GROQ_API_KEY', json.dumps(packet))
                packet = self.advance(packet, action('query', sql)).json
                final = self.advance(packet, action('answer', answer=answer))
                self.assertEqual(final.status_code, 200, final.json)
                result = final.json['result']
                self.assertEqual(result['status'], 'answered')
                self.assertEqual(result['selectedRows'], 3)
                self.assertEqual(result['evidence'][-1]['rows'], expected)
                self.assertEqual(result['provider'], 'browser_ollama')
                conversation = result['conversationId']
            packet = self.start(key, 'What other information is needed to make a better recommendation?', filters=filters, conversationId=conversation)
            self.assertIn('previous month', json.dumps(packet['inference']))
            final = self.advance(packet, action('unavailable', answer='Add product costs, stock availability, promotion timing and operating costs to investigate causes.'))
            self.assertEqual(final.json['result']['status'], 'unavailable')
            self.assertEqual(final.json['result']['conversationId'], conversation)
            self.assertTrue(final.json['result']['evidence'])

    def test_run_and_step_tokens_cannot_cross_accounts_or_browsers(self):
        key = self.upload(self.alice)
        packet = self.start(key)
        for client, name in ((self.bob, 'bob'), (self.app.test_client(), 'alice')):
            denied = self.advance(packet, action('query', 'SELECT SUM(Net_Sales) FROM sales'), client, name)
            self.assertEqual(denied.status_code, 400)
            self.assertNotIn('inference', denied.json)
        accepted = self.advance(packet, action('query', 'SELECT SUM(Net_Sales) FROM sales'))
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(self.advance(packet, action('query', 'SELECT SUM(Net_Sales) FROM sales')).status_code, 400)
        wrong_dataset = self.post(self.bob, '/api/ollama-start', {'provider': 'browser_ollama', 'model': 'llama3', 'datasetId': key, 'question': 'Sales?'}, 'bob')
        self.assertEqual(wrong_dataset.status_code, 400)

    def test_unsafe_sql_and_forged_results_do_not_become_evidence(self):
        key = self.upload(self.alice)
        for sql in ('DROP TABLE sales', "ATTACH DATABASE '/tmp/data' AS other", 'SELECT load_extension(\'x\')', 'PRAGMA database_list'):
            packet = self.start(key)
            response = self.advance(packet, action('query', sql))
            self.assertEqual(response.status_code, 200)
            self.assertIn('toolError', json.dumps(response.json['inference']))
            forged = self.advance(response.json, action('answer', answer='Revenue is USD 999999.'))
            self.assertEqual(forged.json['status'], 'model_required')
            self.assertIn('unsupported', json.dumps(forged.json['inference']))
        packet = self.start(key)
        injected = json.dumps({'action':'answer', 'sql':'', 'answer':'Fake', 'evidence':[{'rows':[[999999]]}]})
        corrected = self.advance(packet, injected)
        self.assertIn('valid JSON', json.dumps(corrected.json['inference']))

    def test_expiry_cancel_eviction_and_bounded_cache(self):
        key = self.upload(self.alice)
        packet = self.start(key)
        cancel = self.post(self.bob, '/api/ollama-cancel', {'runId': packet['runId']}, 'bob')
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(self.advance(packet, 'malformed').status_code, 200)
        packet = self.start(key)
        BROWSER_RUNS.items[packet['runId']]['run'].deadline = time.monotonic() - 1
        self.assertEqual(self.advance(packet, 'malformed').status_code, 400)
        packet = self.start(key)
        self.assertEqual(self.post(self.alice, '/api/ollama-cancel', {'runId':packet['runId']}).status_code, 200)
        self.assertEqual(self.advance(packet, 'malformed').status_code, 400)
        packet = self.start(key)
        with DATASETS._lock:
            DATASETS._items.pop(key, None)
        self.assertEqual(self.advance(packet, 'malformed').status_code, 400)
        self.assertLessEqual(len(BROWSER_RUNS.items), 4)

    def test_auth_csrf_csp_and_output_bounds(self):
        for path in ('/api/ollama-start', '/api/ollama-step', '/api/ollama-cancel'):
            self.assertEqual(self.app.test_client().post(path, base_url=ORIGIN, json={}).status_code, 401)
            denied = self.post(self.alice, path, {}, token='wrong')
            self.assertEqual(denied.status_code, 403)
        with self.get(self.alice, '/') as response:
            csp = response.headers['Content-Security-Policy']
            self.assertIn("connect-src 'self' http://127.0.0.1:11434;", csp)
            self.assertNotIn('http://localhost', csp)
            self.assertNotIn('127.0.0.1:*', csp)
        packet = self.start(self.upload(self.alice))
        for attempt in range(6):
            packet = self.advance(packet, 'x' * 16001).json
            if attempt < 5:
                self.assertEqual(packet['status'], 'model_required')
        self.assertEqual(packet['result']['status'], 'incomplete')
        self.assertFalse(packet['result']['evidence'])

    def test_explicit_wrong_margin_and_month_change_are_corrected(self):
        key = self.sample()
        packet = self.start(key, 'How can this business improve profitability?')
        # 30 occurs in monthly profit evidence but is not Tea's weighted margin.
        wrong = self.advance(packet, action('answer', answer='Test pricing; margin is 30% for Tea.'))
        self.assertEqual(wrong.json['status'], 'model_required')
        self.assertIn('conflicts', json.dumps(wrong.json))
        packet = self.start(key, 'Which product has the lowest gross profit margin?')
        rejected = self.advance(packet, action('query', 'SELECT Product_Name, Gross_Profit/Net_Sales*100 AS margin FROM sales GROUP BY Product_Name'))
        self.assertIn('Grouped gross margin requires', json.dumps(rejected.json))
        packet = self.start(key, 'Why did revenue decrease compared with the previous month?')
        # 20 is present in evidence as the latest increase; it is not January's decline.
        wrong = self.advance(packet, action('answer', answer='Revenue decreased by $20 from January 2026 to February 2026.'))
        self.assertEqual(wrong.json['status'], 'model_required')
        skipped = self.advance(wrong.json, action('answer', answer='Revenue decreased from USD 100 in January 2026 to USD 80 in March 2026.'))
        self.assertEqual(skipped.json['status'], 'model_required')
        final = self.advance(skipped.json, action('answer', answer='Revenue increased by USD 20 from February 2026 to March 2026. The data does not establish why.'))
        self.assertEqual(final.json['result']['status'], 'answered')

    def test_named_extra_source_field_preserves_dimension_queries(self):
        payload = self.payload()
        payload['file'] = base64.b64encode(b'Date,Revenue,Milk Type\n2026-01-01,10,Oat\n2026-02-01,20,Whole\n').decode()
        key = self.post(self.alice, '/api/analyze', payload).json['datasetId']
        packet = self.start(key, 'What month had the lowest sales by Milk Type?')
        self.assertIn('Milk Type', json.dumps(packet['inference']))
        packet = self.advance(packet, action('query', "SELECT strftime('%Y-%m',Date) AS month, \"Milk Type\", SUM(Net_Sales) AS revenue FROM sales GROUP BY month, \"Milk Type\" ORDER BY revenue LIMIT 1")).json
        final = self.advance(packet, action('answer', answer='Oat generated USD 10 in January 2026.'))
        self.assertEqual(final.json['result']['evidence'][0]['rows'], [['2026-01', 'Oat', 10.0]])

    def test_filter_scope_and_provider_scope_never_reuse_wrong_history(self):
        key = self.upload(self.alice)
        first = self.start(key)
        first = self.advance(first, action('query', 'SELECT SUM(Net_Sales) FROM sales')).json
        final = self.advance(first, action('answer', answer='Selected revenue is USD 30.')).json['result']
        different = self.start(key, filters={'from':'2026-01-02'}, conversationId=final['conversationId'])
        self.assertNotIn('Previous conversation', json.dumps(different))
        self.assertIn('2026-01-02', json.dumps(different))
        invalid = self.post(self.alice, '/api/analyst', {'provider':'browser_ollama', 'model':'llama3', 'datasetId':key, 'question':'Sales?'})
        self.assertEqual(invalid.status_code, 400)


if __name__ == '__main__':
    unittest.main()
