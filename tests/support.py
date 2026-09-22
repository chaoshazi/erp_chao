'''测试夹具：独立的临时 sqlite 库 + TestClient。

本套件只验证 sqlite 形态，不依赖 Postgres、docker 或任何外部服务。
Postgres 适配器与本机未安装的 psycopg 都不在验证范围内。
'''

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

SERVICE_TOKEN = 'dev-service-token'
ADMIN_EMAIL = 'admin@example.com'
ADMIN_PASSWORD = 'admin12345'
MANAGER_EMAIL = 'chenxiao@example.com'
STAFF_EMAIL = 'zhoumin@example.com'
FINANCE_EMAIL = 'lina@example.com'
DEMO_PASSWORD = 'sales12345'

# 与演示数据一致的固定 ID，测试直接按 ID 断言
SEED_IDS = {
    'items': ['item-0001', 'item-0002'],
    'suppliers': ['sup-0001', 'sup-0002'],
    'customers': ['cus-0001', 'cus-0002'],
    'warehouses': ['wh-0001', 'wh-0002'],
    'purchase_orders': ['po-0001', 'po-0002'],
    'purchase_order_lines': ['pol-0001', 'pol-0002', 'pol-0003'],
    'sales_orders': ['so-0001', 'so-0002'],
    'sales_order_lines': ['sol-0001', 'sol-0002'],
    'stock_moves': ['mv-0001', 'mv-0002', 'mv-0003', 'mv-0004', 'mv-0005'],
    'invoices': ['inv-0001', 'inv-0002'],
}


def make_settings(tmpdir: str, **overrides: Any) -> Settings:
    '''构造隔离配置：独立 sqlite 文件、关闭前端托管。'''
    values: dict[str, Any] = {
        'storage': 'sqlite',
        'sqlite_path': str(Path(tmpdir) / 'erp-test.sqlite3'),
        'serve_web': False,
        'seed_demo': True,
        'secret_key': 'test-secret-key',
        'service_token': SERVICE_TOKEN,
        'service_actor_id': 'ai-agent',
        'tenant_id': 'default',
        'bootstrap_admin_email': ADMIN_EMAIL,
        'bootstrap_admin_password': ADMIN_PASSWORD,
        'bootstrap_admin_name': '测试管理员',
        'default_page_size': 50,
        'max_page_size': 200,
    }
    values.update(overrides)
    return Settings(**values)


@contextmanager
def erp(**overrides: Any) -> Iterator[tuple[TestClient, Settings]]:
    '''每个用例一个全新的库，用完即删，用例之间互不影响。'''
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = make_settings(tmpdir, **overrides)
        with TestClient(create_app(settings)) as client:
            yield client, settings


def service_headers(**extra: str) -> dict[str, str]:
    '''AI 能力层实际使用的请求头：bearer 服务令牌。'''
    headers = {'Authorization': 'Bearer ' + SERVICE_TOKEN}
    headers.update(extra)
    return headers


def bearer(token: str) -> dict[str, str]:
    return {'Authorization': 'Bearer ' + token}


def login(client: TestClient, email: str, password: str) -> dict[str, Any]:
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return response.json()


def login_headers(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    return bearer(str(login(client, email, password)['token']))


def data_of(response: Any) -> dict[str, Any]:
    assert response.status_code < 300, response.text
    return response.json()['data']