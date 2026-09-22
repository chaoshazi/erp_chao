'''依赖装配：配置、存储、服务与初始化数据。'''

from __future__ import annotations

import logging

from app.adapters.sql import SqlStore, build_store
from app.core.config import Settings
from app.seed import DEMO_RECORDS, DEMO_TEAMS, DEMO_USERS
from app.services.records import RecordService

logger = logging.getLogger(__name__)


class Container:
    def __init__(self, settings: Settings, store: SqlStore) -> None:
        self.settings = settings
        self.store = store
        self.records = RecordService(store, settings)

    @classmethod
    async def build(cls, settings: Settings) -> Container:
        store = build_store(settings)
        container = cls(settings, store)
        container.bootstrap_admin()
        container.seed_demo()
        logger.info(
            'ERP 已就绪 storage=%s tenant=%s',
            settings.storage,
            settings.tenant_id,
        )
        return container

    def bootstrap_admin(self) -> None:
        '''users 表为空时创建一个管理员，保证第一次能登录。'''
        if self.store.count_users():
            return
        email = str(self.settings.bootstrap_admin_email or '').strip().lower()
        password = str(self.settings.bootstrap_admin_password or '')
        if not email or not password:
            logger.warning('未配置管理员账号，跳过初始化')
            return
        self.store.seed_rows(
            'users',
            [
                {
                    'id': 'u-admin',
                    'name': self.settings.bootstrap_admin_name or '系统管理员',
                    'email': email,
                    'role': 'admin',
                    'password': password,
                }
            ],
        )
        logger.info('已创建初始管理员 account=%s', email)

    def seed_demo(self) -> None:
        if not self.settings.seed_demo:
            return
        teams = self.store.seed_teams(list(DEMO_TEAMS))
        users = self.store.seed_rows('users', list(DEMO_USERS))
        records = sum(
            self.store.seed_rows(object_type, list(rows))
            for object_type, rows in DEMO_RECORDS.items()
        )
        if teams or users or records:
            logger.info(
                '已写入演示数据 teams=%d users=%d records=%d', teams, users, records
            )

    def close(self) -> None:
        self.store.close()
