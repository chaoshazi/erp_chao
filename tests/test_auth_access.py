'''鉴权与行级权限回归。

角色语义（与 AI 能力层的 ACL 假设一致）：

- 服务账号 / admin：全量可见可写；
- manager：只看本部门（team_id 相同），可写本部门记录；
- staff：可读本人 + 本部门（同团队），只能写自己的记录。
'''

from __future__ import annotations

import unittest

from tests import support

OHTER_TEAM_ITEM = 'item-0001'  # t-purchase
OWN_TEAM_CUSTOMER = 'cus-0001'  # t-sales，负责人 u-200
FINANCE_CUSTOMER = 'cus-0002'  # t-finance，负责人 u-300


class AuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_missing_token_is_401(self) -> None:
        response = self.client.get('/api/v1/items')
        self.assertEqual(response.status_code, 401, response.text)

    def test_invalid_token_is_401(self) -> None:
        response = self.client.get('/api/v1/items', headers=support.bearer('nope'))
        self.assertEqual(response.status_code, 401, response.text)

    def test_wrong_password_is_401(self) -> None:
        response = self.client.post(
            '/api/auth/login', json={'email': support.MANAGER_EMAIL, 'password': 'wrong-password'}
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_login_returns_token_and_actor(self) -> None:
        payload = support.login(self.client, support.MANAGER_EMAIL, support.DEMO_PASSWORD)
        self.assertTrue(payload['token'])
        self.assertEqual(payload['user']['id'], 'u-100')
        self.assertEqual(payload['user']['role'], 'manager')
        self.assertEqual(payload['user']['team_id'], 't-purchase')

    def test_me_reports_effective_actor(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        payload = self.client.get('/api/auth/me', headers=headers).json()
        self.assertEqual(payload['id'], 'u-200')
        self.assertEqual(payload['role'], 'staff')
        self.assertEqual(payload['kind'], 'user')

    def test_service_token_can_claim_an_actor_for_attribution(self) -> None:
        headers = support.service_headers(**{'X-Actor-Id': 'u-100', 'X-Actor-Team-Ids': 't-purchase'})
        payload = self.client.get('/api/v1/meta', headers=headers).json()
        self.assertEqual(payload['actor']['kind'], 'service')
        self.assertEqual(payload['actor']['id'], 'ai-agent')

    def test_password_change_takes_effect(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        response = self.client.post(
            '/api/auth/password', json={'password': 'newpassword123'}, headers=headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        support.login(self.client, support.STAFF_EMAIL, 'newpassword123')
        stale = self.client.post(
            '/api/auth/login',
            json={'email': support.STAFF_EMAIL, 'password': support.DEMO_PASSWORD},
        )
        self.assertEqual(stale.status_code, 401, stale.text)

    def test_inactive_user_cannot_login(self) -> None:
        service = support.service_headers()
        created = support.data_of(
            self.client.post(
                '/api/v1/users',
                json={
                    'name': '停用员工',
                    'email': 'inactive@example.com',
                    'team_id': 't-sales',
                    'role': 'staff',
                    'password': 'inactive12345',
                    'is_active': False,
                },
                headers=service,
            )
        )
        response = self.client.post(
            '/api/auth/login',
            json={'email': 'inactive@example.com', 'password': 'inactive12345'},
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(created['is_active'], False)


class RowLevelAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = support.erp()
        self.client, self.settings = self._ctx.__enter__()
        self.service = support.service_headers()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def _ids(self, headers: dict[str, str], object_type: str) -> list[str]:
        payload = self.client.get('/api/v1/' + object_type, headers=headers).json()
        return sorted(row['id'] for row in payload['data'])

    def test_service_account_sees_everything(self) -> None:
        self.assertEqual(self._ids(self.service, 'items'), ['item-0001', 'item-0002'])
        self.assertEqual(
            self._ids(self.service, 'customers'), ['cus-0001', 'cus-0002']
        )

    def test_manager_sees_only_own_department(self) -> None:
        headers = support.login_headers(self.client, support.MANAGER_EMAIL)
        self.assertEqual(self._ids(headers, 'items'), ['item-0001', 'item-0002'])
        self.assertEqual(self._ids(headers, 'customers'), [])
        self.assertEqual(self._ids(headers, 'purchase_orders'), ['po-0001', 'po-0002'])

    def test_staff_sees_own_and_team_records(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        self.assertEqual(self._ids(headers, 'customers'), ['cus-0001'])
        self.assertEqual(self._ids(headers, 'sales_orders'), ['so-0001'])
        self.assertEqual(self._ids(headers, 'items'), [])

    def test_finance_manager_sees_finance_records(self) -> None:
        headers = support.login_headers(self.client, support.FINANCE_EMAIL)
        self.assertEqual(self._ids(headers, 'invoices'), ['inv-0001', 'inv-0002'])
        self.assertEqual(self._ids(headers, 'customers'), ['cus-0002'])
        self.assertEqual(self._ids(headers, 'stock_moves'), [])

    def test_invisible_record_is_404_not_403(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        response = self.client.get('/api/v1/items/' + OHTER_TEAM_ITEM, headers=headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_other_team_write_is_404(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        response = self.client.patch(
            '/api/v1/items/' + OHTER_TEAM_ITEM, json={'name': '越权改名'}, headers=headers
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_visible_but_not_writable_is_403(self) -> None:
        '''同部门同事的记录：staff 能读，不能写。'''
        support.data_of(
            self.client.post(
                '/api/v1/users',
                json={
                    'name': '同事甲',
                    'email': 'colleague@example.com',
                    'team_id': 't-sales',
                    'role': 'staff',
                    'password': 'colleague12345',
                },
                headers=self.service,
            )
        )
        created = support.data_of(
            self.client.post(
                '/api/v1/customers',
                json={
                    'name': '同事负责的客户',
                    'owner_id': 'u-201',
                    'team_ids': ['t-sales'],
                },
                headers=self.service,
            )
        )
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        visible = self.client.get('/api/v1/customers/' + created['id'], headers=headers)
        self.assertEqual(visible.status_code, 200, visible.text)
        blocked = self.client.patch(
            '/api/v1/customers/' + created['id'], json={'contact': '越权联系人'}, headers=headers
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)

    def test_manager_can_write_department_record(self) -> None:
        headers = support.login_headers(self.client, support.MANAGER_EMAIL)
        response = self.client.patch(
            '/api/v1/purchase_orders/po-0002', json={'note': '主管备注'}, headers=headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data']['note'], '主管备注')

    def test_staff_can_write_own_record(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        response = self.client.patch(
            '/api/v1/customers/' + OWN_TEAM_CUSTOMER, json={'contact': '新联系人'}, headers=headers
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_staff_cannot_list_deleted_records(self) -> None:
        headers = support.login_headers(self.client, support.STAFF_EMAIL)
        response = self.client.get(
            '/api/v1/customers', params={'include_deleted': 'true'}, headers=headers
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_users_object_is_admin_only_for_writes(self) -> None:
        manager = support.login_headers(self.client, support.MANAGER_EMAIL)
        created = self.client.post(
            '/api/v1/users',
            json={'name': '主管建号', 'email': 'manager-made@example.com', 'password': 'manager12345'},
            headers=manager,
        )
        self.assertEqual(created.status_code, 403, created.text)
        listed = self.client.get('/api/v1/users', headers=manager).json()
        self.assertEqual([row['id'] for row in listed['data']], ['u-100'])

    def test_admin_can_manage_users(self) -> None:
        headers = support.service_headers()
        created = support.data_of(
            self.client.post(
                '/api/v1/users',
                json={
                    'name': '新员工',
                    'email': 'newhire@example.com',
                    'team_id': 't-sales',
                    'role': 'staff',
                    'password': 'newhire12345',
                },
                headers=headers,
            )
        )
        self.assertEqual(created['email'], 'newhire@example.com')
        self.assertEqual(created['team_ids'], ['t-sales'])
        listed = self.client.get('/api/v1/users', headers=headers).json()
        self.assertIn(created['id'], [row['id'] for row in listed['data']])

    def test_teams_visibility(self) -> None:
        admin = self.client.get('/api/v1/teams', headers=self.service).json()
        self.assertEqual(
            sorted(team['id'] for team in admin['data']), ['t-finance', 't-purchase', 't-sales']
        )
        staff = support.login_headers(self.client, support.STAFF_EMAIL)
        own = self.client.get('/api/v1/teams', headers=staff).json()
        self.assertEqual([team['id'] for team in own['data']], ['t-sales'])
        self.assertEqual(own['data'][0]['member_count'], 1)

    def test_team_management_requires_admin(self) -> None:
        staff = support.login_headers(self.client, support.STAFF_EMAIL)
        response = self.client.post('/api/v1/teams', json={'name': '私建部门'}, headers=staff)
        self.assertEqual(response.status_code, 403, response.text)
        created = self.client.post(
            '/api/v1/teams', json={'id': 't-ops', 'name': '运维部'}, headers=self.service
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()['member_count'], 0)

    def test_audit_endpoint_requires_admin(self) -> None:
        staff = support.login_headers(self.client, support.STAFF_EMAIL)
        self.assertEqual(self.client.get('/api/v1/audit', headers=staff).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/audit', headers=self.service).status_code, 200)

    def test_service_actor_headers_do_not_widen_user_permissions(self) -> None:
        '''服务账号自身是全量的，但声明成真实操作者只用于审计归因，不改行级可见性。'''
        headers = support.service_headers(**{'X-Actor-Id': 'u-203', 'X-Actor-Team-Ids': 't-unknown'})
        payload = self.client.get('/api/v1/items', headers=headers).json()
        self.assertEqual(payload['total'], 2)


if __name__ == '__main__':
    unittest.main()