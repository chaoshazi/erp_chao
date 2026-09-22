'''记录服务：把存储层的 CRUD 包装成带幂等与审计的用例。

写接口的幂等语义（AI 侧会重试，所以必须可靠）：

- 带 Idempotency-Key 时，同一 (操作者, key) 的重复请求直接回放首次响应，不再写库；
- 同一 key 换了请求体视为误用，返回 409；
- 回放不重复写审计，避免审计里出现两条一样的记录。
'''

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.adapters.sql import SqlStore
from app.contract import get_object
from app.core.config import Settings
from app.domain import Actor, RecordPage, utcnow
from app.errors import Conflict, NotFound, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_LIST_LIMIT = 50


def payload_hash(payload: dict[str, Any] | None) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def parse_updated_since(value: str | None):
    '''updated_since 接受 ISO 8601（可带时区）。'''
    text = str(value or '').strip()
    if not text:
        return None
    candidate = text[:-1] + '+00:00' if text.endswith('Z') else text
    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValidationError('updated_since 必须是 ISO 8601 时间') from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


class RecordService:
    def __init__(self, store: SqlStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    # ---- 查询 ----
    def list_records(
        self,
        actor: Actor,
        object_type: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        updated_since: str | None = None,
        filters: dict[str, Any] | None = None,
        q: str | None = None,
        include_deleted: bool = False,
        sort: str | None = None,
        order: str | None = None,
        page: int | None = None,
    ) -> RecordPage:
        if include_deleted and not actor.sees_all:
            raise ValidationError('只有管理员可以查看已删除记录')
        return self.store.list_records(
            actor,
            object_type,
            cursor=cursor,
            limit=limit,
            updated_since=parse_updated_since(updated_since),
            filters=filters,
            q=q,
            include_deleted=include_deleted,
            sort=sort,
            order=order,
            page=page,
        )

    def get(self, actor: Actor, object_type: str, record_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        found = self.store.get_record(actor, object_type, record_id, include_deleted=include_deleted)
        if found is None:
            raise NotFound('记录不存在或无权访问')
        return found

    # ---- 写入 ----
    def create(
        self,
        actor: Actor,
        object_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        path: str = '',
    ) -> tuple[int, dict[str, Any]]:
        if get_object(object_type) is None:
            raise NotFound(f'未知对象类型：{object_type}')
        method = 'POST'
        replayed = self._replay(actor, idempotency_key, method, path, payload)
        if replayed is not None:
            return replayed
        record = self.store.create_record(actor, object_type, payload)
        self.store.add_audit(
            actor,
            source=self._source(actor),
            method=method,
            path=path,
            object_type=object_type,
            record_id=str(record.get('id') or ''),
            before=None,
            after=record,
            idempotency_key=idempotency_key,
        )
        return self._remember(actor, idempotency_key, method, path, payload, 201, record)

    def update(
        self,
        actor: Actor,
        object_type: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        path: str = '',
    ) -> tuple[int, dict[str, Any]]:
        method = 'PATCH'
        replayed = self._replay(actor, idempotency_key, method, path, payload)
        if replayed is not None:
            return replayed
        before = self.get(actor, object_type, record_id, include_deleted=True)
        record = self.store.update_record(actor, object_type, record_id, payload)
        self.store.add_audit(
            actor,
            source=self._source(actor),
            method=method,
            path=path,
            object_type=object_type,
            record_id=str(record_id),
            before=before,
            after=record,
            idempotency_key=idempotency_key,
        )
        return self._remember(actor, idempotency_key, method, path, payload, 200, record)

    def delete(
        self,
        actor: Actor,
        object_type: str,
        record_id: str,
        *,
        idempotency_key: str | None = None,
        path: str = '',
    ) -> tuple[int, dict[str, Any]]:
        method = 'DELETE'
        replayed = self._replay(actor, idempotency_key, method, path, {})
        if replayed is not None:
            return replayed
        before = self.get(actor, object_type, record_id, include_deleted=True)
        record = self.store.delete_record(actor, object_type, record_id)
        self.store.add_audit(
            actor,
            source=self._source(actor),
            method=method,
            path=path,
            object_type=object_type,
            record_id=str(record_id),
            before=before,
            after=record,
            idempotency_key=idempotency_key,
        )
        return self._remember(actor, idempotency_key, method, path, {}, 200, record)

    # ---- 幂等与审计 ----
    @staticmethod
    def _source(actor: Actor) -> str:
        return 'ai' if actor.is_service else 'human'

    def change_password(self, actor: Actor, password: str) -> None:
        '''改自己的密码；审计里只记「已变更」，不落任何明文或摘要。'''
        self.store.set_password(actor.user_id, password)
        self.store.add_audit(
            actor,
            source=self._source(actor),
            method='PATCH',
            path='/api/auth/password',
            object_type='users',
            record_id=actor.user_id,
            before=None,
            after={'password': 'changed'},
        )

    def _actor_key(self, actor: Actor) -> str:
        return f'{actor.kind}:{actor.user_id}'

    def _replay(
        self,
        actor: Actor,
        idempotency_key: str | None,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]] | None:
        key = str(idempotency_key or '').strip()
        if not key:
            return None
        existing = self.store.find_idempotent(self._actor_key(actor), key)
        if existing is None:
            return None
        if existing.get('request_hash') != payload_hash(payload):
            raise Conflict('幂等键已被不同的请求体使用')
        status_code = int(existing.get('status_code') or 200)
        response = existing.get('response')
        body = response if isinstance(response, dict) else {}
        logger.info('幂等回放 actor=%s key=%s', self._actor_key(actor), key)
        return status_code, body

    def _remember(
        self,
        actor: Actor,
        idempotency_key: str | None,
        method: str,
        path: str,
        payload: dict[str, Any],
        status_code: int,
        record: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        body = {'data': record}
        key = str(idempotency_key or '').strip()
        if key:
            self.store.save_idempotent(
                self._actor_key(actor),
                key,
                method=method,
                path=path,
                request_hash=payload_hash(payload),
                status_code=status_code,
                response=body,
            )
        return status_code, body
