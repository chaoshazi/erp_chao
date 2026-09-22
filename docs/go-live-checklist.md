# 上线检查表（AI 能力层 + 自研 ERP）

面向「把这套系统部署到客户能访问的环境」。三个仓库的分工、端口与启动顺序见同目录的
runbook.md，这里只回答一个问题：**还差什么才能上线，怎么改，怎么验证。**

结论按代码现状给，不按期望给。等级：P0 = 拦上线；P1 = 上线前建议清掉；P2 = 可以放到上线后。

## 1. 一句话结论

- 现在可以交付**内部试用 / 演示**，还不能交付**生产上线**。
- 上线前必须做掉三件事：清空 §3 剩下的 P0、把 §6 的环境备齐、按 §7 走一遍。
- §9 是「代码里有、但本机没跑过」的部分。交付时要把 §9 一起给对方，不要让它看起来
  像已验证 —— 这是本次交付里唯一靠信用兜底的地方。

## 2. 本轮新增的生产保护（2026-09-22，已实测）

两个仓库各自在 `app/core/config.py` 的 `Settings` 上加了同一个守卫
`_guard_production`，行为一致：

- `env` 只认白名单：`dev` / `local` / `test` / `stage` / `staging` / `prod` / `production`。
  写成 `prd` 之类的值会直接报错 —— 拼错就等于把保护静默关掉，所以不给默认放行。
- `env` 落在 `stage` / `staging` / `prod` / `production` 上时，**启动阶段**就把配置校验
  一遍，不合格直接起不来（pydantic `ValidationError`，日志里带逐条清单）。

### 2.1 生产环境里没有开关、必须改掉的项

| 侧 | 配置项 | 要求 |
| --- | --- | --- |
| ERP | `ERP_SECRET_KEY` | 至少 16 位随机串。人工登录令牌的 HMAC 密钥，泄露即可伪造任意用户身份 |
| ERP | `ERP_SERVICE_TOKEN` | 至少 16 位随机串。必须与 AI 层的 `AICRM_ERP_API_TOKEN` 逐字一致 |
| ERP | `ERP_BOOTSTRAP_ADMIN_PASSWORD` | 至少 12 位。`users` 表为空时拿它建管理员 |
| ERP | `ERP_SEED_DEMO` | 必须 `false` |
| ERP | `ERP_CORS_ORIGINS` | 不能出现 `*` |
| AI 层 | `AICRM_API_TOKEN` | 至少 16 位随机串。留空等于 `/api/v1` 对全网开放 |
| AI 层 | `AICRM_DEFAULT_USER_ADMIN` | 必须 `false`。`true` 时「不带任何身份头」的请求就是管理员 |
| AI 层 | `AICRM_DEFAULT_USER_ID` | 不能是 `dev-user` |
| AI 层 | `AICRM_DEMO_SEED` | 必须 `false` |
| AI 层 | `AICRM_<源>_MODE` | 必须 `rest`。`fake` 是内存假数据，会答出与业务系统无关的内容 |
| AI 层 | `AICRM_<源>_AUTH_MODE` | 必须 `bearer` 或 `signature`。`none` 表示不带凭证调用业务系统 |
| AI 层 | `AICRM_LLM_MODE` | 必须 `live`，且 `AICRM_LLM_API_KEY` 是真实密钥 |
| AI 层 | `AICRM_EMBEDDING_PROVIDER` | 必须 `http`。`hash` 是离线占位向量，没有语义能力 |
| AI 层 | `AICRM_CORS_ORIGINS` | 不能出现 `*` |

`<源>` = `CRM` 或 `ERP`，看 `AICRM_SOURCE` 当前指向谁。

### 2.2 只留了两个显式开关

「明知有风险、但确实要这么跑」的两件事做成了显式开关，默认都是 `false`：

| 开关 | 放行什么 | 代价 |
| --- | --- | --- |
| `ERP_ALLOW_EPHEMERAL_STORAGE=true` | 生产用 sqlite 单文件存储 | 并发写与备份恢复都受限 |
| `AICRM_ALLOW_EPHEMERAL_STORAGE=true` | 生产用 memory 存储 | 重启即清空：会话、索引、写回记录全丢 |
| `AICRM_ALLOW_AUTO_APPLY_IN_PROD=true` | 生产让模型不经审批直接写业务系统 | 写错没有人工兜底 |

密钥与身份类的项**没有开关**，只能改值 —— 这是刻意的。

### 2.3 怎么自测这套保护

```powershell
# 两侧各自的守卫用例（不依赖外部服务，秒级）
cd D:\erp;   python -X utf8 -m unittest tests.test_prod_guard -v
cd D:\codex; python -X utf8 -m unittest tests.test_config_guard -v

# 手工确认「真的起不来」：只改 env，不改别的
cd D:\erp;   $env:ERP_ENV='prod';   python -X utf8 -c "from app.main import create_app; create_app()"
cd D:\codex; $env:AICRM_ENV='prod'; python -X utf8 -c "from app.main import create_app; create_app()"
```

期望：进程直接退出，日志里是 `env=prod 属于生产环境，以下 N 项不安全：` 加逐条清单，
最后一行是「要么改掉这些配置，要么把 ENV 调回 dev」。实测 ERP 报 5 项、AI 层报 5 项
（AI 层读的是本机 `.env`，其中数据源、模型、向量几项已经合规，所以只报剩下的 5 项）。

## 3. P0：上线前必须清空

| 编号 | 事项 | 状态 |
| --- | --- | --- |
| P0-1 | AI 层完全无鉴权（`/api/v1/records/users`、`/api/v1/sessions` 匿名可读，且默认管理员） | **已加启动校验**，值待填 |
| P0-2 | ERP 全用出厂密钥（`dev-only-change-me` / `dev-service-token` / `admin12345`） | **已加启动校验 + compose 强制**，值待填 |
| P0-3 | 两侧都没有「生产环境拒绝默认值」校验 | **已完成**（§2） |
| P0-4 | 明文暴露过的密钥必须轮换 | **只能由你来做，未完成** |
| P0-5 | 写回策略（自动写回 / 灰度 / 人工审批）没有业务拍板 | **保护已就位**，待拍板 |
| P0-6 | 存储还是 memory（重启全丢），Postgres 形态从未实测 | **保护已就位**，形态待实测 |
| P0-7 | AI 层怎么对外没定（反代、TLS、身份注入） | **未做** |
| P0-8 | 没有备份与恢复方案 | **未做** |

### P0-1 / P0-2 填生产值

按 §2.1 的表改 `D:\erp\.env` 与 `D:\codex\.env`。生成随机串：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

注意 `ERP_SERVICE_TOKEN` 与 `AICRM_ERP_API_TOKEN` 必须是同一个值，改一边就要改另一边，
否则 AI 层同步会 401。

### P0-4 轮换已暴露的密钥

对话里明文出现过两个令牌：DeepSeek 的 API key 与一个 GitHub PAT。**这两个都必须在后台
重置**，重置后同步改 `D:\codex\.env` 的 `AICRM_LLM_API_KEY`，并重新验证一次真实问答。
（GitHub PAT 如果只用过一次推送、且已废弃，可以直接删掉不重建。）

### P0-5 写回策略拍板

现状是 `AICRM_ACTION_AUTO_APPLY=true` + `AICRM_ACTION_DRY_RUN=false`：`update_field`、
`append_note`、`create_task` 这三类动作由模型直接落到业务系统，不经过人。高风险动作
（`advance_stage`、`close_won`、`transfer_owner`、`delete_record`）本来就要人工审批。
生产环境现在必须二选一：

- 灰度：`AICRM_ACTION_DRY_RUN=true`（只记录不执行）或 `AICRM_ACTION_AUTO_APPLY=false`；
- 或者明确接受自动写回：`AICRM_ALLOW_AUTO_APPLY_IN_PROD=true`。

这项要业务方点头，不是技术选择。

### P0-6 Postgres 形态实测

`storage=postgres` 在两个仓库都存在，但本机没跑过（无 docker、无实例、无 `psycopg` 实测）。
AI 层尤其要注意：**它的 Postgres 适配器不会自动建表**，表结构在 `D:\codex\sql\001_init.sql`
（含 `CREATE EXTENSION vector`，需要 pgvector 镜像或已装扩展的实例），必须先应用这个脚本。
ERP 那边 `ensure_schema()` 会 `CREATE TABLE IF NOT EXISTS`，但**不会补列**（见 P1-1）。

验证顺序：应用建表脚本 → `storage=postgres` 起服务 → `/health` 里 `storage=postgres` →
跑一次 `POST /api/v1/sync/all` → **重启一次进程**，重问同一个问题。memory 形态这一步必
失败（索引空了），postgres 形态必须还能答出带引用的答案。

### P0-7 部署形态

AI 层默认是「谁都能匿名调」的开发形态，生产要么把 `AICRM_API_TOKEN` 配上并在调用方带
`Authorization: Bearer <token>`，要么在网关侧注入 `X-User-Id` / `X-Team-Ids` /
`X-User-Admin` 并用 token 挡住直连。前端 `web/dist` 由后端 `AICRM_SERVE_WEB=true` 托管，
前提是先 `npm run build`。对外要加 TLS 反代（8000 / 9200 不要直接暴露在公网）。

### P0-8 备份与恢复

至少做到：Postgres 定时 `pg_dump` + 保留策略，并且**演练恢复一次**。业务数据在 ERP 侧，
AI 侧的会话与写回审计也建议一并备份。没有演练过的备份等于没有备份。

## 4. P1：上线前建议清掉

| 编号 | 事项 | 现状 |
| --- | --- | --- |
| P1-1 | ERP 没有加列迁移机制 | `app/adapters/sql.py` 的 `ensure_schema()` 只调 `create_all()`，等于 `CREATE TABLE IF NOT EXISTS`，**不会 `ALTER TABLE`**。加字段上不了线，要人工 SQL 或引入迁移工具 |
| P1-2 | AI 层没有 Dockerfile，compose 里也没有 API 服务 | `docker-compose.yml` 只有 postgres + redis；ERP 那边有可用的 Dockerfile |
| P1-3 | redis 依赖是死的 | `redis>=5.0` 与 compose 里的 redis 服务**没有任何代码引用**（只有 `AICRM_REDIS_URL` 一个配置项）。要么用起来，要么删掉，别让对方多运维一个中间件 |
| P1-4 | `alembic` 同样无引用 | 在 requirements 里，但全仓没有迁移脚本 |
| P1-5 | 依赖清单与实现不符 | 项目实际用标准库 `unittest`，requirements 里列了 `pytest` / `pytest-asyncio` |
| P1-6 | 没有 CI | 仓库里没有 `.github/`，224 + 103 条用例只能靠人记得跑 |
| P1-7 | 无 trace id 串联 | 只有 stdout JSON 日志，AI 层到 ERP 的调用链无法串起来 |
| P1-8 | 无速率限制与成本上限 | 模型侧按量计费，没有配额与限流 |
| P1-9 | 前端零测试 | ERP 与 AI 控制台都只有 `tsc --noEmit` + `vite build` |

## 5. P2：可以放到上线后

- **聚合类问题答不了**：检索是按块召回的，做不了求和。实测「未结应收应付」与
  「低库存有哪些」都答不出来，而 `GET /stats/overview` 里有现成的
  `receivable_open` / `payable_open` / `low_stock_count`。修法是加一个只读 `stats`
  工具直读该接口 —— 建议在验收前跟使用方对齐预期，别被当成 bug。
- 多租户是「单租户一进程」，横向扩展要按租户分进程。
- 没有 metrics / tracing。

## 6. 上线环境清单

| 依赖 | 用途 | 备注 |
| --- | --- | --- |
| Python 3.11+ | 两个后端 | 本机实测 3.11.9 |
| Node 18+ | 两个前端构建 | 本机实测 v22.20.0 |
| Postgres 16 + **pgvector** | AI 层存储与向量检索 | 必须能 `CREATE EXTENSION vector` |
| Postgres 16 | ERP 存储（多用户必须） | 单机也可用 `ERP_ALLOW_EPHEMERAL_STORAGE=true` 跑 sqlite |
| OpenAI 兼容向量服务 | 1024 维向量 | 本机用 Ollama `mxbai-embed-large`；生产可用同款或云服务 |
| DeepSeek API key | 问答与技能 | `deepseek-chat`（`deepseek-reasoner` 不支持 function calling） |
| 反向代理 + 证书 | 对外 | 8000 / 9200 不要裸奔在公网 |

Redis 目前不是必需（见 P1-3）。

## 7. 上线步骤

1. 生成密钥，按 §2.1 写两侧 `.env`（`ERP_ENV` / `AICRM_ENV` 都设成 `prod`）。
2. 建库：AI 层应用 `D:\codex\sql\001_init.sql`；ERP 起一次服务让它建表。
3. 起 ERP：`cd D:\erp; python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 9200`。
   期望：不再出现 §2.3 的生产校验失败；`GET /health` 返回 `storage=postgres`、`env=prod`。
4. 起 AI 层：`cd D:\codex; python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`。
   期望：`GET /health` 里 `source_mode=rest`、`embedding_ok=true`、`llm_mode=live`。
5. 建前端：两个仓库各 `cd web; npm run build`。
6. 首次同步：`POST /api/v1/sync/all`，期望对象数与失败数为 `failed=0`。
7. 冒烟：跑 `acceptance-cases.md` 里的 A / D / F 三组用例。
8. 交出去之前再跑一次两侧全量用例：ERP 103 条、AI 层 237 条。

## 8. 回滚

- 应用层：两个仓库都是「起一个 uvicorn」的形态，回滚 = 换回上一个代码版本重启。
- 数据层：Postgres 用 `pg_dump` 的备份恢复；`ensure_schema()` 不会删表也不会改列，
  所以回滚代码不会连带弄坏数据。
- 配置层：`.env` 改错导致起不来时，把 `ENV` 调回 `dev` 就能绕过生产校验启动 ——
  **这条只用于抢修，绕过去等于 §2.1 的项全部失效，别忘了改回来。**

## 9. 仍未验证的部分

以下几项只交付代码与命令，**本机没有跑过**，不要当成已验证：

- Postgres 形态的 ERP 与 AI 层（本机无 docker、无 Postgres 实例）。
- `docker compose` 的镜像构建与容器编排（本机没有 docker 命令）。
- 上表里的 redis（代码没用到）与 alembic（仓库里没有迁移脚本）。
- 公网部署形态：TLS、反向代理、身份注入、限流。

已在 2026-09-22 实测过：ERP sqlite 形态 103 条 unittest、AI 层 237 条 unittest、
两侧前端 `tsc --noEmit` + `vite build`、Ollama `http` 向量（1024 维）、AI 层对 ERP 9200
的全量同步与真实问答、写回 `append_note` 与 ERP 审计留痕、日志见 runbook.md §8。
