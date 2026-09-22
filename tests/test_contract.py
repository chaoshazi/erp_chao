'''对接契约回归：接口形状与字段名必须与 AI 能力层逐字一致。

字段名镜像 D:/codex/app/integrations/erp/field_map.py 的 ERP_FIELD_MAP。
改这里之前先确认那边同步改过，否则 AI 侧会把字段塞进 _extra。
'''

from __future__ import annotations

import unittest

from tests import support

# object_type -> 业务字段名（不含公共列）
OBJECT_FIELDS = {
    'items': ('sku', 'name', 'category', 'spec', 'unit', 'price', 'cost', 'safety_stock', 'is_active'),
    'suppliers': (
        'name',
        'contact',
        'phone',
        'email',
        'region',
        'payment_terms',
        'grade',
        'is_active',
    ),
    'customers': (
        'name',
        'contact',
        'phone',
        'email',
        'region',
        'credit_limit',
        'payment_terms',
        'grade',
        'is_active',
    ),
    'warehouses': ('code', 'name', 'location', 'keeper', 'is_active'),
    'purchase_orders': (
        'code',
        'supplier_id',
        'warehouse_id',
        'order_date',
        'expected_date',
        'status',
        'currency',
        'amount',
        'note',
    ),
    'purchase_order_lines': (
        'order_id',
        'item_id',
        'quantity',
        'unit_price',
        'received_quantity',
        'amount',
    ),
    'sales_orders': (
        'code',
        'customer_id',
        'warehouse_id',
        'order_date',
        'delivery_date',
        'status',
        'currency',
        'amount',
        'note',
    ),
    'sales_order_lines': (
        'order_id',
        'item_id',
        'quantity',
        'unit_price',
        'shipped_quantity',
        'amount',
    ),
    'stock_moves': ('item_id', 'warehouse_id', 'kind', 'quantity', 'occurred_at', 'reference', 'note'),
    'invoices': (
        'code',
        'direction',
        'partner_id',
        'order_id',
        'amount',
        'tax_amount',
        'issued_at',
        'due_at',
        'status',
        'note',
    ),
    # users 的归属同样走团队数组：出参是 team_ids，team_id 属内部列
    'users': ('name', 'email', 'role', 'is_active'),
}

# 每条记录都要有的公共列
COMMON_FIELDS = ('id', 'version', 'updated_at', 'owner_id', 'team_ids')

# 内部列绝不能出现在出参里
INTERNAL_FIELDS = ('tenant_id', 'team_id', 'created_by', 'deleted_at', 'password', 'password_hash')

SAMPLE_PAYLOADS = {
    'items': {
        'sku': 'SKU-9001',
        'name': '契约测试物料',
        'category': '测试分类',
        'spec': '规格 A',
        'unit': '件',
        'price': 199.5,
        'cost': 120,
        'safety_stock': 10,
        'is_active': True,
    },
    'suppliers': {
        'name': '契约测试供应商',
        'contact': '张三',
        'phone': '13900000001',
        'email': 'supplier@example.com',
        'region': '华东',
        'payment_terms': '月结 30 天',
        'grade': 'B',
        'is_active': True,
    },
    'customers': {
        'name': '契约测试客户',
        'contact': '李四',
        'phone': '13900000002',
        'email': 'customer@example.com',
        'region': '华北',
        'credit_limit': 200000,
        'payment_terms': '月结 45 天',
        'grade': 'A',
        'is_active': True,
    },
    'warehouses': {
        'code': 'WH-TEST',
        'name': '契约测试仓',
        'location': '杭州市余杭区',
        'keeper': '王五',
        'is_active': True,
    },
    'purchase_orders': {
        'code': 'PO-2026-9001',
        'supplier_id': 'sup-0001',
        'warehouse_id': 'wh-0001',
        'order_date': '2026-09-20',
        'expected_date': '2026-09-27',
        'status': 'submitted',
        'currency': 'CNY',
        'amount': 12345.67,
        'note': '契约测试采购单',
    },
    'purchase_order_lines': {
        'order_id': 'po-0001',
        'item_id': 'item-0001',
        'quantity': 5,
        'unit_price': 860,
        'received_quantity': 0,
        'amount': 4300,
    },
    'sales_orders': {
        'code': 'SO-2026-9001',
        'customer_id': 'cus-0001',
        'warehouse_id': 'wh-0001',
        'order_date': '2026-09-20',
        'delivery_date': '2026-09-30',
        'status': 'confirmed',
        'currency': 'CNY',
        'amount': 25600,
        'note': '契约测试销售单',
    },
    'sales_order_lines': {
        'order_id': 'so-0001',
        'item_id': 'item-0001',
        'quantity': 20,
        'unit_price': 1280,
        'shipped_quantity': 0,
        'amount': 25600,
    },
    'stock_moves': {
        'item_id': 'item-0001',
        'warehouse_id': 'wh-0001',
        'kind': 'adjust',
        'quantity': -3,
        'occurred_at': '2026-09-20T02:00:00+00:00',
        'reference': 'ST-2026-0001',
        'note': '盘点调整',
    },
    'invoices': {
        'code': 'INV-2026-9001',
        'direction': 'receivable',
        'partner_id': 'cus-0001',
        'order_id': 'so-0001',
        'amount': 25600,
        'tax_amount': 3328,
        'issued_at': '2026-09-20',
        'due_at': '2026-10-20',
        'status': 'issued',
        'note': '契约测试发票',
    },
    'users': {
        'name': '契约测试员工',
        'email': 'contract-user@example.com',
        'team_id': 't-sales',
        'role': 'staff',
        'password': 'contract12345',
    },
}

ENUM_FIELDS = (
    ('suppliers', 'grade', 'A'),
    ('customers', 'grade', 'C'),
    ('purchase_orders', 'status', 'draft'),
    ('sales_orders', 'status', 'draft'),
    ('stock_moves', 'kind', 'adjust'),
    ('invoices', 'direction', 'payable'),
    ('invoices', 'status', 'partial'),
    ('users', 'role', 'manager'),
)


class ContractShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_meta_lists_exactly_the_contract_objects(self) -> None:
        response = self.client.get('/api/v1/meta', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        names = {item['name'] for item in payload['objects']}
        self.assertEqual(names, set(OBJECT_FIELDS))
        self.assertEqual(set(payload['object_names']), set(OBJECT_FIELDS))

    def test_meta_exposes_enum_labels(self) -> None:
        payload = self.client.get('/api/v1/meta', headers=self.headers).json()
        self.assertEqual(
            {item['value'] for item in payload['enums']['po_status']},
            {'draft', 'submitted', 'approved', 'partial', 'received', 'cancelled'},
        )
        grade = {item['value']: item['label'] for item in payload['enums']['grade']}
        self.assertEqual(grade['A'], '优秀')
        self.assertEqual(set(payload['roles']), {'admin', 'manager', 'staff'})

    def test_meta_declares_list_and_filterable_fields(self) -> None:
        payload = self.client.get('/api/v1/meta', headers=self.headers).json()
        objects = {item['name']: item for item in payload['objects']}
        self.assertEqual(
            objects['items']['list_fields'],
            ['sku', 'name', 'category', 'unit', 'price', 'safety_stock'],
        )
        self.assertEqual(
            objects['purchase_orders']['required_fields'],
            ['code', 'supplier_id', 'order_date', 'status'],
        )
        self.assertIn('supplier_id', objects['purchase_orders']['filterable_fields'])
        self.assertIn('grade', objects['suppliers']['filterable_fields'])

    def test_list_envelope_keys(self) -> None:
        payload = self.client.get('/api/v1/items', headers=self.headers).json()
        self.assertEqual(set(payload), {'data', 'next_cursor', 'total'})
        self.assertIsInstance(payload['data'], list)
        self.assertIsInstance(payload['total'], int)
        self.assertIsNone(payload['next_cursor'])

    def test_single_record_envelope(self) -> None:
        payload = self.client.get('/api/v1/items/item-0001', headers=self.headers).json()
        self.assertEqual(set(payload), {'data'})
        self.assertEqual(payload['data']['id'], 'item-0001')

    def test_created_records_expose_contract_fields(self) -> None:
        for object_type, body in SAMPLE_PAYLOADS.items():
            with self.subTest(object_type=object_type):
                created = self.client.post(
                    '/api/v1/' + object_type, json=body, headers=self.headers
                )
                self.assertEqual(created.status_code, 201, created.text)
                record = created.json()['data']
                for field in COMMON_FIELDS + OBJECT_FIELDS[object_type]:
                    self.assertIn(field, record, object_type + '.' + field)
                for field in INTERNAL_FIELDS:
                    self.assertNotIn(field, record, object_type + '.' + field)

    def test_get_returns_same_field_names_as_create(self) -> None:
        created = self.client.post(
            '/api/v1/warehouses', json={'code': 'WH-X', 'name': '字段集仓'}, headers=self.headers
        ).json()['data']
        fetched = self.client.get(
            '/api/v1/warehouses/' + created['id'], headers=self.headers
        ).json()['data']
        self.assertEqual(set(created), set(fetched))

    def test_unknown_object_type_is_404(self) -> None:
        response = self.client.get('/api/v1/leads', headers=self.headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_unknown_record_is_404(self) -> None:
        response = self.client.get('/api/v1/items/item-9999', headers=self.headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_enum_values_are_validated(self) -> None:
        response = self.client.post(
            '/api/v1/purchase_orders',
            json={
                'code': 'PO-BAD',
                'supplier_id': 'sup-0001',
                'order_date': '2026-09-20',
                'status': 'bogus',
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_every_enum_field_accepts_its_declared_values(self) -> None:
        for object_type, field, value in ENUM_FIELDS:
            with self.subTest(object_type=object_type, field=field):
                body = dict(SAMPLE_PAYLOADS[object_type])
                body[field] = value
                response = self.client.post(
                    '/api/v1/' + object_type, json=body, headers=self.headers
                )
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()['data'][field], value)

    def test_required_field_missing_is_400(self) -> None:
        response = self.client.post(
            '/api/v1/purchase_orders', json={'code': 'PO-NO-SUPPLIER'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_unknown_field_goes_to_extra_and_is_kept(self) -> None:
        created = self.client.post(
            '/api/v1/items',
            json={'sku': 'SKU-EXTRA', 'name': '扩展字段物料', 'unit': '件', 'batch_no': 'B-2026'},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        record = created.json()['data']
        self.assertEqual(record['batch_no'], 'B-2026')

    def test_filters_and_keyword_search(self) -> None:
        by_enum = self.client.get(
            '/api/v1/purchase_orders', params={'status': 'received'}, headers=self.headers
        ).json()
        self.assertEqual([row['id'] for row in by_enum['data']], ['po-0001'])
        by_ref = self.client.get(
            '/api/v1/purchase_order_lines', params={'order_id': 'po-0001'}, headers=self.headers
        ).json()
        self.assertEqual(sorted(row['id'] for row in by_ref['data']), ['pol-0001', 'pol-0002'])
        keyword = self.client.get(
            '/api/v1/customers', params={'q': '远山'}, headers=self.headers
        ).json()
        self.assertEqual([row['id'] for row in keyword['data']], ['cus-0001'])

    def test_sort_and_order(self) -> None:
        payload = self.client.get(
            '/api/v1/items', params={'sort': 'sku', 'order': 'asc'}, headers=self.headers
        ).json()
        self.assertEqual([row['sku'] for row in payload['data']], ['SKU-1001', 'SKU-1002'])
        payload = self.client.get(
            '/api/v1/items', params={'sort': 'sku', 'order': 'desc'}, headers=self.headers
        ).json()
        self.assertEqual([row['sku'] for row in payload['data']], ['SKU-1002', 'SKU-1001'])

    def test_unsupported_sort_is_400(self) -> None:
        # 只有带 order/page 的分页查询才会用到 sort 列，按键集游标走时排序固定为 updated_at
        response = self.client.get(
            '/api/v1/items',
            params={'sort': 'drop table', 'order': 'desc'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_user_record_exposes_team_ids_not_team_id(self) -> None:
        payload = self.client.get('/api/v1/users/ui-unused', headers=self.headers)
        self.assertEqual(payload.status_code, 404, payload.text)
        listed = self.client.get('/api/v1/users', headers=self.headers).json()
        row = next(item for item in listed['data'] if item['id'] == 'u-200')
        self.assertNotIn('team_id', row)
        self.assertEqual(row['team_ids'], ['t-sales'])
        self.assertEqual(row['role'], 'staff')

    def test_invoice_partner_and_order_are_free_refs(self) -> None:
        invoice = support.data_of(
            self.client.get('/api/v1/invoices/inv-0001', headers=self.headers)
        )
        self.assertEqual(invoice['partner_id'], 'cus-0001')
        self.assertEqual(invoice['order_id'], 'so-0001')


class PaginationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()
        for index in range(5):
            response = self.client.post(
                '/api/v1/items',
                json={'sku': 'SKU-P' + str(index), 'name': '分页物料 ' + str(index), 'unit': '件'},
                headers=self.headers,
            )
            self.assertEqual(response.status_code, 201, response.text)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_cursor_walk_covers_every_record_once(self) -> None:
        seen: list[str] = []
        cursor = None
        pages = 0
        while True:
            params = {'limit': 2}
            if cursor:
                params['cursor'] = cursor
            payload = self.client.get('/api/v1/items', params=params, headers=self.headers).json()
            pages += 1
            self.assertLessEqual(len(payload['data']), 2)
            seen.extend(row['id'] for row in payload['data'])
            cursor = payload['next_cursor']
            if not cursor:
                break
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), 7)
        self.assertGreater(pages, 1)

    def test_total_is_stable_across_pages(self) -> None:
        first = self.client.get('/api/v1/items', params={'limit': 1}, headers=self.headers).json()
        second = self.client.get(
            '/api/v1/items', params={'limit': 1, 'cursor': first['next_cursor']}, headers=self.headers
        ).json()
        self.assertEqual(first['total'], 7)
        self.assertEqual(second['total'], 7)

    def test_page_param_pages_backwards_compatible(self) -> None:
        first = self.client.get(
            '/api/v1/items', params={'limit': 3, 'page': 1}, headers=self.headers
        ).json()
        second = self.client.get(
            '/api/v1/items', params={'limit': 3, 'page': 2}, headers=self.headers
        ).json()
        self.assertEqual(len(first['data']), 3)
        self.assertEqual(len(second['data']), 3)
        self.assertFalse(set(row['id'] for row in first['data']) & set(row['id'] for row in second['data']))
        self.assertEqual(first['total'], 7)

    def test_updated_since_filters_out_older_records(self) -> None:
        payload = self.client.get(
            '/api/v1/items',
            params={'updated_since': '2999-01-01T00:00:00+00:00'},
            headers=self.headers,
        ).json()
        self.assertEqual(payload['total'], 0)
        self.assertEqual(payload['data'], [])

    def test_updated_since_epoch_returns_everything(self) -> None:
        payload = self.client.get(
            '/api/v1/items',
            params={'updated_since': '1970-01-01T00:00:00+00:00'},
            headers=self.headers,
        ).json()
        self.assertEqual(payload['total'], 7)

    def test_bad_updated_since_is_400(self) -> None:
        response = self.client.get(
            '/api/v1/items', params={'updated_since': 'yesterday'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_limit_above_max_is_clamped_to_max_page_size(self) -> None:
        response = self.client.get('/api/v1/items', params={'limit': 9999}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['data']), 7)

    def test_zero_limit_is_400(self) -> None:
        response = self.client.get('/api/v1/items', params={'limit': 0}, headers=self.headers)
        self.assertEqual(response.status_code, 400, response.text)


class OrderLifecycleWriteTest(unittest.TestCase):
    '''采购/销售状态推进与订单行写回必须可用，AI 侧的写回动作依赖它们。'''

    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.headers = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_purchase_order_can_move_to_received(self) -> None:
        response = self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'status': 'received'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['status'], 'received')

    def test_sales_order_can_move_to_closed(self) -> None:
        response = self.client.patch(
            '/api/v1/sales_orders/so-0002', json={'status': 'closed'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['status'], 'closed')

    def test_invoice_can_be_settled(self) -> None:
        response = self.client.patch(
            '/api/v1/invoices/inv-0002', json={'status': 'settled'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['status'], 'settled')

    def test_line_can_be_created_against_an_order(self) -> None:
        response = self.client.post(
            '/api/v1/purchase_order_lines',
            json={
                'order_id': 'po-0002',
                'item_id': 'item-0001',
                'quantity': 10,
                'unit_price': 860,
                'amount': 8600,
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        line = response.json()['data']
        self.assertEqual(line['order_id'], 'po-0002')
        listed = self.client.get(
            '/api/v1/purchase_order_lines', params={'order_id': 'po-0002'}, headers=self.headers
        ).json()
        self.assertIn(line['id'], [row['id'] for row in listed['data']])

    def test_stage_survives_a_reread(self) -> None:
        self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'status': 'received'}, headers=self.headers
        )
        payload = self.client.get('/api/v1/purchase_orders/po-0002', headers=self.headers).json()
        self.assertEqual(payload['data']['status'], 'received')


if __name__ == '__main__':
    unittest.main()