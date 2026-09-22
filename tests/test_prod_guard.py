'''生产保护：env 落在生产取值上时，出厂默认值一律拒绝启动。

保护生效的前提是 env 认得出来，所以顺手把 env 的取值白名单也测了：
写错成 prd 之类的值会静默关掉保护，那种情况必须直接报错。
'''

from __future__ import annotations

import unittest
from typing import Any

from pydantic import ValidationError

from app.core.config import PRODUCTION_ENVS, Settings

# 一台合规的生产配置；改这里之前先想清楚是不是把生产保护顺带关掉了
HARDENED: dict[str, Any] = {
    'secret_key': 's' * 40,
    'service_token': 'v' * 40,
    'bootstrap_admin_password': 'p' * 20,
    'seed_demo': False,
    'storage': 'postgres',
    'cors_origins': 'https://erp.example.com',
}


def settings(**overrides: Any) -> Settings:
    '''绕开本机 .env，只按显式参数构造。'''
    return Settings(_env_file=None, **overrides)


class ProductionGuardTest(unittest.TestCase):
    def rejected(self, **overrides: Any) -> str:
        '''只接受被拦下来的结果，返回错误正文，方便逐条断言。'''
        with self.assertRaises(ValidationError) as ctx:
            settings(**overrides)
        return str(ctx.exception)

    def test_dev_keeps_defaults_usable(self) -> None:
        built = settings()
        self.assertEqual(built.env, 'dev')
        self.assertEqual(built.storage, 'sqlite')
        self.assertTrue(built.seed_demo)

    def test_prod_rejects_every_default(self) -> None:
        message = self.rejected(env='prod')
        for expected in (
            'ERP_SECRET_KEY 还是出厂默认值',
            'ERP_SERVICE_TOKEN 还是出厂默认值',
            'ERP_BOOTSTRAP_ADMIN_PASSWORD 还是出厂默认值',
            'ERP_SEED_DEMO 仍为 true',
            'ERP_STORAGE=sqlite',
        ):
            self.assertIn(expected, message)

    def test_prod_accepts_hardened_config(self) -> None:
        self.assertEqual(settings(env='prod', **HARDENED).env, 'prod')

    def test_compose_placeholder_is_rejected(self) -> None:
        message = self.rejected(env='prod', **{**HARDENED, 'secret_key': 'change-me-in-production'})
        self.assertIn('ERP_SECRET_KEY', message)

    def test_short_secret_is_rejected(self) -> None:
        message = self.rejected(env='prod', **{**HARDENED, 'secret_key': 'short-key'})
        self.assertIn('ERP_SECRET_KEY 太短', message)

    def test_empty_service_token_is_rejected(self) -> None:
        message = self.rejected(env='prod', **{**HARDENED, 'service_token': ''})
        self.assertIn('ERP_SERVICE_TOKEN 不能为空', message)

    def test_sqlite_needs_explicit_flag(self) -> None:
        message = self.rejected(env='prod', **{**HARDENED, 'storage': 'sqlite'})
        self.assertIn('ERP_ALLOW_EPHEMERAL_STORAGE=true', message)
        relaxed = {**HARDENED, 'storage': 'sqlite', 'allow_ephemeral_storage': True}
        built = settings(env='prod', **relaxed)
        self.assertEqual(built.storage, 'sqlite')

    def test_prod_rejects_wildcard_cors(self) -> None:
        self.assertIn('不能出现 *', self.rejected(env='prod', **{**HARDENED, 'cors_origins': '*'}))

    def test_stage_counts_as_production(self) -> None:
        self.assertIn('staging', PRODUCTION_ENVS)
        self.assertIn('属于生产环境', self.rejected(env='staging'))

    def test_unknown_env_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            settings(env='prd')
        self.assertIn('env 必须是', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
