# AGENTS.md

## Repository state

`D:\erp` 是独立的自研 ERP 管理系统（FastAPI + SQLAlchemy Core + Vite/React 前端），
同时是 AI 能力层 `D:\codex` 的数据底座。两个仓库各自独立启动，不互相内嵌。

- `app/` 后端：契约元数据、配置、存储适配器、用例、路由、种子数据
- `web/` 管理前端（构建产物由 FastAPI 或容器托管）
- `tests/` 标准库 unittest 测试集
- `docs/runbook.md` 全栈启动手册（含 AI 能力层与 Ollama）
- `docs/go-live-checklist.md` 上线检查表（P0/P1/P2、环境清单、上线步骤、回滚与未验证项）
- `docs/acceptance-cases.md` 人工验收用例清单（30 条，可勾选）

已经落地并有实测：sqlite 形态的完整 CRUD、行级权限、写审计、写幂等与版本冲突、
前端类型检查与构建、103 条 unittest。
**未实测**：Postgres 适配、docker 编排、容器镜像构建。

## Commands

```powershell
cd D:\erp
pip install -r requirements.txt

python -X utf8 -m unittest discover -s tests -t .          # 全量测试（sqlite 临时库，离线）
python -X utf8 -m compileall app tests                     # 语法检查
python -m uvicorn app.main:app --host 127.0.0.1 --port 9200 # 起后端（默认 sqlite）

cd D:\erp\web
npm install
npx tsc --noEmit                                          # 前端类型检查
npm run dev                                               # 开发服务器 5175，代理到 9200
npm run build                                             # 构建到 web/dist
```

容器形态（本机没有 docker，未验证）：

```powershell
cd D:\erp\web; npm run build
cd D:\erp; docker compose up -d --build
```

## Conventions

- 源码与文档不使用双引号：Python 用单引号与三单引号，前端用单引号；
  只有 JSON 文件与 HTTP 请求体必须用双引号。
- 注释与 docstring 用中文，标识符用英文。
- 文件一律 UTF-8（无 BOM）+ LF。
  例外：`scripts/*.ps1` 必须写成 UTF-8 **带 BOM**。
  Windows PowerShell 5.1 会把无 BOM 的脚本按 ANSI 解码，脚本里的中文会直接解析失败。
- 测试用标准库 unittest，不用 pytest；测试不依赖 Postgres 或外部服务。
- `env` 只认白名单：`dev` / `local` / `test` / `stage` / `staging` / `prod` / `production`。
  `ERP_ENV` 落在生产的那四个取值上时，启动阶段会先把配置校验一遍
  （`Settings._guard_production`）：`ERP_SECRET_KEY` / `ERP_SERVICE_TOKEN` /
  `ERP_BOOTSTRAP_ADMIN_PASSWORD` 是默认值或过短、`ERP_SEED_DEMO=true`、
  `ERP_STORAGE=sqlite`、`ERP_CORS_ORIGINS` 含 `*` 都会让进程起不来。
  `docker-compose.yml` 按生产形态写死了 `ERP_ENV=prod`，缺密钥时 compose 自己就报错。
- `app/contract.py` 是对象与字段元数据的唯一来源。
  **改字段名等于改与 AI 能力层的对接契约**，要和 `D:\codex` 的
  `D:\codex\app\integrations\erp\field_map.py` 同步改。
- 出参不得暴露内部列（`tenant_id` / `team_id` / `created_by` / `deleted_at`），
  归属只通过 `team_ids` 数组暴露；越权与不存在统一返回 404。
- 未被契约声明的字段必须原样透传，不能因为字段未知就丢数据。
- Windows PowerShell 5.1 传参会破坏同时含中文与双引号的参数。
  用 apply_patch 时直接调用 `codex.exe --codex-run-as-apply-patch`，
  不要走 `.bat` 包装器；含双引号的文件用 `[System.IO.File]::WriteAllText` 写。
- 跑 Python 脚本带 `-X utf8`，否则 Windows 默认 GBK 会把中文报成编码错误。

## Verification

- 改动后跑 `python -X utf8 -m unittest discover -s tests -t .`；
  改前端再跑 `cd web; npx tsc --noEmit && npm run build`。
- 本机没有 docker、Postgres 实例与 `psycopg`：
  `app/adapters/sql.py` 的 postgres 分支、`Dockerfile`、`docker-compose.yml`
  属于代码交付，**不要声称验证过**。
- 本机没有 ruff / mypy，不要声称跑过 lint 或类型检查。
- 对接回归可以用 AI 能力层的探测脚本（只读）：

  ```powershell
  cd D:\codex
  python -X utf8 scripts\erp_probe.py --base-url http://127.0.0.1:9200/api/v1 --token dev-service-token --auth-mode bearer --all --show-raw
  ```
