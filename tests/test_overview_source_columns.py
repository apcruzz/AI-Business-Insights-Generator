"""Overview template language must not become a user's source-column request."""
import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

from backend.ai_providers import AnalystModel
from backend.analyst_agent import AnalystRun, analyze_overview, required_source_columns
from backend.analyst_conversations import ConversationCache
from backend.analyst_datasets import DatasetCache
from backend.analyst_overview import OVERVIEW_QUESTION
from backend.gemini_client import GEMINI_MODEL
from backend.normalizer import normalize


class OverviewSourceColumnTests(unittest.TestCase):
    def setUp(self):
        self.cache = DatasetCache()
        for name, value in [('DATASETS', self.cache), ('CONVERSATIONS', ConversationCache())]:
            handle = patch('backend.analyst_agent.' + name, value)
            handle.start()
            self.addCleanup(handle.stop)

    def dataset(self, extra=None, map_date=False):
        source = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-02-01'],
                               'Product': ['Tea', 'Coffee', 'Tea'], 'Revenue': [10, 40, 20],
                               'Category': ['Drinks'] * 3, **(extra or {})})
        mapping = {'Product_Name': 'Product', 'Net_Sales': 'Revenue', 'Category': 'Category'}
        if map_date:
            mapping['Date'] = 'Date'
        normalized = normalize(source, mapping, 'Cafe', 'USD')
        normalized['filename'] = 'synthetic_overview.csv'
        key = self.cache.put(source, normalized, mapping)
        return {'datasetId': key, 'filters': {}, 'task': 'overview'}

    def run_overview(self, payload, provider='gemini'):
        return AnalystRun(payload, AnalystModel(provider, GEMINI_MODEL if provider == 'gemini' else 'synthetic-model'))

    def test_unmapped_date_does_not_block_an_overview_before_inference(self):
        payload = self.dataset()
        dataset = self.cache.get(payload['datasetId'])
        self.assertFalse(dataset.metadata['capabilities']['Date'])
        self.assertNotIn('Date', self.run_overview(payload).required_columns)
        reply = json.dumps({'action': 'answer', 'sql': '', 'answer': 'Net sales are 70. Recommend reviewing Coffee and measuring sales. Date coverage is unavailable.'})
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-key'}), patch('backend.gemini_client.chat', return_value=reply) as send:
            result = analyze_overview({**payload, 'provider': 'gemini', 'model': GEMINI_MODEL})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['selectedRows'], 3)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result['evidence'][0]['rows'], [[3, 70.0]])
        self.assertTrue(any('Product_Name' in item['query'] for item in result['evidence']))

    def test_template_collisions_do_not_require_unmapped_columns_in_each_query(self):
        payload = self.dataset({'Business': ['A'] * 3, 'Costs': ['unknown'] * 3, 'Inventory': ['unreviewed'] * 3})
        for provider in ('gemini', 'groq', 'ollama', 'browser_ollama'):
            with self.subTest(provider=provider):
                run = self.run_overview(payload, provider)
                self.assertEqual(run.evidence[0]['rows'], [[3, 70.0]])
                self.assertEqual(len(run.evidence), 3)

    def test_raw_date_values_are_not_used_as_reviewed_calendar_dates(self):
        payload = self.dataset({'Date': ['not reviewed', '01/02/03', 'unknown']})
        run = self.run_overview(payload)
        columns = {name for item in run.evidence for name in item['columns']}
        self.assertNotIn('first_recorded_date', columns)
        self.assertNotIn('last_recorded_date', columns)
        self.assertNotIn('recorded_days', columns)
        self.assertFalse(any('strftime' in item['query'] for item in run.evidence))

    def test_unmapped_profit_and_order_fields_are_not_promoted_to_metrics(self):
        payload = self.dataset({'Gross_Profit': ['9000', '9000', '9000'], 'Order_Key': ['A', 'B', 'C']})
        run = self.run_overview(payload)
        columns = run.evidence[0]['columns']
        self.assertNotIn('gross_profit', columns)
        self.assertNotIn('gross_margin_percent', columns)
        self.assertNotIn('orders', columns)
        self.assertEqual(run.evidence[0]['rows'], [[3, 70.0]])

    def test_reviewed_dates_keep_date_coverage_monthly_totals_and_filters(self):
        payload = self.dataset(map_date=True)
        run = self.run_overview({**payload, 'filters': {'from': '2026-01-01', 'to': '2026-01-31'}})
        totals = dict(zip(run.evidence[0]['columns'], run.evidence[0]['rows'][0]))
        self.assertEqual(totals['net_sales'], 50)
        self.assertEqual(totals['first_recorded_date'], '2026-01-01')
        self.assertEqual(totals['last_recorded_date'], '2026-01-02')
        self.assertEqual(totals['recorded_days'], 2)
        monthly = next(item for item in run.evidence if 'strftime' in item['query'])
        self.assertEqual(monthly['rows'], [['2026-01', 2, 50.0]])

    def test_user_question_still_requires_the_named_raw_date_column(self):
        payload = self.dataset()
        run = AnalystRun({**payload, 'task': 'chat', 'question': 'Show sales by Date.'}, AnalystModel('gemini', GEMINI_MODEL))
        with self.assertRaisesRegex(ValueError, 'does not use them: Date'):
            run.query('SELECT SUM(Net_Sales) FROM sales')
        result = run.query('SELECT Date, SUM(Net_Sales) FROM sales GROUP BY Date ORDER BY Date')
        self.assertEqual(result['rows'][0], ['2026-01-01', 10.0])

    def test_user_question_cannot_substitute_another_dimension(self):
        payload = self.dataset({'Milk Type': ['Oat', 'Whole', 'Oat']})
        run = AnalystRun({**payload, 'task': 'chat', 'question': 'Sales by milk types?'}, AnalystModel('gemini', GEMINI_MODEL))
        with self.assertRaisesRegex(ValueError, 'Milk Type'):
            run.query('SELECT Product_Name, SUM(Net_Sales) FROM sales GROUP BY Product_Name')
        result = run.query('SELECT "Milk Type", SUM(Net_Sales) FROM sales GROUP BY "Milk Type" ORDER BY "Milk Type"')
        self.assertEqual(result['rows'], [['Oat', 30.0], ['Whole', 40.0]])

    def test_overview_calculations_still_cannot_write_or_invent_constants(self):
        run = self.run_overview(self.dataset())
        for sql in ('DELETE FROM sales', 'SELECT 999 AS invented_total'):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                run.query(sql)


if __name__ == '__main__':
    unittest.main(verbosity=2)
