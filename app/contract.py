'''对外契约与业务字段元数据。

这个文件是两件事的唯一来源：

1. 对象类型与字段名必须与 D:/codex 的 app/integrations/erp/field_map.py 一致
   （AI 能力层按这些名字做字段映射，改这里等于改对接契约）；
2. 字段类型、必填、枚举与中文标签，供校验、建表、序列化与前端表单复用。

公共列（id / version / created_at / updated_at / owner_id / team_id / deleted_at）
由存储层统一提供，不写在各对象里。

对象分四块：主数据（物料、供应商、客户、仓库）、采购、销售、库存流水与应收应付。
订单头和订单行拆成两个扁平对象（purchase_orders / purchase_order_lines），
这样所有对象都能用同一套同步与字段映射逻辑，AI 层不必处理嵌套结构。

枚举按「枚举名」登记，不按字段名：采购单、销售单、发票都有 status，取值集合并不相同。
'''

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMMON_FIELDS: tuple[str, ...] = (
    'id',
    'version',
    'created_at',
    'updated_at',
    'created_by',
    'owner_id',
    'team_id',
    'deleted_at',
)

PARTNER_GRADES: tuple[str, ...] = ('A', 'B', 'C', 'D')
PARTNER_GRADE_LABELS: dict[str, str] = {
    'A': '优秀',
    'B': '良好',
    'C': '合格',
    'D': '观察',
}
PO_STATUSES: tuple[str, ...] = (
    'draft',
    'submitted',
    'approved',
    'partial',
    'received',
    'cancelled',
)
PO_STATUS_LABELS: dict[str, str] = {
    'draft': '草稿',
    'submitted': '已提交',
    'approved': '已审批',
    'partial': '部分到货',
    'received': '已入库',
    'cancelled': '已取消',
}
SO_STATUSES: tuple[str, ...] = (
    'draft',
    'confirmed',
    'partial',
    'shipped',
    'closed',
    'cancelled',
)
SO_STATUS_LABELS: dict[str, str] = {
    'draft': '草稿',
    'confirmed': '已确认',
    'partial': '部分发货',
    'shipped': '已发货',
    'closed': '已关闭',
    'cancelled': '已取消',
}
MOVE_KINDS: tuple[str, ...] = ('receipt', 'issue', 'transfer_in', 'transfer_out', 'adjust')
MOVE_KIND_LABELS: dict[str, str] = {
    'receipt': '采购入库',
    'issue': '销售出库',
    'transfer_in': '调拨入',
    'transfer_out': '调拨出',
    'adjust': '盘点调整',
}
INVOICE_DIRECTIONS: tuple[str, ...] = ('receivable', 'payable')
INVOICE_DIRECTION_LABELS: dict[str, str] = {'receivable': '应收', 'payable': '应付'}
INVOICE_STATUSES: tuple[str, ...] = (
    'draft',
    'issued',
    'partial',
    'settled',
    'overdue',
    'void',
)
INVOICE_STATUS_LABELS: dict[str, str] = {
    'draft': '草稿',
    'issued': '已开具',
    'partial': '部分结算',
    'settled': '已结清',
    'overdue': '逾期',
    'void': '已作废',
}
USER_ROLES: tuple[str, ...] = ('admin', 'manager', 'staff')
ROLE_LABELS: dict[str, str] = {
    'admin': '管理员',
    'manager': '部门主管',
    'staff': '职员',
    'service': '服务账号',
}
SERVICE_ROLE = 'service'

STR_KINDS = frozenset({'str', 'text', 'email', 'phone', 'enum', 'ref'})

ENUM_OPTIONS: dict[str, tuple[str, ...]] = {
    'grade': PARTNER_GRADES,
    'po_status': PO_STATUSES,
    'so_status': SO_STATUSES,
    'move_kind': MOVE_KINDS,
    'invoice_direction': INVOICE_DIRECTIONS,
    'invoice_status': INVOICE_STATUSES,
    'role': USER_ROLES,
}
ENUM_LABELS: dict[str, dict[str, str]] = {
    'grade': PARTNER_GRADE_LABELS,
    'po_status': PO_STATUS_LABELS,
    'so_status': SO_STATUS_LABELS,
    'move_kind': MOVE_KIND_LABELS,
    'invoice_direction': INVOICE_DIRECTION_LABELS,
    'invoice_status': INVOICE_STATUS_LABELS,
    'role': ROLE_LABELS,
}


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    label: str
    required: bool = False
    ref: str | None = None
    in_list: bool = False
    filterable: bool = False
    write_only: bool = False
    enum: str = ''

    @property
    def options(self) -> tuple[str, ...]:
        return ENUM_OPTIONS.get(self.enum, ())

    def to_public(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'kind': self.kind,
            'label': self.label,
            'required': self.required,
            'ref': self.ref,
            'in_list': self.in_list,
            'filterable': self.filterable,
            'write_only': self.write_only,
            'enum': self.enum,
            'options': [
                {'value': value, 'label': ENUM_LABELS.get(self.enum, {}).get(value, value)}
                for value in self.options
            ],
        }


@dataclass(frozen=True)
class ObjectSpec:
    name: str
    label: str
    singular: str
    id_prefix: str
    fields: tuple[Field, ...]
    title_field: str
    default_sort: str = 'updated_at'
    default_order: str = 'desc'
    related_by: tuple[str, ...] = ()

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields)

    @property
    def list_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields if item.in_list and not item.write_only)

    @property
    def filterable_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields if item.filterable)

    @property
    def search_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields if item.kind in STR_KINDS)

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields if item.required)

    def field(self, name: str) -> Field | None:
        for item in self.fields:
            if item.name == name:
                return item
        return None

    def to_public(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'label': self.label,
            'singular': self.singular,
            'title_field': self.title_field,
            'default_sort': self.default_sort,
            'default_order': self.default_order,
            'list_fields': list(self.list_fields),
            'filterable_fields': list(self.filterable_fields),
            'required_fields': list(self.required_fields),
            'search_fields': list(self.search_fields),
            'related_by': list(self.related_by),
            'fields': [item.to_public() for item in self.fields],
        }


OBJECTS: dict[str, ObjectSpec] = {
    'items': ObjectSpec(
        name='items',
        label='物料',
        singular='物料',
        id_prefix='item',
        title_field='name',
        fields=(
            Field('sku', 'str', '物料编码', required=True, in_list=True, filterable=True),
            Field('name', 'str', '物料名称', required=True, in_list=True),
            Field('category', 'str', '分类', in_list=True, filterable=True),
            Field('spec', 'str', '规格'),
            Field('unit', 'str', '单位', required=True, in_list=True),
            Field('price', 'decimal', '销售单价', in_list=True),
            Field('cost', 'decimal', '标准成本'),
            Field('safety_stock', 'decimal', '安全库存', in_list=True),
            Field('is_active', 'bool', '启用'),
        ),
    ),
    'suppliers': ObjectSpec(
        name='suppliers',
        label='供应商',
        singular='供应商',
        id_prefix='sup',
        title_field='name',
        fields=(
            Field('name', 'str', '供应商名称', required=True, in_list=True),
            Field('contact', 'str', '联系人', in_list=True),
            Field('phone', 'phone', '电话'),
            Field('email', 'email', '邮箱', in_list=True),
            Field('region', 'str', '区域', in_list=True, filterable=True),
            Field('payment_terms', 'str', '账期', in_list=True),
            Field('grade', 'enum', '评级', in_list=True, filterable=True, enum='grade'),
            Field('is_active', 'bool', '启用'),
        ),
    ),
    'customers': ObjectSpec(
        name='customers',
        label='客户',
        singular='客户',
        id_prefix='cus',
        title_field='name',
        fields=(
            Field('name', 'str', '客户名称', required=True, in_list=True),
            Field('contact', 'str', '联系人', in_list=True),
            Field('phone', 'phone', '电话'),
            Field('email', 'email', '邮箱', in_list=True),
            Field('region', 'str', '区域', in_list=True, filterable=True),
            Field('credit_limit', 'decimal', '信用额度', in_list=True),
            Field('payment_terms', 'str', '账期', in_list=True),
            Field('grade', 'enum', '评级', in_list=True, filterable=True, enum='grade'),
            Field('is_active', 'bool', '启用'),
        ),
    ),
    'warehouses': ObjectSpec(
        name='warehouses',
        label='仓库',
        singular='仓库',
        id_prefix='wh',
        title_field='name',
        fields=(
            Field('code', 'str', '仓库编码', required=True, in_list=True, filterable=True),
            Field('name', 'str', '仓库名称', required=True, in_list=True),
            Field('location', 'str', '所在地', in_list=True),
            Field('keeper', 'str', '仓管员', in_list=True),
            Field('is_active', 'bool', '启用'),
        ),
    ),
    'purchase_orders': ObjectSpec(
        name='purchase_orders',
        label='采购订单',
        singular='采购单',
        id_prefix='po',
        title_field='code',
        related_by=('supplier_id',),
        fields=(
            Field('code', 'str', '采购单号', required=True, in_list=True, filterable=True),
            Field('supplier_id', 'ref', '供应商', required=True, ref='suppliers', in_list=True, filterable=True),
            Field('warehouse_id', 'ref', '收货仓库', ref='warehouses', in_list=True, filterable=True),
            Field('order_date', 'date', '下单日期', required=True, in_list=True),
            Field('expected_date', 'date', '预计到货', in_list=True),
            Field('status', 'enum', '状态', required=True, in_list=True, filterable=True, enum='po_status'),
            Field('currency', 'str', '币种'),
            Field('amount', 'decimal', '金额', in_list=True),
            Field('note', 'text', '备注'),
        ),
    ),
    'purchase_order_lines': ObjectSpec(
        name='purchase_order_lines',
        label='采购订单行',
        singular='采购订单行',
        id_prefix='pol',
        title_field='order_id',
        related_by=('order_id', 'item_id'),
        fields=(
            Field('order_id', 'ref', '采购单', required=True, ref='purchase_orders', in_list=True, filterable=True),
            Field('item_id', 'ref', '物料', required=True, ref='items', in_list=True, filterable=True),
            Field('quantity', 'decimal', '数量', required=True, in_list=True),
            Field('unit_price', 'decimal', '单价', required=True, in_list=True),
            Field('received_quantity', 'decimal', '已到货数量', in_list=True),
            Field('amount', 'decimal', '行金额', in_list=True),
        ),
    ),
    'sales_orders': ObjectSpec(
        name='sales_orders',
        label='销售订单',
        singular='销售单',
        id_prefix='so',
        title_field='code',
        related_by=('customer_id',),
        fields=(
            Field('code', 'str', '销售单号', required=True, in_list=True, filterable=True),
            Field('customer_id', 'ref', '客户', required=True, ref='customers', in_list=True, filterable=True),
            Field('warehouse_id', 'ref', '发货仓库', ref='warehouses', in_list=True, filterable=True),
            Field('order_date', 'date', '下单日期', required=True, in_list=True),
            Field('delivery_date', 'date', '要求交期', in_list=True),
            Field('status', 'enum', '状态', required=True, in_list=True, filterable=True, enum='so_status'),
            Field('currency', 'str', '币种'),
            Field('amount', 'decimal', '金额', in_list=True),
            Field('note', 'text', '备注'),
        ),
    ),
    'sales_order_lines': ObjectSpec(
        name='sales_order_lines',
        label='销售订单行',
        singular='销售订单行',
        id_prefix='sol',
        title_field='order_id',
        related_by=('order_id', 'item_id'),
        fields=(
            Field('order_id', 'ref', '销售单', required=True, ref='sales_orders', in_list=True, filterable=True),
            Field('item_id', 'ref', '物料', required=True, ref='items', in_list=True, filterable=True),
            Field('quantity', 'decimal', '数量', required=True, in_list=True),
            Field('unit_price', 'decimal', '单价', required=True, in_list=True),
            Field('shipped_quantity', 'decimal', '已发货数量', in_list=True),
            Field('amount', 'decimal', '行金额', in_list=True),
        ),
    ),
    'stock_moves': ObjectSpec(
        name='stock_moves',
        label='库存流水',
        singular='库存流水',
        id_prefix='mv',
        title_field='reference',
        related_by=('item_id', 'warehouse_id'),
        fields=(
            Field('item_id', 'ref', '物料', required=True, ref='items', in_list=True, filterable=True),
            Field('warehouse_id', 'ref', '仓库', required=True, ref='warehouses', in_list=True, filterable=True),
            Field('kind', 'enum', '类型', required=True, in_list=True, filterable=True, enum='move_kind'),
            Field('quantity', 'decimal', '数量', required=True, in_list=True),
            Field('occurred_at', 'datetime', '发生时间', required=True, in_list=True),
            Field('reference', 'str', '来源单据', in_list=True, filterable=True),
            Field('note', 'text', '备注'),
        ),
    ),
    'invoices': ObjectSpec(
        name='invoices',
        label='发票',
        singular='发票',
        id_prefix='inv',
        title_field='code',
        related_by=('partner_id', 'order_id'),
        fields=(
            Field('code', 'str', '发票号', required=True, in_list=True, filterable=True),
            Field('direction', 'enum', '方向', required=True, in_list=True, filterable=True, enum='invoice_direction'),
            Field('partner_id', 'ref', '往来单位', required=True, ref='any', in_list=True, filterable=True),
            Field('order_id', 'ref', '关联订单', ref='any', in_list=True, filterable=True),
            Field('amount', 'decimal', '金额', required=True, in_list=True),
            Field('tax_amount', 'decimal', '税额', in_list=True),
            Field('issued_at', 'date', '开票日期', in_list=True),
            Field('due_at', 'date', '到期日', in_list=True),
            Field('status', 'enum', '状态', required=True, in_list=True, filterable=True, enum='invoice_status'),
            Field('note', 'text', '备注'),
        ),
    ),
    'users': ObjectSpec(
        name='users',
        label='员工',
        singular='员工',
        id_prefix='usr',
        title_field='name',
        fields=(
            Field('name', 'str', '姓名', required=True, in_list=True),
            Field('email', 'email', '邮箱', required=True, in_list=True),
            Field('team_id', 'ref', '部门', ref='teams', in_list=True, filterable=True),
            Field('role', 'enum', '角色', in_list=True, filterable=True, enum='role'),
            Field('is_active', 'bool', '启用'),
            Field('password', 'password', '密码', write_only=True),
        ),
    ),
}

OBJECT_NAMES: tuple[str, ...] = tuple(OBJECTS)
TEAMS_OBJECT = 'teams'
DEFAULT_ROLE = 'staff'


def get_object(name: str) -> ObjectSpec | None:
    return OBJECTS.get(str(name or '').strip())


def is_object_type(name: str) -> bool:
    return str(name or '') in OBJECTS


def enum_options(name: str) -> tuple[str, ...]:
    return ENUM_OPTIONS.get(str(name or ''), ())


def meta_payload() -> dict[str, Any]:
    '''给前端与联调工具的对象元数据。'''
    return {
        'objects': [OBJECTS[name].to_public() for name in OBJECT_NAMES],
        'object_names': list(OBJECT_NAMES),
        'roles': list(USER_ROLES),
        'role_labels': ROLE_LABELS,
        'enums': {
            name: [
                {'value': value, 'label': ENUM_LABELS.get(name, {}).get(value, value)}
                for value in options
            ]
            for name, options in ENUM_OPTIONS.items()
        },
    }