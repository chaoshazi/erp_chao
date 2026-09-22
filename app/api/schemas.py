'''HTTP 入参出参模型。

对象记录本身是动态字段（见 app/contract.py），因此记录相关接口直接用 dict 传递，
只给固定的管理与认证接口定义模型。
'''

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=200, description='登录邮箱')
    password: str = Field(min_length=1, max_length=200, description='登录密码')


class LoginResponse(BaseModel):
    token: str
    expires_at: int
    user: dict[str, Any]


class PasswordChangeRequest(BaseModel):
    password: str = Field(min_length=6, max_length=200, description='新密码，至少 6 位')


class TeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamOut(BaseModel):
    id: str
    name: str
    version: str = '1'
    member_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class HealthResponse(BaseModel):
    status: str = 'ok'
    version: str
    env: str
    tenant_id: str
    storage: str
    serve_web: bool
    object_types: list[str]