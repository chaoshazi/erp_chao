'''业务异常：由 API 层统一翻译成 HTTP 状态码。'''

from __future__ import annotations


class ErpError(RuntimeError):
    status_code = 400


class ValidationError(ErpError):
    '''入参非法：缺必填、类型不符、枚举越界。'''

    status_code = 400


class AuthError(ErpError):
    '''缺少凭证或凭证无效。'''

    status_code = 401


class Forbidden(ErpError):
    '''越权访问：行级权限或角色不允许。'''

    status_code = 403


class NotFound(ErpError):
    '''记录不存在或不可见（不区分两者，避免探测）。'''

    status_code = 404


class Conflict(ErpError):
    '''版本冲突或幂等键复用。'''

    status_code = 409