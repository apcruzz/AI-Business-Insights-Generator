"""Analyst integration/security checks; model calls mocked for deterministic assertions."""
import base64
import io
import json
import unittest
from unittest.mock import patch

import pandas as pd
from backend.analyst_datasets import DatasetCache, select_rows
from backend.analyst_query import QueryTool
from backend.analyst_agent import analyze_question, required_source_columns, supported_numbers
from backend.data_loader import frame_from_payload
from backend.normalizer import normalize


class AnalystTests(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame({'Date':['2025-01-02','2025-02-03','2025-02-03','2026-01-02'],
            'Product':['Tea','Coffee','Tea','Tea'], 'Revenue':[10,40,20,60], 'Quantity':[1,4,2,6],
            'Hour':[8,14,20,9], 'Milk Type':['Oat','Whole','Oat','Almond']})
        self.mapping = {'Date':'Date','Product_Name':'Product','Net_Sales':'Revenue','Quantity':'Quantity','Hour':'Hour'}
        self.result = normalize(self.source, self.mapping, 'Cafe')
        self.result['filename'] = 'sales.csv'
        self.cache = DatasetCache()
        self.key = self.cache.put(self.source, self.result, self.mapping)
        self.dataset = self.cache.get(self.key)

    def test_month_ranking_and_ties_use_all_years_and_rows(self):
        tool = QueryTool(select_rows(self.dataset, {}))
        try:
            result = tool.run("WITH monthly AS (SELECT strftime('%Y-%m', Date) AS month, SUM(Net_Sales) AS revenue FROM sales GROUP BY month) SELECT * FROM monthly WHERE revenue = (SELECT MAX(revenue) FROM monthly) ORDER BY month")
            self.assertEqual(result['rows'], [['2025-02',60.0],['2026-01',60.0]])
        finally:
            tool.close()

    def test_filters_match_dashboard_and_do_not_mutate_cache(self):
        selected = select_rows(self.dataset, {'from':'2025-02-01','to':'2025-02-28','product':'Tea','weekday':'1','period':'evening'})
        self.assertEqual(selected['Net_Sales'].sum(), 20)
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(self.cache.get(self.key).frame), 4)
        self.assertNotIn('Weather', selected.columns)
        self.assertNotIn('Order_Key', selected.columns)
        with self.assertRaises(ValueError):
            select_rows(self.dataset, {'period':'invalid'})

    def test_extra_source_columns_are_queryable(self):
        tool = QueryTool(select_rows(self.dataset, {}))
        try:
            result = tool.run('SELECT "Milk Type" AS milk, SUM(Net_Sales) AS revenue FROM sales GROUP BY "Milk Type" ORDER BY revenue DESC')
            self.assertEqual(result['rows'], [['Almond',60.0],['Whole',40.0],['Oat',30.0]])
            self.assertEqual(self.dataset.source_columns['Milk Type'], 'Milk Type')
        finally:
            tool.close()

    def test_queries_cannot_write_read_files_or_inspect_other_tables(self):
        tool = QueryTool(select_rows(self.dataset, {}))
        try:
            for sql in ["SELECT 999 AS invented_revenue", "DELETE FROM sales", "UPDATE sales SET Net_Sales=0", "DROP TABLE sales", "PRAGMA database_list", "ATTACH DATABASE '/tmp/evil' AS evil", "SELECT * FROM sqlite_master", "SELECT load_extension('/tmp/evil')", "SELECT readfile('/etc/passwd')", "SELECT randomblob(999999999)", "SELECT * FROM sales; DELETE FROM sales", "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT * FROM x"]:
                with self.subTest(sql=sql), self.assertRaises(ValueError):
                    tool.run(sql)
            self.assertEqual(tool.run('SELECT SUM(Net_Sales) FROM sales')['rows'], [[130.0]])
        finally:
            tool.close()

    def test_explicit_source_dimension_and_invented_numbers(self):
        required = required_source_columns(self.dataset, 'Sales by milk types?')
        self.assertEqual(required, ['Milk Type'])
        tool = QueryTool(select_rows(self.dataset, {}))
        try:
            with self.assertRaisesRegex(ValueError, 'Milk Type'):
                tool.run('SELECT Product_Name, SUM(Net_Sales) FROM sales GROUP BY Product_Name', required)
        finally:
            tool.close()
        self.assertFalse(supported_numbers('Sales were 999.', [{'rows':[[130]]}], 'What were sales?'))
        self.assertTrue(supported_numbers('Sales were USD 130.', [{'rows':[[130]]}], 'What were sales?'))

    def test_result_limits_and_expired_dataset(self):
        tool = QueryTool(pd.DataFrame({'value': range(100)}))
        try:
            result = tool.run('SELECT value FROM sales')
            self.assertEqual(len(result['rows']),30)
            self.assertTrue(result['truncated'])
        finally:
            tool.close()
        cache = DatasetCache(max_items=1)
        first = cache.put(self.source,self.result,self.mapping)
        second = cache.put(self.source,self.result,self.mapping)
        with self.assertRaises(ValueError): cache.get(first)
        self.assertEqual(len(cache.get(second).frame),4)
        expired = DatasetCache(ttl=-1)
        key = expired.put(self.source,self.result,self.mapping)
        with self.assertRaises(ValueError): expired.get(key)

    def test_csv_and_excel_use_same_validated_rows(self):
        csv = self.source.to_csv(index=False).encode()
        stream = io.BytesIO()
        self.source.to_excel(stream,index=False,sheet_name='Sales')
        for name, raw in [('sales.csv',csv),('sales.xlsx',stream.getvalue())]:
            frame, _, _ = frame_from_payload({'filename':name,'file':base64.b64encode(raw).decode(),'sheet':'Sales'})
            result = normalize(frame,self.mapping,'Cafe')
            result['filename'] = name
            key = self.cache.put(frame,result,self.mapping)
            self.assertEqual(select_rows(self.cache.get(key),{})['Net_Sales'].sum(),130)

    def run_agent(self, actions, filters=None):
        with patch('backend.analyst_agent.DATASETS',self.cache), patch('backend.analyst_agent.local_models',return_value=['llama3']), patch('backend.analyst_agent.chat',side_effect=[json.dumps(a) for a in actions]) as chat:
            result = analyze_question({'model':'llama3','datasetId':self.key,'question':'Which month had the highest sales revenue?','filters':filters or {}})
            return result, chat

    def test_model_queries_data_before_answering(self):
        result, calls = self.run_agent([
            {'action':'query','sql':"SELECT strftime('%Y-%m',Date) AS month, SUM(Net_Sales) AS revenue FROM sales GROUP BY month ORDER BY revenue DESC, month LIMIT 1",'answer':''},
            {'action':'answer','sql':'','answer':'February 2025 had USD 60 in selected sales.'},
        ], {'to':'2025-12-31'})
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['selectedRows'],3)
        self.assertEqual(result['evidence'][0]['rows'],[['2025-02',60.0]])
        self.assertEqual(calls.call_count,2)

    def test_unverified_answer_is_rejected_and_bad_query_can_be_corrected(self):
        result, calls = self.run_agent([
            {'action':'answer','answer':'Sales were 999.','sql':''},
            {'action':'query','sql':'SELECT SUM(nonexistent) FROM sales','answer':''},
            {'action':'query','sql':'SELECT SUM(Net_Sales) AS revenue FROM sales','answer':''},
            {'action':'answer','answer':'Selected sales total USD 130.','sql':''},
        ])
        self.assertEqual(result['status'],'answered')
        self.assertEqual(len(result['evidence']),1)
        self.assertEqual(calls.call_count,4)

    def test_growth_rejects_ranking_and_followup_receives_context(self):
        actions = [
            {'action':'answer','sql':'','answer':'The highest month had sales of USD 60.'},
            {'action':'answer','sql':'','answer':'Tea generated USD 90. Test promoting Tea; review costs before discounting.'},
            {'action':'answer','sql':'','answer':'Promote Tea because its USD 90 revenue shows existing demand. Test the promotion and measure profit; costs are missing.'},
        ]
        with patch('backend.analyst_agent.DATASETS',self.cache), patch('backend.analyst_agent.local_models',return_value=['llama3']), patch('backend.analyst_agent.chat',side_effect=[json.dumps(a) for a in actions]) as model:
            first = analyze_question({'model':'llama3','datasetId':self.key,'question':'How can we grow the business?'})
            self.assertEqual(first['status'], 'answered')
            self.assertIn('Test promoting Tea',first['answer'])
            self.assertEqual(model.call_count,2)
            second = analyze_question({'model':'llama3','datasetId':self.key,'question':'Why that recommendation?', 'conversationId':first['conversationId']})
            self.assertEqual(second['conversationId'],first['conversationId'])
            self.assertEqual(second['status'],'answered')
            prompt = json.dumps(model.call_args.args[1])
            self.assertIn('How can we grow the business?',prompt)
            self.assertIn('Test promoting Tea',prompt)

    def test_conversation_scope_expiry_and_size(self):
        from backend.analyst_conversations import ConversationCache
        cache = ConversationCache(max_items=2)
        key, _ = cache.open(None,self.key,{},'llama3')
        for i in range(6): cache.append(key, 'Why?', 'Answer', [])
        _, turns = cache.open(key,self.key,{},'llama3')
        self.assertEqual(len(turns),4)
        for dataset, filters, model in [('other',{},'llama3'),(self.key,{'product':'Tea'},'llama3'),(self.key,{},'other')]:
            fresh, turns = cache.open(key,dataset,filters,model)
            self.assertNotEqual(fresh,key)
            self.assertEqual(turns,[])
        expired = ConversationCache(ttl=-1)
        key,_ = expired.open(None,self.key,{},'llama3')
        self.assertNotEqual(expired.open(key,self.key,{},'llama3')[0],key)
        self.assertTrue(supported_numbers('1. Test promotion; sales were USD 130.', [{'rows':[[130]]}], 'Advice?'))

    def test_failures_empty_and_missing_data_are_honest(self):
        result,_ = self.run_agent([{'action':'unavailable','sql':'','answer':'Cost data is not supplied.'}])
        self.assertEqual(result['status'],'unavailable')
        result,_ = self.run_agent([], {'product':'missing'})
        self.assertEqual(result['status'],'empty')
        with patch('backend.analyst_agent.DATASETS',self.cache), patch('backend.analyst_agent.local_models',return_value=['llama3']), patch('backend.analyst_agent.chat',side_effect=TimeoutError):
            result=analyze_question({'model':'llama3','datasetId':self.key,'question':'Sales?'})
            self.assertEqual(result['status'],'incomplete')
            self.assertEqual(result['evidence'],[])


if __name__ == '__main__': unittest.main()
