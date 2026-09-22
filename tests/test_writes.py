'''写入路径回归：幂等、乐观锁、软删除、字段校验与未知字段兜底。

这些行为是 AI 侧写回的安全边界：重试要安全、并发要能发现冲突、
软删除不能把数据真删掉、模型生成的脏字段不能把写库打挂。
'''

from __future__ import annotations

import unittest

from tests import support


class IdempotencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def _create(self, key: str, body: dict | None = None):
        headers = dict(self.headers)
        headers['Idempotency-Key'] = key
        return self.client.post(
            '/api/v1/purchase_orders',
            json=body
            or {
                'code': 'PO-IDEM-1',
                'supplier_id': 'sup-0001',
                'order_date': '2026-09-20',
                'status': 'draft',
                'amount': 1000,
            },
            headers=headers,
        )

    def test_same_key_same_body_replays_first_response(self) -> None:
        first = self._create('po-key-1')
        second = self._create('po-key-1')
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()['data']['id'], second.json()['data']['id'])
        listed = self.client.get(
            '/api/v1/purchase_orders', params={'q': 'PO-IDEM-1'}, headers=self.headers
        ).json()
        self.assertEqual(listed['total'], 1)

    def test_same_key_different_body_conflicts(self) -> None:
        self._create('po-key-2')
        response = self._create(
            'po-key-2',
            {
                'code': 'PO-IDEM-2',
                'supplier_id': 'sup-0001',
                'order_date': '2026-09-21',
                'status': 'draft',
            },
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_different_keys_create_two_records(self) -> None:
        first = self._create('po-key-3')
        second = self._create('po-key-4')
        self.assertNotEqual(first.json()['data']['id'], second.json()['data']['id'])

    def test_idempotent_update_and_delete(self) -> None:
        headers = dict(self.headers)
        headers['Idempotency-Key'] = 'patch-1'
        first = self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'status': 'received'}, headers=headers
        )
        second = self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'status': 'received'}, headers=headers
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()['data']['version'], first.json()['data']['version'])
        delete_headers = dict(self.headers)
        delete_headers['Idempotency-Key'] = 'del-1'
        self.client.delete('/api/v1/purchase_orders/po-0002', headers=delete_headers)
        replay = self.client.delete('/api/v1/purchase_orders/po-0002', headers=delete_headers)
        self.assertEqual(replay.status_code, 200, replay.text)


class VersionLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_stale_version_is_conflict(self) -> None:
        response = self.client.patch(
            '/api/v1/sales_orders/so-0001',
            json={'version': 1, 'status': 'closed'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_current_version_is_accepted_and_bumped(self) -> None:
        current = support.data_of(
            self.client.get('/api/v1/sales_orders/so-0001', headers=self.headers)
        )
        response = self.client.patch(
            '/api/v1/sales_orders/so-0001',
            json={'version': current['version'], 'status': 'closed'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()['data']
        self.assertEqual(updated['status'], 'closed')
        self.assertTrue(updated['version'].isdigit())
        self.assertNotEqual(updated['version'], '1')

    def test_far_future_version_is_conflict(self) -> None:
        response = self.client.patch(
            '/api/v1/sales_orders/so-0001',
            json={'version': 99, 'status': 'closed'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_missing_version_on_update_is_allowed(self) -> None:
        response = self.client.patch(
            '/api/v1/sales_orders/so-0001', json={'note': '无版本更新'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['note'], '无版本更新')


class SoftDeleteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_delete_hides_record_everywhere(self) -> None:
        response = self.client.delete('/api/v1/items/item-0002', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['id'], 'item-0002')
        gone = self.client.get('/api/v1/items/item-0002', headers=self.headers)
        self.assertEqual(gone.status_code, 404, gone.text)
        listed = self.client.get('/api/v1/items', headers=self.headers).json()
        self.assertNotIn('item-0002', [row['id'] for row in listed['data']])

    def test_admin_can_list_deleted_records(self) -> None:
        self.client.delete('/api/v1/items/item-0002', headers=self.headers)
        payload = self.client.get(
            '/api/v1/items', params={'include_deleted': 'true'}, headers=self.headers
        ).json()
        self.assertIn('item-0002', [row['id'] for row in payload['data']])

    def test_write_to_deleted_record_is_404(self) -> None:
        self.client.delete('/api/v1/items/item-0002', headers=self.headers)
        patched = self.client.patch(
            '/api/v1/items/item-0002', json={'name': '已删除'}, headers=self.headers
        )
        self.assertEqual(patched.status_code, 404, patched.text)

    def test_delete_unknown_record_is_404(self) -> None:
        response = self.client.delete('/api/v1/items/item-9999', headers=self.headers)
        self.assertEqual(response.status_code, 404, response.text)


class ValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_missing_required_fields_are_reported(self) -> None:
        response = self.client.post('/api/v1/items', json={'sku': 'SKU-NO-NAME'}, headers=self.headers)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('name', response.json()['detail'])

    def test_bad_email_is_rejected(self) -> None:
        response = self.client.post(
            '/api/v1/suppliers', json={'name': '坏邮箱供应商', 'email': 'not-an-email'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_duplicate_user_email_conflicts(self) -> None:
        response = self.client.post(
            '/api/v1/users',
            json={'name': '重复邮箱', 'email': 'chenxiao@example.com', 'password': 'duplicate123'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_unknown_object_type_is_404(self) -> None:
        response = self.client.post('/api/v1/deals', json={'name': 'x'}, headers=self.headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_unknown_fields_are_kept_but_do_not_break_contract(self) -> None:
        created = self.client.post(
            '/api/v1/customers',
            json={'name': '扩展字段客户', 'tax_no': '91310000XYZ'},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        record = created.json()['data']
        self.assertEqual(record['tax_no'], '91310000XYZ')
        self.assertIn('name', record)

    def test_patch_ignores_id_and_created_at(self) -> None:
        response = self.client.patch(
            '/api/v1/customers/cus-0001',
            json={'id': 'cus-hacked', 'created_at': '1999-01-01T00:00:00+00:00', 'contact': '新联系人'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        record = response.json()['data']
        self.assertEqual(record['id'], 'cus-0001')
        self.assertNotEqual(record['created_at'], '1999-01-01T00:00:00+00:00')
        self.assertEqual(record['contact'], '新联系人')

    def test_team_ids_alias_is_accepted(self) -> None:
        created = self.client.post(
            '/api/v1/warehouses',
            json={'code': 'WH-ALIAS', 'name': '别名团队仓', 'team_ids': ['t-sales']},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()['data']['team_ids'], ['t-sales'])

    def test_quantity_accepts_decimal_strings(self) -> None:
        created = self.client.post(
            '/api/v1/stock_moves',
            json={
                'item_id': 'item-0001',
                'warehouse_id': 'wh-0001',
                'kind': 'adjust',
                'quantity': '12.50',
                'occurred_at': '2026-09-21T01:00:00+00:00',
            },
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()['data']['quantity'], 12.5)


if __name__ == '__main__':
    unittest.main()