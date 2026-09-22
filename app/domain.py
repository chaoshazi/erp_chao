'''领域类型：与 HTTP 无关的纯数据结构。

时间统一按 naive UTC 存库、按带时区的 ISO 字符串出参，
这样 sqlite 与 postgres 行为一致，AI 侧也能直接解析。
'''

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    '''当前时间（naive UTC，用于入库）。'''
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    aware = as_aware(value)
    return aware.isoformat() if aware is not None else None


@dataclass(frozen=True)
class Actor:
    '''请求者身份：人工用户或 AI 服务账号。'''

    kind: str
    user_id: str
    role: str
    team_id: str | None = None
    tenant_id: str = 'default'
    display: str = ''
    # AI 侧通过 X-Actor-Id 传来的真实操作者（仅用于审计归因）
    on_behalf_of: str | None = None

    @property
    def is_service(self) -> bool:
        return self.kind == 'service'

    @property
    def sees_all(self) -> bool:
        '''管理员与服务账号不受行级限制。'''
        return self.role in ('admin', 'service')

    def to_public(self) -> dict[str, Any]:
        return {
            'id': self.user_id,
            'name': self.display or self.user_id,
            'role': self.role,
            'team_id': self.team_id,
            'kind': self.kind,
        }


@dataclass
class RecordPage:
    items: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: str | None = None
    total: int = 0