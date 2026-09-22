'''运行时配置：全部来自环境变量或 .env，统一前缀 ERP_。'''

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

STORAGE_CHOICES = ('sqlite', 'postgres')

# ---- 生产环境保护 ----
# env 落在 PRODUCTION_ENVS 上时，出厂默认值与演示开关一律拒绝启动。
KNOWN_ENVS = ('dev', 'local', 'test', 'stage', 'staging', 'prod', 'production')
PRODUCTION_ENVS = ('stage', 'staging', 'prod', 'production')

# 必须替换掉的出厂值；docker-compose.yml 里的 change-me-in-production 同样算默认值
PLACEHOLDER_VALUES = frozenset(
    {
        'dev-only-change-me',
        'dev-service-token',
        'change-me-in-production',
        'change-me',
        'changeme',
        'replace-me',
        'admin12345',
    }
)

MIN_SECRET_KEY_LENGTH = 16
MIN_SERVICE_TOKEN_LENGTH = 16
MIN_ADMIN_PASSWORD_LENGTH = 12


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in (value or '').split(',') if part.strip()]


def _check_secret(
    problems: list[str], name: str, value: str, min_length: int, purpose: str
) -> None:
    '''空值、出厂默认值与过短的密钥都记进 problems，由调用方统一报错。'''
    stripped = (value or '').strip()
    if not stripped:
        problems.append(f'{name} 不能为空：{purpose}')
    elif stripped.lower() in PLACEHOLDER_VALUES:
        problems.append(f'{name} 还是出厂默认值 {stripped}，必须换成随机串：{purpose}')
    elif len(stripped) < min_length:
        problems.append(f'{name} 太短（至少 {min_length} 位）：{purpose}')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_prefix='ERP_', extra='ignore')

    # ---- 应用 ----
    env: str = 'dev'
    log_level: str = 'INFO'
    tenant_id: str = 'default'

    # ---- 存储 ----
    storage: str = 'sqlite'
    sqlite_path: str = 'data/erp.sqlite3'
    database_url: str = 'postgresql+psycopg://erp:erp@localhost:5434/erp'
    auto_migrate: bool = True

    # ---- 安全 ----
    secret_key: str = 'dev-only-change-me'
    token_ttl_hours: int = 12
    service_token: str = 'dev-service-token'
    service_actor_id: str = 'ai-agent'

    # ---- 初始化数据 ----
    seed_demo: bool = True
    bootstrap_admin_email: str = 'admin@example.com'
    bootstrap_admin_password: str = 'admin12345'
    bootstrap_admin_name: str = '系统管理员'

    # ---- 前端 ----
    serve_web: bool = True
    web_dist_dir: str = 'web/dist'
    cors_origins: str = 'http://localhost:5175,http://127.0.0.1:5175'

    # ---- 分页 ----
    default_page_size: int = 50
    max_page_size: int = 200

    # ---- 生产保护 ----
    # 只在生产环境（见 PRODUCTION_ENVS）生效：sqlite 是单文件存储，默认拒绝启动，
    # 确认要让生产库落在单文件上才显式打开。
    allow_ephemeral_storage: bool = False

    @field_validator('env')
    @classmethod
    def _validate_env(cls, value: str) -> str:
        '''env 只认已知取值：拼错（prd 之类）会静默关掉生产保护，所以直接拒绝。'''
        resolved = (value or '').strip().lower()
        if resolved not in KNOWN_ENVS:
            raise ValueError(f'env 必须是 {KNOWN_ENVS} 之一，收到 {value}')
        return resolved

    @model_validator(mode='after')
    def _guard_production(self) -> Settings:
        '''生产环境拒绝出厂默认值：宁可起不来，也不要带着默认密钥对外服务。'''
        if self.env not in PRODUCTION_ENVS:
            return self
        problems: list[str] = []
        _check_secret(
            problems,
            'ERP_SECRET_KEY',
            self.secret_key,
            MIN_SECRET_KEY_LENGTH,
            '人工登录令牌的 HMAC 密钥，泄露即可伪造任意用户身份',
        )
        _check_secret(
            problems,
            'ERP_SERVICE_TOKEN',
            self.service_token,
            MIN_SERVICE_TOKEN_LENGTH,
            'AI 能力层（D:/codex）的 AICRM_ERP_API_TOKEN 必须与它一致',
        )
        _check_secret(
            problems,
            'ERP_BOOTSTRAP_ADMIN_PASSWORD',
            self.bootstrap_admin_password,
            MIN_ADMIN_PASSWORD_LENGTH,
            'users 表为空时会拿它建管理员，必须换掉',
        )
        if self.seed_demo:
            problems.append('ERP_SEED_DEMO 仍为 true，生产环境不写入演示数据')
        if self.storage == 'sqlite' and not self.allow_ephemeral_storage:
            problems.append(
                'ERP_STORAGE=sqlite 是单文件存储，生产请用 postgres；'
                '确实要在生产跑单文件就显式设置 ERP_ALLOW_EPHEMERAL_STORAGE=true'
            )
        if '*' in self.cors_origin_list:
            problems.append('ERP_CORS_ORIGINS 不能出现 *，要逐个列出来源域名')
        if problems:
            raise ValueError(
                f'env={self.env} 属于生产环境，以下 {len(problems)} 项不安全：\n  - '
                + '\n  - '.join(problems)
                + '\n要么改掉这些配置，要么把 ERP_ENV 调回 dev（开发与演示形态）。'
            )
        return self

    @field_validator('storage')
    @classmethod
    def _validate_storage(cls, value: str) -> str:
        resolved = (value or '').strip().lower()
        if resolved not in STORAGE_CHOICES:
            raise ValueError(f'storage 必须是 {STORAGE_CHOICES} 之一，收到 {value}')
        return resolved

    @property
    def database_uri(self) -> str:
        '''sqlite 走本地文件（零依赖），postgres 用配置里的连接串。'''
        if self.storage == 'sqlite':
            return f'sqlite+pysqlite:///{self.sqlite_file}'
        return self.database_url

    @property
    def sqlite_file(self) -> str:
        return str(self.sqlite_path).replace('\\', '/')

    @property
    def cors_origin_list(self) -> list[str]:
        return sorted(_split_csv(self.cors_origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()
