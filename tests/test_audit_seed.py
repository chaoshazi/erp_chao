'''写审计与演示数据回归。

审计是 AI 写回的可追溯依据：谁（人工/服务账号）、替谁（X-Actor-Id）、
改了什么（before/after）、走哪条请求（method/path）、用了哪个幂等键，都要落库。
'''

from __future__ import annotations

import unittest

from tests import support


class AuditTrailTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.service = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def _audit(self, **params) -> list[dict]:
        response = self.client.get('/api/v1/audit', params=params, headers=self.service)
        assert response.status_code == 200, response.text
        return response.json()['data']

    def test_create_is_audited_with_source_ai(self) -> None:
        created = support.data_of(
            self.client.post(
                '/api/v1/suppliers', json={'name': '审计供应商'}, headers=self.service
            )
        )
        rows = self._audit(object_type='suppliers', record_id=created['id'])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['method'], 'POST')
        self.assertEqual(row['source'], 'ai')
        self.assertEqual(row['actor_id'], 'ai-agent')
        self.assertEqual(row['actor_kind'], 'service')
        self.assertIsNone(row['before'])
        self.assertEqual(row['after']['name'], '审计供应商')
        self.assertIn('/api/v1/suppliers', row['path'])

    def test_update_records_before_and_after(self) -> None:
        self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'status': 'received'}, headers=self.service
        )
        row = self._audit(object_type='purchase_orders', record_id='po-0002')[0]
        self.assertEqual(row['method'], 'PATCH')
        self.assertEqual(row['before']['status'], 'approved')
        self.assertEqual(row['after']['status'], 'received')

    def test_delete_is_audited(self) -> None:
        self.client.delete('/api/v1/items/item-0002', headers=self.service)
        row = self._audit(object_type='items', record_id='item-0002')[0]
        self.assertEqual(row['method'], 'DELETE')
        self.assertIsNotNone(row['after'])

    def test_human_source_is_recorded(self) -> None:
        headers = support.login_headers(self.client, support.MANAGER_EMAIL)
        self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'note': '人工备注'}, headers=headers
        )
        row = self._audit(object_type='purchase_orders', record_id='po-0002')[0]
        self.assertEqual(row['source'], 'human')
        self.assertEqual(row['actor_id'], 'u-100')
        self.assertEqual(row['actor_kind'], 'user')

    def test_on_behalf_of_is_recorded(self) -> None:
        headers = support.service_headers(**{'X-Actor-Id': 'u-100'})
        self.client.patch('/api/v1/purchase_orders/po-0002', json={'note': '代操作'}, headers=headers)
        row = self._audit(object_type='purchase_orders', record_id='po-0002')[0]
        self.assertEqual(row['on_behalf_of'], 'u-100')
        self.assertEqual(row['actor_id'], 'ai-agent')

    def test_idempotency_key_is_recorded(self) -> None:
        headers = dict(self.service)
        headers['Idempotency-Key'] = 'audit-key-1'
        self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'note': '幂等备注'}, headers=headers
        )
        rows = self._audit(object_type='purchase_orders', record_id='po-0002')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['idempotency_key'], 'audit-key-1')

    def test_idempotent_replay_does_not_duplicate_audit(self) -> None:
        headers = dict(self.service)
        headers['Idempotency-Key'] = 'audit-key-2'
        body = {'note': '回放不重复审计'}
        self.client.patch('/api/v1/purchase_orders/po-0002', json=body, headers=headers)
        self.client.patch('/api/v1/purchase_orders/po-0002', json=body, headers=headers)
        self.assertEqual(len(self._audit(object_type='purchase_orders', record_id='po-0002')), 1)

    def test_password_change_is_audited_without_secret(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        self.client.post('/api/auth/password', json={'password': 'auditpass123'}, headers=headers)
        rows = self._audit(object_type='users', record_id='u-200')
        self.assertEqual(rows[0]['after'], {'password': 'changed'})
        self.assertNotIn('auditpass123', str(rows[0]))

    def test_audit_is_filtered_by_object_type(self) -> None:
        self.client.patch('/api/v1/purchase_orders/po-0002', json={'note': 'x'}, headers=self.service)
        self.client.patch('/api/v1/sales_orders/so-0002', json={'note': 'y'}, headers=self.service)
        only_sales = self._audit(object_type='sales_orders')
        self.assertEqual([row['object_type'] for row in only_sales], ['sales_orders'])
        self.assertEqual(only_sales[0]['record_id'], 'so-0002')


class SeedDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.service = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_every_seeded_id_is_present(self) -> None:
        for object_type, ids in support.SEED_IDS.items():
            with self.subTest(object_type=object_type):
                payload = self.client.get('/api/v1/' + object_type, headers=self.service).json()
                self.assertEqual(sorted(row['id'] for row in payload['data']), sorted(ids))

    def test_item_fields_round_trip(self) -> None:
        item = support.data_of(self.client.get('/api/v1/items/item-0001', headers=self.service))
        self.assertEqual(item['sku'], 'SKU-1001')
        self.assertEqual(item['name'], '工业路由器 R200')
        self.assertEqual(item['unit'], '台')
        self.assertEqual(item['price'], 1280.0)
        self.assertEqual(item['safety_stock'], 20.0)
        self.assertEqual(item['owner_id'], 'u-100')
        self.assertEqual(item['team_ids'], ['t-purchase'])
        self.assertEqual(item['version'], '1')
        self.assertEqual(item['updated_at'], '2026-09-02T01:00:00+00:00')

    def test_order_and_invoice_links(self) -> None:
        order = support.data_of(
            self.client.get('/api/v1/purchase_orders/po-0002', headers=self.service)
        )
        self.assertEqual(order['supplier_id'], 'sup-0002')
        self.assertEqual(order['status'], 'approved')
        self.assertEqual(order['amount'], 25750.0)
        invoice = support.data_of(
            self.client.get('/api/v1/invoices/inv-0002', headers=self.service)
        )
        self.assertEqual(invoice['direction'], 'payable')
        self.assertEqual(invoice['partner_id'], 'sup-0001')
        self.assertEqual(invoice['order_id'], 'po-0001')

    def test_users_have_roles_and_demo_password(self) -> None:
        rows = {
            row['id']: row
            for row in self.client.get('/api/v1/users', headers=self.service).json()['data']
        }
        self.assertEqual(rows['u-100']['role'], 'manager')
        self.assertEqual(rows['u-100']['team_ids'], ['t-purchase'])
        self.assertEqual(rows['u-200']['role'], 'staff')
        self.assertEqual(rows['u-300']['role'], 'manager')
        self.assertEqual(rows['u-300']['team_ids'], ['t-finance'])
        support.login(self.client, support.FINANCE_EMAIL, support.DEMO_PASSWORD)

    def test_bootstrap_admin_exists(self) -> None:
        support.login(self.client, support.ADMIN_EMAIL, support.ADMIN_PASSWORD)

    def test_stats_overview_matches_seed(self) -> None:
        stats = self.client.get('/api/v1/stats/overview', headers=self.service).json()
        counts = stats['counts']
        self.assertEqual(counts['items'], 2)
        self.assertEqual(counts['purchase_orders'], 2)
        self.assertEqual(counts['purchase_order_lines'], 3)
        self.assertEqual(counts['sales_orders'], 2)
        self.assertEqual(counts['stock_moves'], 5)
        self.assertEqual(counts['invoices'], 2)
        self.assertEqual(stats['purchase_amount'], 111750.0)
        self.assertEqual(stats['sales_amount'], 108800.0)
        self.assertEqual(stats['open_purchase_orders'], 1)
        self.assertEqual(stats['open_sales_orders'], 1)
        self.assertEqual(stats['open_invoices'], 2)
        self.assertEqual(stats['receivable_open'], 76800.0)
        self.assertEqual(stats['payable_open'], 86000.0)
        self.assertEqual(stats['stock_value'], 34400.0)
        self.assertEqual(stats['low_stock_count'], 1)
        self.assertEqual(stats['low_stock_items'][0]['id'], 'item-0001')
        self.assertEqual(stats['low_stock_items'][0]['balance'], 0.0)
        self.assertEqual(len(stats['recent_moves']), 5)

    def test_stats_follow_row_level_permissions(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        stats = self.client.get('/api/v1/stats/overview', headers=headers).json()
        self.assertEqual(stats['counts']['items'], 0)
        self.assertEqual(stats['counts']['sales_orders'], 1)
        self.assertEqual(stats['sales_amount'], 76800.0)
        self.assertEqual(stats['purchase_amount'], 0.0)

    def test_meta_reports_object_types_and_enums(self) -> None:
        payload = self.client.get('/api/v1/meta', headers=self.service).json()
        self.assertEqual(len(payload['object_names']), 11)
        self.assertEqual(payload['enums']['invoice_direction'][0]['label'], '应收')
        self.assertEqual(payload['role_labels']['staff'], '职员')

    def test_health_lists_object_types(self) -> None:
        payload = self.client.get('/health').json()
        self.assertEqual(payload['storage'], 'sqlite')
        self.assertIn('purchase_orders', payload['object_types'])
        self.assertFalse(payload['serve_web'])


if __name__ == '__main__':
    unittest.main()