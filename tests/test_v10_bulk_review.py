"""Isolated bulk matching workflow: test physical/source preservation and fail-closed controls."""
import base64
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SMARTQUOTE_AUTH', 'off')
from fastapi.testclient import TestClient
import engine
import main


class BulkReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        local = patch.object(main, 'DB', Path(folder.name) / 'quote.sqlite')
        local.start()
        self.addCleanup(local.stop)
        self.client = TestClient(main.app)
        self.quote = self.client.post('/api/quotes').json()['quote']
        self.root = '/api/quotes/' + self.quote['id']
        data = ('Name,Make,Model,Description,Serial Number\n'
                'Newcastle,0,250G-0,R-Cycle - Recumbent Cycle,R001\n'
                'Newcastle,0,250G-0,R-Cycle - Recumbent Cycle,R002\n'
                'Newcastle,0,260G-0,Low Impact Elevation Treadmill,T001\n'
                'London,0,260G-0,Low Impact Elevation Treadmill,T002\n'
                'Newcastle,224B-AAB,224B,Group Cycle,C001\n').encode()
        self.assertEqual(self.client.post(self.root + '/import', json={
            'filename': 'complex.csv', 'content_base64': base64.b64encode(data).decode()
        }).status_code, 200)

    def groups(self):
        response = self.client.get(self.root + '/bulk-review/queue')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirmed(self, group, sku=None):
        sku = sku or next(c['sku'] for c in group['candidates'] if c['batch_selectable'])
        return {'asset_id': group['asset_id'], 'sku': sku,
                'verified': True, 'evidence': 'Physically checked actual machine and console against site register'}

    def test_queue_shows_distinct_sites_and_blocks_legacy_replacements(self):
        data = self.groups()
        self.assertGreaterEqual(data['total_groups'], 4)
        self.assertEqual(sum(g['rows'] for g in data['groups']), 5)
        newcastle = [g for g in data['groups'] if g['source_code'] == '250G-0']
        self.assertEqual(len(newcastle), 1)
        self.assertEqual(newcastle[0]['rows'], 2)
        treadmills = [g for g in data['groups'] if g['source_code'] == '260G-0']
        self.assertEqual(len(treadmills), 2)
        self.assertEqual({g['site'] for g in treadmills}, {'Newcastle', 'London'})
        old_cycle = next(g for g in data['groups'] if '224B' in g['source_code'])
        self.assertTrue(all(not c['batch_selectable'] for c in old_cycle['candidates']
                            if str(c['model']) not in ('', '224B')))

    def test_two_phase_staged_multi_group_commit_is_lossless(self):
        queue = self.groups()
        possible = [g for g in queue['groups'] if g['can_bulk_review']]
        actions = [self.confirmed(g) for g in possible[:2]]
        original = copy.deepcopy(self.client.get(self.root).json()['quote']['assets'])
        preview = self.client.post(self.root + '/bulk-review/preview', json={
            'token': queue['token'], 'actions': actions})
        self.assertEqual(preview.status_code, 200, preview.text)
        expected = preview.json()
        self.assertEqual(expected['groups'], 2)
        self.assertGreaterEqual(expected['source_rows'], 2)
        self.assertFalse(expected['commercially_approved'])
        self.assertEqual(self.client.get(self.root).json()['quote']['assets'], original)
        denied = self.client.post(self.root + '/bulk-review/apply', json={
            'token': queue['token'], 'actions': actions})
        self.assertEqual(denied.status_code, 400)
        apply = self.client.post(self.root + '/bulk-review/apply', json={
            'token': queue['token'], 'actions': actions, 'acknowledge': True})
        self.assertEqual(apply.status_code, 200, apply.text)
        new_assets = apply.json()['quote']['assets']
        self.assertEqual(len(new_assets), len(original))
        for before, after in zip(original, new_assets):
            self.assertEqual((before['id'], before.get('serial'), before.get('source_row'),
                              before.get('source_cells'), before.get('source_raw_columns')),
                             (after['id'], after.get('serial'), after.get('source_row'),
                              after.get('source_cells'), after.get('source_raw_columns')))
        self.assertEqual(len([a for a in new_assets if a.get('review_evidence')]), expected['source_rows'])
        self.assertEqual(apply.json()['quote']['pricing_approved'], False)
        self.assertEqual(self.client.post(self.root + '/bulk-review/apply', json={
            'token': queue['token'], 'actions': actions, 'acknowledge': True}).status_code, 409)
        events = self.client.get(self.root + '/history').json()['events']
        self.assertTrue(any(e['action'] == 'BULK_EQUIPMENT_REVIEW' for e in events))

    def test_invalid_groups_and_skus_are_atomic(self):
        before = self.client.get(self.root).json()['quote']
        q = self.groups()
        group = next(g for g in q['groups'] if g['can_bulk_review'])
        good = self.confirmed(group)
        wrong = {**good, 'sku': '228C-AAB'}
        for actions in ([good, good], [good, wrong], [dict(good, evidence='short')],
                        [dict(good, verified=False)], [dict(good, sku='NOT-AN-ITEM')]):
            result = self.client.post(self.root + '/bulk-review/apply', json={
                'token': q['token'], 'actions': actions, 'acknowledge': True})
            self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.client.get(self.root).json()['quote']['assets'], before['assets'])

    def test_stale_quote_or_catalogue_token_blocked(self):
        queue = self.groups()
        group = next(g for g in queue['groups'] if g['can_bulk_review'])
        action = self.confirmed(group)
        changed = self.client.put(self.root, json={'customer': 'A different client'})
        self.assertEqual(changed.status_code, 200)
        # Non-equipment edits not influencing prices do not invalidate this token.
        new_group = self.groups()
        self.assertEqual(queue['token'], new_group['token'])
        aset = self.client.get(self.root).json()['quote']['assets'][0]
        edit = self.client.put(self.root + '/assets/' + aset['id'], json={'display_name': 'Staff corrected name'})
        self.assertEqual(edit.status_code, 200, edit.text)
        failed = self.client.post(self.root + '/bulk-review/apply', json={
            'token': queue['token'], 'actions': [action], 'acknowledge': True})
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(self.client.get(self.root).json()['quote']['assets'][0].get('selected'), None)

    def test_batch_rejects_description_only_guess_and_unknown_model(self):
        from bulk_review import _bulk_eligibility
        confident = {'model': '873H', 'rrp': 2350.0, 'console': ''}
        ok, why = _bulk_eligibility({'name': 'Equipment', 'model': ''}, confident)
        self.assertFalse(ok)
        self.assertIn('No reliable original model', why)
        wrong, message = _bulk_eligibility({'name': 'Group Cycle', 'model': '224B'},
                                             {'model': '228C', 'rrp': 2200})
        self.assertFalse(wrong)
        self.assertIn('Different machine family', message)
        mismatched, reason = _bulk_eligibility({'model': '260G', 'console': 'Console 6'},
                                                {'model': '260G', 'console': 'Console 5',
                                                 'console_display': 'Console 5', 'rrp': 9300.0})
        self.assertFalse(mismatched)
        self.assertIn('console differs', reason)

    def test_queue_prioritises_machine_count_not_source_row_order(self):
        queue = self.groups()
        counts = [g['units'] for g in queue['groups']]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_pagination_and_review_queue_leave_quote_unchanged(self):
        original = self.client.get(self.root).json()['quote']['assets']
        first = self.client.get(self.root + '/bulk-review/queue?limit=2&offset=0').json()
        second = self.client.get(self.root + '/bulk-review/queue?limit=2&offset=2').json()
        self.assertEqual(first['shown'], 2)
        self.assertGreaterEqual(second['shown'], 1)
        self.assertEqual(first['token'], second['token'])
        self.assertEqual(original, self.client.get(self.root).json()['quote']['assets'])

if __name__ == '__main__':
    unittest.main()
