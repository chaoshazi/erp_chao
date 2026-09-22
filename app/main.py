'''FastAPI 入口：uvicorn app.main:app。

同一个进程既提供 API 也托管 ERP 前端构建产物（web/dist）：
跑一次 cd web; npm run build 之后，直接访问 http://127.0.0.1:9200 就是完整界面；
没构建过时自动退化成纯 API 服务（AI 能力层的对接不受影响）。
'''

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import api_router, auth_router, health_router
from app.container import Container
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.errors import ErpError

logger = logging.getLogger(__name__)

# 这些前缀属于接口，不能被前端 catch-all 兜住
RESERVED_PATHS = ('api', 'health', 'docs', 'openapi.json', 'redoc')


def _is_reserved(full_path: str) -> bool:
    return any(
        full_path == prefix or full_path.startswith(prefix + '/') for prefix in RESERVED_PATHS
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        setup_logging(resolved.log_level)
        container = await Container.build(resolved)
        application.state.container = container
        try:
            yield
        finally:
            container.close()

    application = FastAPI(
        title='ERP 管理系统',
        version=__version__,
        description='自研销售 ERP：业务管理界面 + 供 AI 能力层使用的同步与写回接口。',
        lifespan=lifespan,
    )

    @application.exception_handler(ErpError)
    async def _erp_error(request: Request, exc: ErpError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error('业务异常 %s: %s', type(exc).__name__, exc)
        return JSONResponse(status_code=exc.status_code, content={'detail': str(exc)})

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(api_router)
    if resolved.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.cors_origin_list,
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'],
        )
    _mount_web(application, resolved)
    return application


def _mount_web(application: FastAPI, settings: Settings) -> None:
    '''托管前端构建产物；目录不存在就跳过，保证纯后端也能启动。'''
    if not settings.serve_web:
        logger.info('ERP_SERVE_WEB=false，跳过前端静态托管')
        return
    dist = Path(settings.web_dist_dir)
    if not dist.is_absolute():
        dist = Path(__file__).resolve().parent.parent / dist
    index_file = dist / 'index.html'
    if not index_file.is_file():
        logger.info('未找到前端构建产物 %s，仅提供 API', index_file)
        return
    assets = dist / 'assets'
    if assets.is_dir():
        application.mount('/assets', StaticFiles(directory=assets), name='assets')

    @application.get('/', include_in_schema=False)
    async def web_index() -> FileResponse:
        return FileResponse(index_file)

    @application.get('/{full_path:path}', include_in_schema=False)
    async def web_spa(full_path: str) -> FileResponse:
        if _is_reserved(full_path):
            raise HTTPException(status.HTTP_404_NOT_FOUND, '接口不存在')
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index_file)

    logger.info('前端静态托管已挂载：%s', dist)


app = create_app()