# 自研 ERP 管理系统

一个可直接运行的销售 ERP：FastAPI + SQLAlchemy Core 后端，
Vite + React + TypeScript 管理前端，行级数据权限、写审计与写幂等。

它同时是 **AI x ERP 能力层**（`D:\codex`）的数据底座：
AI 层只通过下面那套 REST 契约读写 ERP，两边的进程与部署完全独立。

## 界面预览

截图来自本机实跑（`npm run dev` + sqlite 演示数据，管理员视角，1440x900），
每个栏目一张，原图放在 `docs/images/`。

### 登录

用 ERP 账号登录（首次启动的管理员由 `ERP_BOOTSTRAP_ADMIN_*` 决定），
令牌存在浏览器本地，后续请求带 `Authorization: Bearer`。

![登录](docs/images/00-login.png)

### 仪表盘

对象计数、库存金额、低库存条数、未结应收应付，外加采购/销售状态分布与最近库存流水。

![仪表盘](docs/images/01-dashboard.png)

### 物料

物料主数据：编码、名称、规格、单位、成本价、安全库存。列表页统一带关键词过滤、
属性下拉过滤、分页与「显示已删除」开关，表格列由 `contract.py` 推导。

![物料](docs/images/02-items.png)

### 供应商

供应商主数据：联系方式、所属区域、账期与评级。

![供应商](docs/images/03-suppliers.png)

### 客户

客户主数据：联系方式、信用额度、账期与评级。

![客户](docs/images/04-customers.png)

### 仓库

仓库编码、名称、所在地与保管人。

![仓库](docs/images/05-warehouses.png)

### 采购订单

采购单列表：单号、供应商、收货仓库、下单与预计到货日期、状态、金额、负责人。

![采购订单](docs/images/06-purchase_orders.png)

### 采购订单详情

单据详情：版本号（乐观锁）、负责人与归属团队、单据头字段，以及挂在本单下的采购订单行；
页内可以直接新增订单行，备注栏能看到 AI 写回留下的内容。

![采购订单详情](docs/images/06-purchase_orders-detail.png)

### 新建采购订单

新建表单由契约推导：必填校验、枚举下拉，外键（供应商 / 仓库 / 负责人）选项都从接口拉。

![新建采购订单](docs/images/06-purchase_orders-form.png)

### 采购订单行

订单行通过 `order_id` 挂在采购单下，行金额按数量 × 单价计算。

![采购订单行](docs/images/07-purchase_order_lines.png)

### 销售订单

销售单列表：客户、发货仓库、状态、金额、负责人。

![销售订单](docs/images/08-sales_orders.png)

### 销售订单行

销售订单明细行，同样通过 `order_id` 关联到销售单。

![销售订单行](docs/images/09-sales_order_lines.png)

### 库存流水

唯一的库存变动台账（采购入库、销售出库、调拨进出），可用库存由它汇总得出，
不另建余额表。

![库存流水](docs/images/10-stock_moves.png)

### 发票

应收 / 应付发票，按方向与未结状态汇总出未结应收应付金额。

![发票](docs/images/11-invoices.png)

### 用户

用户与角色（admin / manager / staff）、所属团队与启停用状态。仅管理员可见。

![用户](docs/images/12-users.png)

### 团队

团队与成员；行级权限按团队划分可见范围。

![团队](docs/images/13-teams.png)

### 审计日志

每次写操作的留痕：时间、来源（human / ai）、操作者、对象与记录、方法、请求路径、
修改前后的值、幂等键。仅管理员可见，AI 写回记成 `source=ai`、`actor_kind=service`。

![审计日志](docs/images/14-audit.png)

### 设置 / AI 对接

当前账号与改密码，以及把本系统接进 AI 能力层（`D:\codex`）所需的接口地址、
`.env` 片段与只读探测命令。

![设置与 AI 对接](docs/images/15-settings.png)

## 目录结构

```text
app/
  contract.py         对象与字段元数据的唯一来源（改字段名等于改对接契约）
  core/               配置、JSON 日志、密码与自签令牌
  adapters/sql.py     存储层：建表、CRUD、行级权限、游标分页、审计、幂等
  services/records.py 用例层：幂等回放、审计落库、时间解析
  api/                路由、请求响应模型、身份依赖
  seed.py             演示数据（ID 与 AI 层 fake 模式保持一致）
  container.py        依赖装配与初始化
  main.py             FastAPI 入口，附带前端静态托管
web/                  Vite + React + TypeScript + Tailwind 管理前端
tests/                标准库 unittest 测试集（sqlite 临时库 + TestClient）
docs/runbook.md       全栈启动手册（含 AI 能力层与向量模型）
```

## 快速开始

```powershell
cd D:\erp
pip install -r requirements.txt
copy .env.example .env

# 默认 sqlite，零外部依赖，首次启动自动建表 + 演示数据 + 管理员
python -m uvicorn app.main:app --host 127.0.0.1 --port 9200
```

- 健康检查：`http://127.0.0.1:9200/health`
- 接口文档：`http://127.0.0.1:9200/docs`
- 管理界面：`http://127.0.0.1:9200`（需要先构建前端，见下）

前端开发形态（热更新，代理到 9200）：

```powershell
cd D:\erp\web
npm install
npm run dev        # http://127.0.0.1:5175
```

前端生产形态（由 FastAPI 或容器托管）：

```powershell
cd D:\erp\web
npm run build      # 产出 web/dist
```

Postgres 形态与容器编排见 `docs/runbook.md`。

## 与 AI 能力层的对接契约

### 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/{object_type}` | 列表，支持 `cursor` / `limit` / `updated_since` |
| GET | `/api/v1/{object_type}/{id}` | 单条 |
| POST | `/api/v1/{object_type}` | 新建 |
| PATCH | `/api/v1/{object_type}/{id}` | 局部更新 |
| DELETE | `/api/v1/{object_type}/{id}` | 软删除 |

列表统一返回 `{"data": [...], "next_cursor": ..., "total": N}`，
单条与写操作统一返回 `{"data": {...}}`。

### 鉴权

AI 层用 `Authorization: Bearer <ERP_SERVICE_TOKEN>`，服务账号等同管理员，
并可用 `X-Actor-Id` / `X-Actor-Team-Ids` 声明真实操作者（只影响审计归因与写入归属）。
人工用户走 `POST /api/auth/login` 换自签令牌。

### 对象与字段

| 对象 | 业务字段 |
| --- | --- |
| `items` 物料 | sku, name, category, spec, unit, price, cost, safety_stock, is_active |
| `suppliers` 供应商 | name, contact, phone, email, region, payment_terms, grade, is_active |
| `customers` 客户 | name, contact, phone, email, region, credit_limit, payment_terms, grade, is_active |
| `warehouses` 仓库 | code, name, location, keeper, is_active |
| `purchase_orders` 采购订单 | code, supplier_id, warehouse_id, order_date, expected_date, status, currency, amount, note |
| `purchase_order_lines` 采购订单行 | order_id, item_id, quantity, unit_price, received_quantity, amount |
| `sales_orders` 销售订单 | code, customer_id, warehouse_id, order_date, delivery_date, status, currency, amount, note |
| `sales_order_lines` 销售订单行 | order_id, item_id, quantity, unit_price, shipped_quantity, amount |
| `stock_moves` 库存流水 | item_id, warehouse_id, kind, quantity, occurred_at, reference, note |
| `invoices` 发票 | code, direction, partner_id, order_id, amount, tax_amount, issued_at, due_at, status, note |
| `users` 员工 | name, email, role, is_active |

每条记录另有公共列：`id`、`version`、`updated_at`、`owner_id`、`team_ids`。

约定：

- 字段名就是契约，不要在 ERP 侧改名；改了 AI 层会把值收进 `_extra`。
- 未声明的字段不会被丢弃，会原样透传（AI 侧收进 `_extra`）。
- 内部列 `tenant_id` / `team_id` / `created_by` / `deleted_at` 不出现在出参里，
  归属只通过 `team_ids` 数组暴露。
- 写入时 `team_ids` 与 `team_id` 都接受，方便「读到什么就写回什么」。

### 写幂等与冲突

- 写接口接受 `Idempotency-Key`：同 key 同请求体直接回放首次响应，不再写库、不重复记审计；
  同 key 不同请求体返回 409。
- `PATCH` / `DELETE` 接受可选 `version`，与当前版本不符返回 409（乐观锁）。
- 可重试状态码沿用 AI 层约定：408 / 425 / 429 / 5xx 时安全重试。

### 状态码

`400` 入参非法（缺必填、枚举越界、类型不符）、`401` 凭证缺失或失效、
`403` 记录可见但无写权限、`404` 记录不存在或不可见（两者不区分，避免探测）、
`409` 版本冲突或幂等键复用。

## 权限模型

| 角色 | 可见 | 可写 |
| --- | --- | --- |
| `admin` / 服务账号 | 全部 | 全部 |
| `manager` | 本部门 | 本部门 |
| `staff` | 本人 + 本部门 | 仅本人 |

团队与用户由管理员在界面维护；记录单团队归属。
可见但无写权限返回 403，不可见返回 404。

## 审计

每次写操作（人工与 AI）都落一条审计：时间、来源（`human` / `ai`）、操作者、
对象与记录 ID、方法、请求路径、修改前后的值、幂等键。
审计只有管理员能查，界面在「审计」页。

## 测试

```powershell
cd D:\erp
python -X utf8 -m unittest discover -s tests -t .
```

103 条用例，覆盖契约字段形状、游标分页、`updated_since`、
写幂等回放与冲突、版本冲突、软删除、三角色行级权限、
鉴权与令牌失效、写审计与种子数据完整性。
测试使用临时 sqlite 库，不依赖 Postgres 或任何外部服务。

## 演示账号

首次启动（`ERP_SEED_DEMO=true`）会写入三个演示用户，密码统一 `sales12345`：

| 账号 | 姓名 | 角色 | 部门 |
| --- | --- | --- | --- |
| `chenxiao@example.com` | 陈晓 | manager | 采购部 `t-purchase` |
| `zhoumin@example.com` | 周敏 | staff | 销售部 `t-sales` |
| `lina@example.com` | 李娜 | manager | 财务部 `t-finance` |

管理员账号来自 `ERP_BOOTSTRAP_ADMIN_EMAIL` / `ERP_BOOTSTRAP_ADMIN_PASSWORD`，
默认 `admin@example.com` / `admin12345`（只在 users 表为空时创建）。

## 配置

全部配置以 `ERP_` 为前缀，见 `.env.example`。常用项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ERP_STORAGE` | `sqlite` | `sqlite` 或 `postgres` |
| `ERP_ENV` | `dev` | `dev` / `local` / `test` / `stage` / `staging` / `prod` / `production` |
| `ERP_SQLITE_PATH` | `data/erp.sqlite3` | sqlite 文件位置 |
| `ERP_DATABASE_URL` | — | postgres 连接串 |
| `ERP_SERVICE_TOKEN` | `dev-service-token` | AI 层用的服务令牌 |
| `ERP_SECRET_KEY` | `dev-only-change-me` | 登录令牌签名密钥 |
| `ERP_SERVE_WEB` | `true` | 是否托管 `web/dist` |
| `ERP_SEED_DEMO` | `true` | 是否写入演示数据 |

`ERP_ENV` 落在 `stage` / `staging` / `prod` / `production` 上时会启用生产保护：启动阶段
校验配置，默认密钥、默认管理员密码、`ERP_SEED_DEMO=true`、`ERP_STORAGE=sqlite`、
`ERP_CORS_ORIGINS` 含 `*` 都会让进程直接起不来（宁可起不来，也不要带着默认密钥对外服务）。
要求与开关清单见 `docs/go-live-checklist.md`，用例在 `tests/test_prod_guard.py`。

## 未验证项

本机只验证了 sqlite 形态、unittest 套件与前端类型检查/构建。
Postgres 适配、`docker compose` 编排、容器镜像构建均**未实测**，
相关内容见 `docs/runbook.md` 第 8 节；上线前要补什么见 `docs/go-live-checklist.md`。
