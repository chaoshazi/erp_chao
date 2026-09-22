'''依赖注入：容器、身份解析与权限门槛。

身份有两类：

- 服务账号：Authorization 里的令牌等于 ERP_SERVICE_TOKEN，代表 AI 能力层，
  权限等同管理员，并可用 X-Actor-Id / X-Actor-Team-Ids 声明真实操作者（仅用于归因与归属）；
- 人工用户：令牌是 /api/auth/login 签发的自签 HMAC 令牌，权限按角色与行级范围。
'''

from __future__ import annotations

import hmac
from typing import Any

from fastapi import Depends, Header, Request

from app.adapters.sql import SqlStore
from app.contract import DEFAULT_ROLE
from app.core.config import Settings
from app.core.security import read_token
from app.domain import Actor
from app.errors import AuthError, Forbidden
from app.services.records import RecordService


def get_container(request: Request) -> Any:
    container = getattr(request.app.state, 'container', None)
    if container is None:
        raise RuntimeError('容器尚未初始化')
    return container


def get_settings_dep(request: Request) -> Settings:
    return get_container(request).settings


def get_store(request: Request) -> SqlStore:
    return get_container(request).store


def get_service(request: Request) -> RecordService:
    return get_container(request).records


def _extract_token(authorization: str | None, api_token: str | None) -> str:
    if authorization:
        scheme, _, value = str(authorization).partition(' ')
        if scheme.lower() == 'bearer' and value.strip():
            return value.strip()
    return str(api_token or '').strip()


def _is_active(row: dict[str, Any]) -> bool:
    value = row.get('is_active')
    return True if value is None else bool(value)


def current_actor(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_token: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    x_actor_team_ids: str | None = Header(default=None),
) -> Actor:
    settings = get_settings_dep(request)
    store = get_store(request)
    token = _extract_token(authorization, x_api_token)
    if not token:
        raise AuthError('缺少访问凭证')
    if settings.service_token and hmac.compare_digest(token, settings.service_token):
        teams = [part.strip() for part in str(x_actor_team_ids or '').split(',') if part.strip()]
        return Actor(
            kind='service',
            user_id=settings.service_actor_id,
            role='service',
            team_id=teams[0] if teams else None,
            tenant_id=settings.tenant_id,
            display='AI 服务账号',
            on_behalf_of=str(x_actor_id or '').strip() or None,
        )
    payload = read_token(token, settings.secret_key)
    if payload is None:
        raise AuthError('凭证无效或已过期')
    row = store.get_user_row(str(payload.get('sub') or ''))
    if row is None:
        raise AuthError('用户不存在')
    if not _is_active(row):
        raise AuthError('用户已停用')
    return Actor(
        kind='user',
        user_id=str(row.get('id')),
        role=str(row.get('role') or DEFAULT_ROLE),
        team_id=row.get('team_id'),
        tenant_id=settings.tenant_id,
        display=str(row.get('name') or row.get('id') or ''),
    )


def require_admin(actor: Actor = Depends(current_actor)) -> Actor:
    if not actor.sees_all:
        raise Forbidden('需要管理员权限')
    return actor