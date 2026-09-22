'''HTTP 路由。

路由顺序很关键：/meta、/stats/overview、/audit、/teams 必须声明在 /{object_type} 之前，
否则这些路径会先被对象类型路由匹配掉。

对象记录接口同时服务两类调用方：
- AI 能力层：只读同步（cursor/limit/updated_since）与受控写回（POST/PATCH/DELETE + Idempotency-Key）；
- ERP 前端：额外的 q/status/grade/owner_id/team_id/order/page 等筛选与排序参数。
'''

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api import schemas
from app.api.deps import (
    current_actor,
    get_service,
    get_settings_dep,
    get_store,
    require_admin,
)
from app.contract import DEFAULT_ROLE, OBJECT_NAMES, get_object, meta_payload
from app.core.security import issue_token, verify_password
from app.domain import Actor
from app.errors import AuthError, NotFound
from app.services.records import RecordService

health_router = APIRouter(tags=['health'])
auth_router = APIRouter(prefix='/api/auth', tags=['auth'])
api_router = APIRouter(prefix='/api/v1', tags=['erp'])

OWNERSHIP_FILTER_KEYS = ('owner_id', 'team_id')


def _spec_or_404(object_type: str):
    spec = get_object(object_type)
    if spec is None:
        raise NotFound('未知对象类型：' + str(object_type))
    return spec


def _active(row: dict[str, Any]) -> bool:
    value = row.get('is_active')
    return True if value is None else bool(value)


# ---- 健康检查 ----
@health_router.get('/health', response_model=schemas.HealthResponse)
def health(request: Request) -> schemas.HealthResponse:
    settings = get_settings_dep(request)
    return schemas.HealthResponse(
        version=__version__,
        env=settings.env,
        tenant_id=settings.tenant_id,
        storage=settings.storage,
        serve_web=settings.serve_web,
        object_types=list(OBJECT_NAMES),
    )


# ---- 认证 ----
@auth_router.post('/login', response_model=schemas.LoginResponse)
def login(
    payload: schemas.LoginRequest,
    store=Depends(get_store),
    settings=Depends(get_settings_dep),
) -> schemas.LoginResponse:
    row = store.find_user_by_email(payload.email)
    if row is None or not verify_password(payload.password, str(row.get('password_hash') or '')):
        raise AuthError('邮箱或密码不正确')
    if not _active(row):
        raise AuthError('用户已停用')
    token, expires_at = issue_token(
        subject=str(row.get('id')),
        secret=settings.secret_key,
        ttl_seconds=int(settings.token_ttl_hours) * 3600,
    )
    actor = Actor(
        kind='user',
        user_id=str(row.get('id')),
        role=str(row.get('role') or DEFAULT_ROLE),
        team_id=row.get('team_id'),
        tenant_id=settings.tenant_id,
        display=str(row.get('name') or ''),
    )
    user = {**actor.to_public(), 'email': str(row.get('email') or '')}
    return schemas.LoginResponse(token=token, expires_at=expires_at, user=user)


@auth_router.get('/me')
def me(actor: Actor = Depends(current_actor)) -> dict[str, Any]:
    return actor.to_public()


@auth_router.post('/password')
def change_password(
    payload: schemas.PasswordChangeRequest,
    actor: Actor = Depends(current_actor),
    service: RecordService = Depends(get_service),
) -> dict[str, Any]:
    service.change_password(actor, payload.password)
    return {'detail': '密码已更新'}


# ---- 元数据、统计、审计 ----
@api_router.get('/meta')
def meta(actor: Actor = Depends(current_actor)) -> dict[str, Any]:
    payload = meta_payload()
    payload['actor'] = actor.to_public()
    return payload


@api_router.get('/stats/overview')
def stats_overview(
    actor: Actor = Depends(current_actor), service: RecordService = Depends(get_service)
) -> dict[str, Any]:
    return service.store.stats(actor)


@api_router.get('/audit')
def list_audit(
    object_type: str | None = Query(default=None),
    record_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    actor: Actor = Depends(require_admin),
    service: RecordService = Depends(get_service),
) -> dict[str, Any]:
    return {
        'data': service.store.list_audit(
            actor, limit=limit, object_type=object_type, record_id=record_id
        )
    }


# ---- 团队 ----
@api_router.get('/teams')
def list_teams(
    actor: Actor = Depends(current_actor), service: RecordService = Depends(get_service)
) -> dict[str, Any]:
    return {'data': service.store.list_teams(actor)}


@api_router.post('/teams', status_code=201, response_model=schemas.TeamOut)
def create_team(
    payload: schemas.TeamRequest,
    actor: Actor = Depends(require_admin),
    service: RecordService = Depends(get_service),
) -> schemas.TeamOut:
    return schemas.TeamOut(**service.store.create_team(actor, payload.model_dump()))


@api_router.patch('/teams/{team_id}', response_model=schemas.TeamOut)
def update_team(
    team_id: str,
    payload: schemas.TeamRequest,
    actor: Actor = Depends(require_admin),
    service: RecordService = Depends(get_service),
) -> schemas.TeamOut:
    return schemas.TeamOut(**service.store.update_team(actor, team_id, payload.model_dump()))


@api_router.delete('/teams/{team_id}', response_model=schemas.TeamOut)
def delete_team(
    team_id: str,
    actor: Actor = Depends(require_admin),
    service: RecordService = Depends(get_service),
) -> schemas.TeamOut:
    return schemas.TeamOut(**service.store.delete_team(actor, team_id))


# ---- 对象记录：AI 契约与前端共用 ----
@api_router.get('/{object_type}')
def list_objects(
    object_type: str,
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    updated_since: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    actor: Actor = Depends(current_actor),
    service: RecordService = Depends(get_service),
) -> dict[str, Any]:
    spec = _spec_or_404(object_type)
    filters: dict[str, Any] = {}
    for key in (*spec.filterable_fields, *OWNERSHIP_FILTER_KEYS):
        value = request.query_params.get(key)
        if value not in (None, ''):
            filters[key] = value
    result = service.list_records(
        actor,
        object_type,
        cursor=cursor,
        limit=limit,
        updated_since=updated_since,
        filters=filters,
        q=q,
        include_deleted=bool(include_deleted),
        sort=sort,
        order=order,
        page=page,
    )
    return {'data': result.items, 'next_cursor': result.next_cursor, 'total': result.total}


@api_router.post('/{object_type}')
def create_object(
    object_type: str,
    request: Request,
    payload: dict[str, Any] | None = Body(default=None),
    actor: Actor = Depends(current_actor),
    service: RecordService = Depends(get_service),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
) -> JSONResponse:
    _spec_or_404(object_type)
    code, body = service.create(
        actor,
        object_type,
        payload or {},
        idempotency_key=idempotency_key,
        path=str(request.url.path),
    )
    return JSONResponse(content=body, status_code=code)


@api_router.get('/{object_type}/{record_id}')
def get_object_record(
    object_type: str,
    record_id: str,
    include_deleted: bool = Query(default=False),
    actor: Actor = Depends(current_actor),
    service: RecordService = Depends(get_service),
) -> dict[str, Any]:
    _spec_or_404(object_type)
    return {
        'data': service.get(
            actor, object_type, record_id, include_deleted=bool(include_deleted)
        )
    }


@api_router.patch('/{object_type}/{record_id}')
def update_object_record(
    object_type: str,
    record_id: str,
    request: Request,
    payload: dict[str, Any] | None = Body(default=None),
    actor: Actor = Depends(current_actor),
    service: RecordService = Depends(get_service),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
) -> JSONResponse:
    _spec_or_404(object_type)
    code, body = service.update(
        actor,
        object_type,
        record_id,
        payload or {},
        idempotency_key=idempotency_key,
        path=str(request.url.path),
    )
    return JSONResponse(content=body, status_code=code)


@api_router.delete('/{object_type}/{record_id}')
def delete_object_record(
    object_type: str,
    record_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    service: RecordService = Depends(get_service),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
) -> JSONResponse:
    _spec_or_404(object_type)
    code, body = service.delete(
        actor,
        object_type,
        record_id,
        idempotency_key=idempotency_key,
        path=str(request.url.path),
    )
    return JSONResponse(content=body, status_code=code)