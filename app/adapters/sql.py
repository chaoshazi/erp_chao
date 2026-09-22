'''SQLAlchemy Core 存储层：一套实现同时支持 sqlite（默认）与 postgres。

- 每个对象类型一张表，公共列由 _common_columns() 生成，类型列来自 app/contract.py；
- 未知字段一律进 extra(JSON)，避免模型生成的键导致写回失败；
- 另有 record_audit（写审计）与 idempotency_keys（写幂等）两张辅助表。

出参只暴露契约字段：tenant_id / team_id / created_by / deleted_at 属内部列，
记录归属通过 team_ids 数组暴露，避免污染 AI 侧的字段映射。
'''

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    and_,
    case,
    create_engine,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Engine

from app.contract import OBJECTS, Field, ObjectSpec, get_object
from app.core.config import Settings
from app.core.security import hash_password
from app.domain import Actor, RecordPage, to_iso, utcnow
from app.errors import Conflict, Forbidden, NotFound, ValidationError

logger = logging.getLogger(__name__)

TEAMS_TABLE = 'teams'
AUDIT_TABLE = 'record_audit'
IDEMPOTENCY_TABLE = 'idempotency_keys'

# email 类型的最小校验：一个 @ 加带点的域名，挡住明显脏数据又不至于误杀正常地址
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# 内部列：不进入对外 payload
INTERNAL_COLUMNS = ('tenant_id', 'team_id', 'created_by', 'deleted_at')
# 客户端不允许直接设置的公共列（归属列单独处理）
IGNORED_INPUT_KEYS = frozenset(
    {'id', 'version', 'created_at', 'updated_at', 'created_by', 'deleted_at', 'tenant_id', 'team_ids'}
)
OWNERSHIP_KEYS = ('owner_id', 'team_id')
SORTABLE_COMMON = ('updated_at', 'created_at', 'id', 'owner_id', 'team_id', 'version')
COMMON_COLUMN_NAMES = (
    'tenant_id',
    'version',
    'created_at',
    'updated_at',
    'created_by',
    'owner_id',
    'team_id',
    'deleted_at',
)
MAX_ID_ATTEMPTS = 5
# 库存流水方向：这两类使出库，其余（采购入库、调拨入）按正数累加
OUTBOUND_MOVE_KINDS = ('issue', 'transfer_out')
# 未完结状态：仪表盘据此统计在途单据
OPEN_PO_STATUSES = ('draft', 'submitted', 'approved', 'partial')
OPEN_SO_STATUSES = ('draft', 'confirmed', 'partial')
OPEN_INVOICE_STATUSES = ('draft', 'issued', 'partial', 'overdue')
MAX_LOW_STOCK_ROWS = 10


def _common_columns(skip: tuple[str, ...] = ()) -> list[Column]:
    '''每个业务表都有的公共列；Column 不能跨表复用，所以每次新建实例。

    skip 用于对象自己定义了同名字段的情况：users 的 team_id 来自契约字段，
    不能再由公共列提供，否则建表时列名冲突。
    '''
    columns = [
        Column('tenant_id', String(64), nullable=False, default='default'),
        Column('version', String(32), nullable=False, default='1'),
        Column('created_at', DateTime, nullable=False),
        Column('updated_at', DateTime, nullable=False, index=True),
        Column('created_by', String(64), nullable=False, default=''),
        Column('owner_id', String(64), nullable=True, index=True),
        Column('team_id', String(64), nullable=True, index=True),
        Column('deleted_at', DateTime, nullable=True),
    ]
    return [column for column in columns if column.name not in skip]


def _column_for(field: Field) -> Column:
    if field.kind == 'decimal':
        return Column(field.name, Numeric(18, 2), nullable=True)
    if field.kind == 'date':
        return Column(field.name, Date, nullable=True)
    if field.kind == 'datetime':
        return Column(field.name, DateTime, nullable=True)
    if field.kind == 'bool':
        return Column(field.name, Boolean, nullable=True)
    if field.kind == 'text':
        return Column(field.name, Text, nullable=True)
    return Column(field.name, String(512), nullable=True)


def build_metadata() -> MetaData:
    '''按契约元数据建表：对象表 + 团队表 + 审计表 + 幂等表。'''
    metadata = MetaData()
    Table(
        TEAMS_TABLE,
        metadata,
        Column('id', String(64), primary_key=True),
        *_common_columns(),
        Column('name', String(200), nullable=False),
    )
    for spec in OBJECTS.values():
        skip = tuple(item.name for item in spec.fields if item.name in COMMON_COLUMN_NAMES)
        columns: list[Column] = [
            Column('id', String(64), primary_key=True),
            *_common_columns(skip),
        ]
        columns.extend(_column_for(item) for item in spec.fields if item.kind != 'password')
        columns.append(Column('extra', JSON, nullable=True))
        if spec.name == 'users':
            columns.append(Column('password_hash', String(256), nullable=False, default=''))
        Table(spec.name, metadata, *columns)
    Table(
        AUDIT_TABLE,
        metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('at', DateTime, nullable=False, index=True),
        Column('tenant_id', String(64), nullable=False, default='default'),
        Column('actor_id', String(64), nullable=False),
        Column('actor_kind', String(32), nullable=False),
        Column('on_behalf_of', String(64), nullable=True),
        Column('source', String(32), nullable=False),
        Column('method', String(16), nullable=False),
        Column('path', String(256), nullable=False),
        Column('object_type', String(32), nullable=False),
        Column('record_id', String(64), nullable=True), 
        Column('before', JSON, nullable=True),
        Column('after', JSON, nullable=True),
        Column('idempotency_key', String(200), nullable=True),
    )
    Table(
        IDEMPOTENCY_TABLE,
        metadata,
        Column('actor', String(64), primary_key=True),
        Column('key', String(200), primary_key=True),
        Column('method', String(16), nullable=False),
        Column('path', String(256), nullable=False),
        Column('request_hash', String(64), nullable=False),
        Column('status_code', Integer, nullable=False),
        Column('response', JSON, nullable=True),
        Column('created_at', DateTime, nullable=False),
    )
    return metadata


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _bump_version(raw: Any) -> str:
    try:
        return str(int(str(raw)) + 1)
    except (TypeError, ValueError):
        return '2'


class SqlStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.metadata = build_metadata()
        self.engine: Engine = self._create_engine(settings)
        if settings.auto_migrate:
            self.ensure_schema()

    # ---- 基础设施 ----
    def _create_engine(self, settings: Settings) -> Engine:
        uri = settings.database_uri
        connect_args: dict[str, Any] = {}
        if uri.startswith('sqlite'):
            connect_args = {'check_same_thread': False}
            target = settings.sqlite_file
            if target and not target.startswith(':'):
                Path(target).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(uri, future=True, pool_pre_ping=True, connect_args=connect_args)

    def ensure_schema(self) -> None:
        self.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def table(self, name: str) -> Table:
        return self.metadata.tables[name]

    def _spec(self, object_type: str) -> ObjectSpec:
        spec = get_object(object_type)
        if spec is None:
            raise NotFound(f'未知对象类型：{object_type}')
        return spec

    def _page_size(self, limit: int | None) -> int:
        if limit is None:
            return self._settings.default_page_size
        try:
            value = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValidationError('limit 必须是整数') from exc
        if value <= 0:
            raise ValidationError('limit 必须大于 0')
        return min(value, self._settings.max_page_size)

    # ---- 权限 ----
    def _visibility_conditions(self, actor: Actor, spec: ObjectSpec, table: Table) -> list[Any]:
        '''行级可见性：管理员与服务账号全量，其余按 owner + team 过滤。'''
        if actor.sees_all:
            return []
        if spec.name == 'users':
            options = [table.c.id == actor.user_id]
            if actor.team_id:
                options.append(table.c.team_id == actor.team_id)
            return [or_(*options)]
        own = table.c.owner_id == actor.user_id
        if not actor.team_id:
            return [own]
        if actor.role == 'manager':
            return [table.c.team_id == actor.team_id]
        return [or_(own, table.c.team_id == actor.team_id)]

    def can_write(self, actor: Actor, spec: ObjectSpec, row: dict[str, Any]) -> bool:
        if actor.sees_all:
            return True
        if spec.name == 'users':
            return False
        if actor.role == 'manager':
            return bool(actor.team_id) and row.get('team_id') == actor.team_id
        return row.get('owner_id') == actor.user_id

    def _assert_can_manage_users(self, actor: Actor) -> None:
        if not actor.sees_all:
            raise Forbidden('只有管理员可以维护用户')

    # ---- 序列化 ----
    def serialize(self, spec: ObjectSpec, source: Any) -> dict[str, Any]:
        raw = dict(source)
        data: dict[str, Any] = {}
        write_only = {field.name for field in spec.fields if field.write_only}
        for key, value in raw.items():
            if key in INTERNAL_COLUMNS or key in ('extra', 'password_hash'):
                continue
            if key in write_only:
                continue
            data[key] = _jsonable(value)
        extra = raw.get('extra')
        if isinstance(extra, dict):
            for key, value in extra.items():
                data.setdefault(str(key), _jsonable(value))
        team_id = raw.get('team_id')
        data['team_ids'] = [team_id] if team_id else []
        return data

    # ---- 查询 ----
    def list_records(
        self,
        actor: Actor,
        object_type: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        updated_since: datetime | None = None,
        filters: dict[str, Any] | None = None,
        q: str | None = None,
        include_deleted: bool = False,
        sort: str | None = None,
        order: str | None = None,
        page: int | None = None,
    ) -> RecordPage:
        spec = self._spec(object_type)
        table = self.table(spec.name)
        page_size = self._page_size(limit)
        conds: list[Any] = [table.c.tenant_id == actor.tenant_id]
        if not include_deleted:
            conds.append(table.c.deleted_at.is_(None))
        conds.extend(self._visibility_conditions(actor, spec, table))
        if updated_since is not None:
            conds.append(table.c.updated_at >= updated_since)
        allowed_filters = set(spec.filterable_fields) | set(OWNERSHIP_KEYS)
        for key, value in (filters or {}).items():
            if value in (None, ''):
                continue
            if str(key) not in allowed_filters:
                continue
            conds.append(table.c[str(key)] == value)
        keyword = str(q or '').strip()
        if keyword:
            like = f'%{keyword}%'
            options = [table.c[name].ilike(like) for name in spec.search_fields]
            options.append(table.c.id.ilike(like))
            if 'owner_id' in allowed_filters:
                options.append(table.c.owner_id.ilike(like))
            conds.append(or_(*options))
        descending = str(order or '').lower() == 'desc'
        keyset = not descending and page is None
        with self.engine.begin() as conn:
            total = int(conn.execute(select(func.count()).select_from(table).where(*conds)).scalar_one())
            if keyset:
                if cursor:
                    last_updated, last_id = decode_cursor(cursor)
                    conds.append(
                        or_(
                            table.c.updated_at > last_updated,
                            and_(table.c.updated_at == last_updated, table.c.id > last_id),
                        )
                    )
                order_by = (table.c.updated_at.asc(), table.c.id.asc())
                offset = 0
            else:
                column = self._sort_column(spec, table, sort)
                order_by = (column.desc() if descending else column.asc(), table.c.id.asc())
                offset = max(0, (max(1, int(page or 1)) - 1) * page_size)
            # keyset 模式下多取一行：用于判断是否还有下一页，避免让调用方多发一次空请求
            probe = page_size + 1 if keyset else page_size
            rows = conn.execute(
                select(table).where(*conds).order_by(*order_by).limit(probe).offset(offset)
            ).all()
        has_more = keyset and len(rows) > page_size
        visible_rows = rows[:page_size] if keyset else rows
        items = [self.serialize(spec, row._mapping) for row in visible_rows]
        next_cursor = None
        if has_more and visible_rows:
            last = dict(visible_rows[-1]._mapping)
            next_cursor = encode_cursor(last['updated_at'], str(last['id']))
        return RecordPage(items=items, next_cursor=next_cursor, total=total)

    def _sort_column(self, spec: ObjectSpec, table: Table, sort: str | None):
        name = str(sort or 'updated_at').strip()
        if name in SORTABLE_COMMON or spec.field(name) is not None:
            return table.c[name]
        raise ValidationError(f'不支持按 {name} 排序')

    def _row(
        self,
        conn: Any,
        spec: ObjectSpec,
        table: Table,
        actor: Actor,
        record_id: str,
        *,
        include_deleted: bool = False,
    ):
        conds: list[Any] = [table.c.tenant_id == actor.tenant_id, table.c.id == str(record_id)]
        if not include_deleted:
            conds.append(table.c.deleted_at.is_(None))
        conds.extend(self._visibility_conditions(actor, spec, table))
        return conn.execute(select(table).where(*conds)).first()

    def get_record(
        self, actor: Actor, object_type: str, record_id: str, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        spec = self._spec(object_type)
        table = self.table(spec.name)
        with self.engine.begin() as conn:
            row = self._row(conn, spec, table, actor, record_id, include_deleted=include_deleted)
            return self.serialize(spec, row._mapping) if row is not None else None

    def require_record(self, actor: Actor, object_type: str, record_id: str) -> dict[str, Any]:
        found = self.get_record(actor, object_type, record_id)
        if found is None:
            raise NotFound('记录不存在或无权访问')
        return found

    # ---- 写入 ----
    def _check_required(self, spec: ObjectSpec, values: dict[str, Any], *, creating: bool) -> None:
        for name in spec.required_fields:
            if name not in values:
                if creating:
                    raise ValidationError(f'缺少必填字段：{name}')
                continue
            value = values[name]
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValidationError(f'字段不能为空：{name}')

    def _coerce(self, field: Field, value: Any) -> Any:
        if value is None:
            return None
        kind = field.kind
        if kind == 'bool':
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in ('1', 'true', 'yes', 'y', '是'):
                return True
            if text in ('0', 'false', 'no', 'n', '否'):
                return False
            raise ValidationError(f'{field.name} 必须是布尔值')
        if kind == 'decimal':
            try:
                return Decimal(str(value).strip())
            except (InvalidOperation, ValueError) as exc:
                raise ValidationError(f'{field.name} 必须是数字') from exc
        if kind == 'date':
            return self._coerce_date(field, value)
        if kind == 'datetime':
            return self._coerce_datetime(field, value)
        text = str(value).strip()
        if kind == 'email':
            if not text:
                return None
            if not EMAIL_PATTERN.match(text):
                raise ValidationError(f'{field.name} 必须是有效的邮箱地址')
            return text
        if kind == 'enum':
            if not text:
                return None
            if text not in field.options:
                raise ValidationError(f'{field.name} 取值必须是 ' + '/'.join(field.options) + ' 之一')
            return text
        return text

    @staticmethod
    def _coerce_date(field: Field, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise ValidationError(f'{field.name} 必须是 YYYY-MM-DD 格式的日期') from exc

    @staticmethod
    def _coerce_datetime(field: Field, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return aware.astimezone(timezone.utc).replace(tzinfo=None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        text = str(value).strip()
        if not text:
            return None
        candidate = text[:-1] + '+00:00' if text.endswith('Z') else text
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            try:
                return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
            except ValueError as exc:
                raise ValidationError(f'{field.name} 必须是 ISO 8601 时间') from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)

    def _split_payload(
        self, spec: ObjectSpec, data: dict[str, Any], *, current_extras: Any = None
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        '''把入参拆成 已知字段 / 未知字段(extra) / 密码。'''
        values: dict[str, Any] = {}
        extras: dict[str, Any] = dict(current_extras) if isinstance(current_extras, dict) else {}
        password = ''
        for raw_key, raw_value in (data or {}).items():
            key = str(raw_key)
            if key in IGNORED_INPUT_KEYS:
                continue
            if key == 'extra':
                if isinstance(raw_value, dict):
                    extras.update({str(k): v for k, v in raw_value.items()})
                continue
            field = spec.field(key)
            if field is None:
                # 归属列不对对象生效时由 _resolve_*_ownership 处理，不进 extra
                if key in OWNERSHIP_KEYS:
                    continue
                extras[key] = raw_value
                continue
            if field.kind == 'password':
                password = str(raw_value or '')
                continue
            values[key] = self._coerce(field, raw_value)
        return values, extras, password

    @staticmethod
    def _normalize_aliases(data: dict[str, Any]) -> dict[str, Any]:
        '''出参里归属是 team_ids 数组，入参就同样接受 team_ids，避免读了写不回。

        单团队模型下取数组里第一个非空值；同时把 team_ids 从入参里摘掉，
        防止它以未知字段的身份落进 extra。
        '''
        payload = dict(data or {})
        if 'team_ids' in payload:
            raw = payload.pop('team_ids')
            if 'team_id' not in payload:
                values = raw if isinstance(raw, (list, tuple, set)) else [raw]
                first = next((str(item).strip() for item in values if str(item).strip()), '')
                payload['team_id'] = first or None
        return payload

    def _next_id(self, conn: Any, spec: ObjectSpec) -> str:
        table = self.table(spec.name)
        for _ in range(MAX_ID_ATTEMPTS):
            candidate = f'{spec.id_prefix}-{uuid4().hex[:10]}'
            exists = conn.execute(
                select(func.count()).select_from(table).where(table.c.id == candidate)
            ).scalar_one()
            if not exists:
                return candidate
        raise Conflict('ID 生成冲突，请重试')

    def _find_record_any(self, conn: Any, actor: Actor, record_id: str) -> dict[str, Any] | None:
        '''跨对象类型按 ID 找一条可见记录，用于备注/任务继承归属。'''
        target = str(record_id or '').strip()
        if not target:
            return None
        for spec in OBJECTS.values():
            table = self.table(spec.name)
            row = self._row(conn, spec, table, actor, target)
            if row is not None:
                found = dict(row._mapping)
                found['object_type'] = spec.name
                return found
        return None

    def _resolve_create_ownership(
        self, actor: Actor, data: dict[str, Any], target: dict[str, Any] | None
    ) -> tuple[str | None, str | None]:
        owner = str(data.get('owner_id') or '').strip()
        team = str(data.get('team_id') or '').strip()
        if target:
            owner = owner or str(target.get('owner_id') or '')
            team = team or str(target.get('team_id') or '')
        owner = owner or str(actor.on_behalf_of or '') or actor.user_id
        team = team or str(actor.team_id or '')
        if not actor.sees_all:
            allowed = owner == actor.user_id or (bool(actor.team_id) and team == actor.team_id)
            if not allowed:
                raise Forbidden('无权在该记录下创建数据')
        return owner or None, team or None

    def _resolve_update_ownership(
        self, actor: Actor, data: dict[str, Any], row: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        owner = row.get('owner_id')
        team = row.get('team_id')
        if 'owner_id' in (data or {}):
            new_owner = str(data.get('owner_id') or '').strip() or None
            if new_owner != owner:
                if not actor.sees_all and actor.role != 'manager':
                    raise Forbidden('无权变更负责人')
                owner = new_owner
        if 'team_id' in (data or {}):
            new_team = str(data.get('team_id') or '').strip() or None
            if new_team != team:
                if not actor.sees_all:
                    raise Forbidden('无权变更归属团队')
                team = new_team
        return owner, team

    def create_record(self, actor: Actor, object_type: str, data: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(object_type)
        table = self.table(spec.name)
        payload = self._normalize_aliases(data)
        if spec.name == 'users':
            self._assert_can_manage_users(actor)
        values, extras, password = self._split_payload(spec, payload)
        self._check_required(spec, values, creating=True)
        now = utcnow()
        with self.engine.begin() as conn:
            target = self._find_record_any(conn, actor, str(values.get('target_id') or ''))
            owner, team = self._resolve_create_ownership(actor, payload, target)
            record_id = self._next_id(conn, spec)
            row: dict[str, Any] = {
                'id': record_id,
                'tenant_id': actor.tenant_id,
                'version': '1',
                'created_at': now,
                'updated_at': now,
                'created_by': actor.user_id,
                'owner_id': owner,
                'team_id': team,
                'deleted_at': None,
                'extra': extras or None,
                **values,
            }
            if spec.name == 'users':
                email = str(values.get('email') or '').strip().lower()
                if not email:
                    raise ValidationError('缺少必填字段：email')
                if self._email_taken(conn, email):
                    raise Conflict('邮箱已存在')
                row['email'] = email
                row['password_hash'] = hash_password(password) if password else ''
                if 'is_active' not in values:
                    row['is_active'] = True
            conn.execute(insert(table).values(**row))
        # 未填写的可选字段补齐成 null：保证创建响应与 GET、列表的字段集合一致
        for field in spec.fields:
            row.setdefault(field.name, None)
        return self.serialize(spec, row)

    def update_record(
        self, actor: Actor, object_type: str, record_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        spec = self._spec(object_type)
        table = self.table(spec.name)
        payload = self._normalize_aliases(data)
        with self.engine.begin() as conn:
            found = self._row(conn, spec, table, actor, record_id)
            if found is None:
                raise NotFound('记录不存在或无权访问')
            row = dict(found._mapping)
            if not self.can_write(actor, spec, row):
                raise Forbidden('无权修改该记录')
            if spec.name == 'users':
                self._assert_can_manage_users(actor)
            expected = payload.get('version')
            if expected not in (None, '') and str(expected) != str(row.get('version')):
                raise Conflict(f'版本冲突：当前版本 {row.get("version")}')
            values, extras, password = self._split_payload(
                spec, payload, current_extras=row.get('extra')
            )
            self._check_required(spec, values, creating=False)
            owner, team = self._resolve_update_ownership(actor, payload, row)
            updates: dict[str, Any] = {
                **values,
                'owner_id': owner,
                'team_id': team,
                'extra': extras or None,
                'version': _bump_version(row.get('version')),
                'updated_at': utcnow(),
            }
            if spec.name == 'users':
                if 'email' in values:
                    email = str(values.get('email') or '').strip().lower()
                    if not email:
                        raise ValidationError('字段不能为空：email')
                    if self._email_taken(conn, email, exclude_id=str(record_id)):
                        raise Conflict('邮箱已存在')
                    updates['email'] = email
                if password:
                    updates['password_hash'] = hash_password(password)
            conn.execute(update(table).where(table.c.id == str(record_id)).values(**updates))
            row.update(updates)
        return self.serialize(spec, row)

    def delete_record(self, actor: Actor, object_type: str, record_id: str) -> dict[str, Any]:
        spec = self._spec(object_type)
        table = self.table(spec.name)
        with self.engine.begin() as conn:
            found = self._row(conn, spec, table, actor, record_id)
            if found is None:
                raise NotFound('记录不存在或无权访问')
            row = dict(found._mapping)
            if not self.can_write(actor, spec, row):
                raise Forbidden('无权删除该记录')
            if spec.name == 'users':
                self._assert_can_manage_users(actor)
            now = utcnow()
            updates = {'deleted_at': now, 'updated_at': now, 'version': _bump_version(row.get('version'))}
            conn.execute(update(table).where(table.c.id == str(record_id)).values(**updates))
            row.update(updates)
        return self.serialize(spec, row)

    def _email_taken(self, conn: Any, email: str, *, exclude_id: str | None = None) -> bool:
        table = self.table('users')
        conds = [func.lower(table.c.email) == email.lower()]
        if exclude_id:
            conds.append(table.c.id != exclude_id)
        return bool(conn.execute(select(func.count()).select_from(table).where(*conds)).scalar_one())

    def set_password(self, user_id: str, password: str) -> None:
        '''改密码走独立入口：用户改自己的密码不需要对象级写权限。'''
        raw = str(password or '')
        if len(raw) < 6:
            raise ValidationError('密码至少 6 位')
        table = self.table('users')
        with self.engine.begin() as conn:
            found = conn.execute(
                select(table).where(
                    table.c.id == str(user_id), table.c.deleted_at.is_(None)
                )
            ).first()
            if found is None:
                raise NotFound('用户不存在')
            conn.execute(
                update(table)
                .where(table.c.id == str(user_id))
                .values(
                    password_hash=hash_password(raw),
                    updated_at=utcnow(),
                    version=_bump_version(dict(found._mapping).get('version')),
                )
            )

    # ---- 初始化数据（仅供 seed 使用，按给定 id/version/updated_at 原样写入）----
    def seed_rows(self, object_type: str, rows: list[dict[str, Any]]) -> int:
        spec = self._spec(object_type)
        table = self.table(spec.name)
        stamp_field = Field('updated_at', 'datetime', '更新时间')
        inserted = 0
        with self.engine.begin() as conn:
            for raw in rows:
                record_id = str(raw.get('id') or '')
                if not record_id:
                    raise ValidationError('演示数据缺少 id')
                exists = conn.execute(
                    select(func.count()).select_from(table).where(table.c.id == record_id)
                ).scalar_one()
                if exists:
                    continue
                values, extras, password = self._split_payload(spec, raw)
                stamp = self._coerce_datetime(stamp_field, raw.get('updated_at')) or utcnow()
                row: dict[str, Any] = {
                    'id': record_id,
                    'tenant_id': raw.get('tenant_id') or self._settings.tenant_id,
                    'version': str(raw.get('version') or '1'),
                    'created_at': stamp,
                    'updated_at': stamp,
                    'created_by': raw.get('created_by') or 'seed',
                    'owner_id': raw.get('owner_id'),
                    'team_id': raw.get('team_id'),
                    'deleted_at': None,
                    'extra': extras or None,
                    **values,
                }
                if spec.name == 'users':
                    row['email'] = str(values.get('email') or '').lower()
                    row['password_hash'] = hash_password(password) if password else ''
                    if 'is_active' not in values:
                        row['is_active'] = True
                conn.execute(insert(table).values(**row))
                inserted += 1
        return inserted

    def seed_teams(self, rows: list[dict[str, Any]]) -> int:
        table = self.table(TEAMS_TABLE)
        inserted = 0
        with self.engine.begin() as conn:
            for raw in rows:
                team_id = str(raw.get('id') or '')
                if not team_id:
                    raise ValidationError('演示团队缺少 id')
                exists = conn.execute(
                    select(func.count()).select_from(table).where(table.c.id == team_id)
                ).scalar_one()
                if exists:
                    continue
                now = utcnow()
                conn.execute(
                    insert(table).values(
                        id=team_id,
                        tenant_id=self._settings.tenant_id,
                        name=str(raw.get('name') or team_id),
                        version='1',
                        created_at=now,
                        updated_at=now,
                        created_by='seed',
                        owner_id=None,
                        team_id=None,
                        deleted_at=None,
                    )
                )
                inserted += 1
        return inserted

    # ---- 审计 ----
    def add_audit(
        self,
        actor: Actor,
        *,
        source: str,
        method: str,
        path: str,
        object_type: str,
        record_id: str | None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        table = self.table(AUDIT_TABLE)
        with self.engine.begin() as conn:
            conn.execute(
                insert(table).values(
                    at=utcnow(),
                    tenant_id=actor.tenant_id,
                    actor_id=actor.user_id,
                    actor_kind=actor.kind,
                    on_behalf_of=actor.on_behalf_of,
                    source=source,
                    method=method,
                    path=path[:256],
                    object_type=object_type,
                    record_id=record_id,
                    before=before,
                    after=after,
                    idempotency_key=idempotency_key,
                )
            )

    def list_audit(
        self,
        actor: Actor,
        *,
        limit: int = 100,
        object_type: str | None = None,
        record_id: str | None = None,
    ) -> list[dict[str, Any]]:
        table = self.table(AUDIT_TABLE)
        conds: list[Any] = [table.c.tenant_id == actor.tenant_id]
        if object_type:
            conds.append(table.c.object_type == str(object_type))
        if record_id:
            conds.append(table.c.record_id == str(record_id))
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(table).where(*conds).order_by(table.c.id.desc()).limit(min(max(1, limit), 500))
            ).all()
        return [
            {key: _jsonable(value) for key, value in dict(row._mapping).items()} for row in rows
        ]

    # ---- 幂等 ----
    def find_idempotent(self, actor_key: str, key: str) -> dict[str, Any] | None:
        table = self.table(IDEMPOTENCY_TABLE)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(table).where(table.c.actor == actor_key, table.c.key == key)
            ).first()
            return dict(row._mapping) if row is not None else None

    def save_idempotent(
        self,
        actor_key: str,
        key: str,
        *,
        method: str,
        path: str,
        request_hash: str,
        status_code: int,
        response: dict[str, Any] | None,
    ) -> None:
        table = self.table(IDEMPOTENCY_TABLE)
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(func.count()).select_from(table).where(
                    table.c.actor == actor_key, table.c.key == key
                )
            ).scalar_one()
            if exists:
                return
            conn.execute(
                insert(table).values(
                    actor=actor_key,
                    key=key[:200],
                    method=method.upper(),
                    path=path[:256],
                    request_hash=request_hash,
                    status_code=int(status_code),
                    response=response,
                    created_at=utcnow(),
                )
            )

    # ---- 用户与团队 ----
    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        table = self.table('users')
        target = str(email or '').strip().lower()
        if not target:
            return None
        with self.engine.begin() as conn:
            row = conn.execute(
                select(table).where(
                    func.lower(table.c.email) == target, table.c.deleted_at.is_(None)
                )
            ).first()
            return dict(row._mapping) if row is not None else None

    def get_user_row(self, user_id: str) -> dict[str, Any] | None:
        table = self.table('users')
        with self.engine.begin() as conn:
            row = conn.execute(
                select(table).where(table.c.id == str(user_id), table.c.deleted_at.is_(None))
            ).first()
            return dict(row._mapping) if row is not None else None

    def count_users(self) -> int:
        table = self.table('users')
        with self.engine.begin() as conn:
            return int(conn.execute(select(func.count()).select_from(table)).scalar_one())

    def team_members(self, team_id: str) -> int:
        table = self.table('users')
        with self.engine.begin() as conn:
            return int(
                conn.execute(
                    select(func.count())
                    .select_from(table)
                    .where(table.c.team_id == str(team_id), table.c.deleted_at.is_(None))
                ).scalar_one()
            )

    def list_teams(self, actor: Actor) -> list[dict[str, Any]]:
        table = self.table(TEAMS_TABLE)
        conds: list[Any] = [table.c.tenant_id == actor.tenant_id, table.c.deleted_at.is_(None)]
        if not actor.sees_all:
            if not actor.team_id:
                return []
            conds.append(table.c.id == actor.team_id)
        with self.engine.begin() as conn:
            rows = conn.execute(select(table).where(*conds).order_by(table.c.name.asc())).all()
        return [self._serialize_team(row._mapping) for row in rows]

    def get_team(self, actor: Actor, team_id: str) -> dict[str, Any] | None:
        table = self.table(TEAMS_TABLE)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(table).where(
                    table.c.tenant_id == actor.tenant_id,
                    table.c.id == str(team_id),
                    table.c.deleted_at.is_(None),
                )
            ).first()
            return self._serialize_team(row._mapping) if row is not None else None

    def _serialize_team(self, source: Any) -> dict[str, Any]:
        raw = dict(source)
        return {
            'id': raw.get('id'),
            'name': raw.get('name') or '',
            'version': raw.get('version') or '1',
            'created_at': _jsonable(raw.get('created_at')),
            'updated_at': _jsonable(raw.get('updated_at')),
            'member_count': self.team_members(str(raw.get('id') or '')),
        }

    def create_team(self, actor: Actor, data: dict[str, Any]) -> dict[str, Any]:
        self._assert_can_manage_users(actor)
        name = str((data or {}).get('name') or '').strip()
        if not name:
            raise ValidationError('缺少必填字段：name')
        table = self.table(TEAMS_TABLE)
        now = utcnow()
        team_id = str((data or {}).get('id') or '').strip() or f'team-{uuid4().hex[:10]}'
        row = {
            'id': team_id,
            'tenant_id': actor.tenant_id,
            'name': name,
            'version': '1',
            'created_at': now,
            'updated_at': now,
            'created_by': actor.user_id,
            'owner_id': None,
            'team_id': None,
            'deleted_at': None,
        }
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(func.count()).select_from(table).where(table.c.id == team_id)
            ).scalar_one()
            if exists:
                raise Conflict('团队 ID 已存在')
            conn.execute(insert(table).values(**row))
        return self._serialize_team(row)

    def update_team(self, actor: Actor, team_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._assert_can_manage_users(actor)
        table = self.table(TEAMS_TABLE)
        with self.engine.begin() as conn:
            found = conn.execute(
                select(table).where(
                    table.c.tenant_id == actor.tenant_id,
                    table.c.id == str(team_id),
                    table.c.deleted_at.is_(None),
                )
            ).first()
            if found is None:
                raise NotFound('团队不存在')
            row = dict(found._mapping)
            name = str((data or {}).get('name') or '').strip()
            if not name:
                raise ValidationError('缺少必填字段：name')
            updates = {'name': name, 'updated_at': utcnow(), 'version': _bump_version(row.get('version'))}
            conn.execute(update(table).where(table.c.id == str(team_id)).values(**updates))
            row.update(updates)
        return self._serialize_team(row)

    def delete_team(self, actor: Actor, team_id: str) -> dict[str, Any]:
        self._assert_can_manage_users(actor)
        table = self.table(TEAMS_TABLE)
        with self.engine.begin() as conn:
            found = conn.execute(
                select(table).where(
                    table.c.tenant_id == actor.tenant_id,
                    table.c.id == str(team_id),
                    table.c.deleted_at.is_(None),
                )
            ).first()
            if found is None:
                raise NotFound('团队不存在')
            row = dict(found._mapping)
            now = utcnow()
            updates = {'deleted_at': now, 'updated_at': now, 'version': _bump_version(row.get('version'))}
            conn.execute(update(table).where(table.c.id == str(team_id)).values(**updates))
            row.update(updates)
        return self._serialize_team(row)

    # ---- 统计 ----
    def stats(self, actor: Actor) -> dict[str, Any]:
        '''仪表盘口径：对象计数、采购/销售状态分布、库存与应收应付敞口。'''
        with self.engine.begin() as conn:
            counts = self._counts(conn, actor)
            purchase_pipeline = self._pipeline(conn, actor, 'purchase_orders')
            sales_pipeline = self._pipeline(conn, actor, 'sales_orders')
            balances = self._stock_balances(conn, actor)
            low_stock, stock_value = self._stock_health(conn, actor, balances)
            exposure = self._invoice_exposure(conn, actor)
        recent = self.list_records(actor, 'stock_moves', limit=5, order='desc', page=1).items
        return {
            'counts': counts,
            'purchase_pipeline': purchase_pipeline,
            'purchase_amount': float(sum(item['amount'] for item in purchase_pipeline)),
            'open_purchase_orders': sum(
                item['count'] for item in purchase_pipeline if item['status'] in OPEN_PO_STATUSES
            ),
            'sales_pipeline': sales_pipeline,
            'sales_amount': float(sum(item['amount'] for item in sales_pipeline)),
            'open_sales_orders': sum(
                item['count'] for item in sales_pipeline if item['status'] in OPEN_SO_STATUSES
            ),
            'low_stock_items': low_stock,
            'low_stock_count': len(low_stock),
            'stock_value': stock_value,
            'receivable_open': exposure['receivable'],
            'payable_open': exposure['payable'],
            'open_invoices': exposure['count'],
            'recent_moves': recent,
        }

    def _counts(self, conn: Any, actor: Actor) -> dict[str, int]:
        counts: dict[str, int] = {}
        for spec in OBJECTS.values():
            table = self.table(spec.name)
            conds: list[Any] = [
                table.c.tenant_id == actor.tenant_id,
                table.c.deleted_at.is_(None),
                *self._visibility_conditions(actor, spec, table),
            ]
            counts[spec.name] = int(
                conn.execute(select(func.count()).select_from(table).where(*conds)).scalar_one()
            )
        return counts

    def _pipeline(
        self, conn: Any, actor: Actor, object_type: str
    ) -> list[dict[str, Any]]:
        '''按状态聚合单据数量与金额：订单对象都有 status 与 amount 两个字段。'''
        spec = self._spec(object_type)
        table = self.table(object_type)
        conds: list[Any] = [
            table.c.tenant_id == actor.tenant_id,
            table.c.deleted_at.is_(None),
            *self._visibility_conditions(actor, spec, table),
        ]
        column = table.c['status']
        rows = conn.execute(
            select(column, func.count(), func.coalesce(func.sum(table.c.amount), 0))
            .where(*conds)
            .group_by(column)
        ).all()
        return [
            {'status': str(row[0] or ''), 'count': int(row[1]), 'amount': float(row[2] or 0)}
            for row in rows
        ]

    def _stock_balances(self, conn: Any, actor: Actor) -> dict[str, float]:
        '''按物料汇总库存：出库类型取负，其余为正。'''
        spec = self._spec('stock_moves')
        table = self.table('stock_moves')
        conds: list[Any] = [
            table.c.tenant_id == actor.tenant_id,
            table.c.deleted_at.is_(None),
            *self._visibility_conditions(actor, spec, table),
        ]
        signed = case(
            (table.c.kind.in_(OUTBOUND_MOVE_KINDS), -table.c.quantity), else_=table.c.quantity
        )
        rows = conn.execute(
            select(table.c.item_id, func.sum(signed)).where(*conds).group_by(table.c.item_id)
        ).all()
        return {str(row[0]): float(row[1] or 0) for row in rows if row[0]}

    def _stock_health(
        self, conn: Any, actor: Actor, balances: dict[str, float]
    ) -> tuple[list[dict[str, Any]], float]:
        '''低于安全库存的物料清单，以及按标准成本估算的库存金额。'''
        spec = self._spec('items')
        table = self.table('items')
        conds: list[Any] = [
            table.c.tenant_id == actor.tenant_id,
            table.c.deleted_at.is_(None),
            *self._visibility_conditions(actor, spec, table),
        ]
        rows = conn.execute(
            select(table.c.id, table.c.sku, table.c.name, table.c.safety_stock, table.c.cost).where(
                *conds
            )
        ).all()
        low: list[dict[str, Any]] = []
        stock_value = 0.0
        for row in rows:
            balance = float(balances.get(str(row[0]), 0.0))
            stock_value += balance * float(row[4] or 0)
            safety = float(row[3] or 0)
            if safety > 0 and balance < safety:
                low.append(
                    {
                        'id': row[0],
                        'sku': row[1],
                        'name': row[2],
                        'balance': balance,
                        'safety_stock': safety,
                    }
                )
        low.sort(key=lambda item: item['balance'])
        return low[:MAX_LOW_STOCK_ROWS], stock_value

    def _invoice_exposure(self, conn: Any, actor: Actor) -> dict[str, Any]:
        '''未结清发票的应收与应付金额合计。'''
        spec = self._spec('invoices')
        table = self.table('invoices')
        conds: list[Any] = [
            table.c.tenant_id == actor.tenant_id,
            table.c.deleted_at.is_(None),
            *self._visibility_conditions(actor, spec, table),
            table.c.status.in_(OPEN_INVOICE_STATUSES),
        ]
        rows = conn.execute(
            select(table.c.direction, func.count(), func.coalesce(func.sum(table.c.amount), 0))
            .where(*conds)
            .group_by(table.c.direction)
        ).all()
        exposure: dict[str, Any] = {'receivable': 0.0, 'payable': 0.0, 'count': 0}
        for row in rows:
            exposure[str(row[0] or '')] = float(row[2] or 0)
            exposure['count'] += int(row[1])
        return exposure

# ---- 游标与工厂 ----
import base64  # noqa: E402  （放在类定义之后，仅本模块使用）


def encode_cursor(updated_at: datetime, record_id: str) -> str:
    '''keyset 游标：不透明 base64，内容为 updated_at 与 id。'''
    raw = f'{to_iso(updated_at)}|{record_id}'
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = str(cursor) + '=' * (-len(str(cursor)) % 4)
        raw = base64.urlsafe_b64decode(padded).decode('utf-8')
        stamp, _, record_id = raw.partition('|')
        parsed = datetime.fromisoformat(stamp)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValidationError('cursor 非法') from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None), record_id


def build_store(settings: Settings) -> SqlStore:
    return SqlStore(settings)
