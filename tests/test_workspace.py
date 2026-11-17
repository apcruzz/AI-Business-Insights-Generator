"""Refresh recovery uses existing authenticated dataset ownership; fixtures contain fictional rows only."""
import base64
import unittest
from unittest.mock import patch

from backend.analyst_datasets import DATASETS
from tests import test_production as production_helpers
from tests import test_accounts as account_helpers

ORIGIN = production_helpers.ORIGIN


class WorkspaceTests(unittest.TestCase):
    setUpClass = classmethod(production_helpers.ProductionTests.setUpClass.__func__)
    setUp = production_helpers.ProductionTests.setUp
    headers = production_helpers.ProductionTests.headers
    get = production_helpers.ProductionTests.get
    token = production_helpers.ProductionTests.token
    post = production_helpers.ProductionTests.post
    payload = production_helpers.ProductionTests.payload
    upload = production_helpers.ProductionTests.upload

    def test_csv_and_excel_restore_normalized_rows_metadata_and_preferences(self):
        for excel in (False, True):
            payload = self.payload(excel)
            original = self.post(self.alice, '/api/analyze', payload).json
            key = original['datasetId']
            state = {'filters': {'from': '2026-01-02'}, 'chartIds': ['trend'], 'kpiIds': ['netSales'],
                     'chartTypes': {'trend': 'bar'}, 'page': 'detail', 'answerMode': '', 'sidebarCollapsed': True}
            saved = self.post(self.alice, '/api/workspace-save', {'datasetId': key, 'state': state, 'revision': 10})
            self.assertEqual(saved.status_code, 200, saved.json)
            result = self.post(self.alice, '/api/workspace-restore', {'datasetId': key})
            self.assertEqual(result.status_code, 200, result.json)
            self.assertEqual(result.json['dashboard'], original)
            self.assertEqual(result.json['state'], state)
            self.assertEqual(result.json['revision'], 10)
            # A slower old request cannot overwrite the last preferences after refresh.
            self.post(self.alice, '/api/workspace-save', {'datasetId': key, 'state': {}, 'revision': 9})
            self.assertEqual(self.post(self.alice, '/api/workspace-restore', {'datasetId': key}).json['state'], state)

    def test_restore_does_not_return_unmapped_source_columns(self):
        payload = self.payload()
        payload['file'] = base64.b64encode(b'Date,Revenue,Extra\n2026-01-01,10,Fictional extra field\n').decode()
        original = self.post(self.alice, '/api/analyze', payload).json
        result = self.post(self.alice, '/api/workspace-restore', {'datasetId': original['datasetId']})
        self.assertEqual(result.json['dashboard'], original)
        self.assertNotIn('Extra', result.json['dashboard']['rows'][0])

    def test_workspace_is_authenticated_csrf_protected_and_session_isolated(self):
        key = self.upload(self.alice)
        for action, value in [('workspace-restore', {'datasetId': key}),
                              ('workspace-save', {'datasetId': key, 'state': {}, 'revision': 1})]:
            path = '/api/' + action
            anonymous = self.app.test_client().post(path, base_url=ORIGIN, json=value)
            self.assertEqual(anonymous.status_code, 401)
            self.assertEqual(self.post(self.alice, path, value, origin='https://other.example').status_code, 403)
            self.assertEqual(self.post(self.alice, path, value, token='wrong').status_code, 403)
            for client, name in ((self.bob, 'bob'), (self.app.test_client(), 'alice')):
                denied = self.post(client, path, value, name)
                self.assertEqual(denied.status_code, 400, denied.json)
                self.assertNotIn('dashboard', denied.json)

    def test_expiry_restart_and_invalid_preferences_are_explicit(self):
        key = self.upload(self.alice)
        for state in ({'rows': []}, {'filters': {'unknown': 'x'}}, {'filters': []}, {'chartTypes': {'trend': []}},
                      {'chartIds': ['x'] * 4}, {'sidebarCollapsed': 'false'}, {'page': 'unknown'}, {'answerMode': 'x' * 17000}):
            response = self.post(self.alice, '/api/workspace-save', {'datasetId': key, 'state': state, 'revision': 1})
            self.assertEqual(response.status_code, 400, response.json)
        with patch.object(DATASETS, 'ttl', -1):
            response = self.post(self.alice, '/api/workspace-restore', {'datasetId': key})
        self.assertEqual(response.status_code, 400)
        self.assertIn('expired', response.json['error'])
        self.assertEqual(self.post(self.alice, '/api/workspace-restore', {'datasetId': 'unknown'}).status_code, 400)


class AccountWorkspaceTests(unittest.TestCase):
    setUp = account_helpers.AccountTests.setUp
    get = account_helpers.AccountTests.get
    bootstrap = account_helpers.AccountTests.bootstrap
    request = account_helpers.AccountTests.request
    register = account_helpers.AccountTests.register
    login = account_helpers.AccountTests.login
    remove_created_users = account_helpers.AccountTests.remove_created_users

    def test_account_workspace_revocation_and_other_account_denial(self):
        self.register(self.alice)
        payload = {'filename': 'fictional.csv', 'file': base64.b64encode(b'Date,Revenue\n2026-01-01,10\n').decode(),
                   'mapping': {'Date': 'Date', 'Net_Sales': 'Revenue'}}
        key = self.request(self.alice, '/api/analyze', payload).json['datasetId']
        self.assertEqual(self.request(self.alice, '/api/workspace-save', {'datasetId': key, 'state': {}, 'revision': 1}).status_code, 200)
        self.assertEqual(self.request(self.alice, '/api/workspace-restore', {'datasetId': key}).status_code, 200)
        self.register(self.bob, 'bob')
        self.assertEqual(self.request(self.bob, '/api/workspace-restore', {'datasetId': key}).status_code, 400)
        self.assertEqual(self.request(self.alice, '/api/auth/logout', {}).status_code, 200)
        self.assertNotIn(key, DATASETS._items)
        self.login(self.alice)
        self.assertEqual(self.request(self.alice, '/api/workspace-restore', {'datasetId': key}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
