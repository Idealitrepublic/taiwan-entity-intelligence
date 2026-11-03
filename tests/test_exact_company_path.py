import unittest
from unittest.mock import Mock
from src.entities.repository import EntityRepository
from src.entities.api import dispatch_entity_api

A, B, X, Y = [f'{i:08d}-1111-4111-8111-111111111111' for i in range(1, 5)]


def node(key, kind='Company'):
    return {'id': key, 'display_name': key, 'entity_type': kind}


def edge(key, source, target):
    return {'id': key, 'source': source, 'target': target, 'source_entity_id': source,
            'target_entity_id': target, 'primary_evidence_id': 'proof-'+key,
            'primary_evidence': {'id': 'proof-'+key, 'source_url': 'https://example.gov.tw/'+key}}


class ExactCompanyPathTests(unittest.TestCase):
    def repo(self, middle):
        repo = EntityRepository(transport=Mock(return_value=middle))
        repo.graph_neighbors = Mock(side_effect=lambda key, **_: {
            'nodes': [node(A), node(B), node(X, 'Person'), node(Y, 'GovernmentAgency')],
            'edges': [edge('ax', A, X), edge('ay', A, Y)] if key == A else [edge('bx', B, X), edge('by', B, Y)],
            'has_more': False})
        return repo

    def test_two_distinct_intermediaries_not_shorter_shared_node(self):
        repo = self.repo([edge('xy', Y, X)])
        result = repo.company_path_at_depth(A, B, depth=3)
        self.assertTrue(result['found'])
        self.assertEqual(result['depth'], 3)
        self.assertTrue(all(c.kwargs['limit'] == 25 for c in repo.graph_neighbors.call_args_list))
        self.assertEqual(len(result['segments']), 3)
        self.assertEqual(len({result['segments'][0]['from_entity']['id'],
                              *[s['to_entity']['id'] for s in result['segments']]}), 4)
        params = repo.transport.call_args.args[1]
        self.assertEqual(params['status'], 'eq.published')
        self.assertEqual(params['primary_evidence.publication_status'], 'eq.published')
        self.assertEqual(params['limit'], 201)
        self.assertIn('relationships_primary_evidence_id_fkey!inner', params['select'])

    def test_shared_node_does_not_satisfy_two_intermediaries(self):
        repo = self.repo([])
        self.assertFalse(repo.company_path_at_depth(A, B, depth=3)['found'])
        self.assertTrue(repo.company_path_at_depth(A, B, depth=2)['found'])

    def test_cycle_or_missing_evidence_never_fills_second_intermediary(self):
        for rows in [[edge('loop', X, X)], [dict(edge('xy', X, Y), primary_evidence={})]]:
            self.assertFalse(self.repo(rows).company_path_at_depth(A, B, depth=3)['found'])

    def test_api_exact_mode_and_legacy_remain_separate(self):
        repo = Mock()
        repo.company_path_at_depth.return_value = {'found': True, 'depth': 3}
        status, _, _ = dispatch_entity_api('/api/v1/paths', {
            'source': [A], 'target': [B], 'max_depth': ['3'], 'company_only': ['1'],
            'exact_depth': ['3']}, repo)
        self.assertEqual(status, 200)
        repo.company_path_at_depth.assert_called_once_with(A, B, depth=3)
        repo.company_relationship_path.assert_not_called()

    def test_truncation_reported_and_missing_endpoint_not_fabricated(self):
        repo = self.repo([])
        repo.graph_neighbors.return_value = None
        repo.graph_neighbors.side_effect = None
        self.assertIsNone(repo.company_path_at_depth(A, B, depth=3))
        repo = self.repo([edge('xy', X, Y)] * 201)
        self.assertTrue(repo.company_path_at_depth(A, B, depth=3)['truncated'])
