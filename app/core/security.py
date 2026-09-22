'''密码摘要与自签令牌：只用标准库，不引入 passlib 或 PyJWT。

密码：pbkdf2_hmac(sha256, 迭代次数, 每用户随机盐)，存储格式 pbkdf2_sha256$迭代$盐$摘要。
令牌：base64url(JSON).base64url(HMAC-SHA256)，载荷含 sub 与 exp，服务端无状态校验。
'''

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

PBKDF2_ITERATIONS = 240_000
PREFIX = 'pbkdf2_sha256'


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError('密码不能为空')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f'{PREFIX}${iterations}${_b64e(salt)}${_b64e(digest)}'


def verify_password(password: str, stored: str) -> bool:
    '''校验密码；摘要格式非法一律当作不匹配，不抛异常。'''
    try:
        prefix, raw_iterations, raw_salt, raw_digest = str(stored).split('$')
        iterations = int(raw_iterations)
        salt = _b64d(raw_salt)
        expected = _b64d(raw_digest)
    except (AttributeError, ValueError):
        return False
    if prefix != PREFIX or iterations <= 0:
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return hmac.compare_digest(digest, expected)


def issue_token(
    *, subject: str, secret: str, ttl_seconds: int, extra: dict[str, Any] | None = None
) -> tuple[str, int]:
    '''签发令牌，返回 (token, 过期时间戳)。'''
    expires_at = int(time.time()) + max(1, int(ttl_seconds))
    payload: dict[str, Any] = {'sub': str(subject), 'exp': expires_at}
    if extra:
        payload.update(extra)
    body = _b64e(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    signature = hmac.new(secret.encode('utf-8'), body.encode('ascii'), hashlib.sha256).digest()
    return f'{body}.{_b64e(signature)}', expires_at


def read_token(token: str, secret: str, *, now: int | None = None) -> dict[str, Any] | None:
    '''校验令牌，过期或签名不符返回 None。'''
    if not token or '.' not in token:
        return None
    body, _, raw_signature = token.partition('.')
    expected = hmac.new(secret.encode('utf-8'), body.encode('ascii'), hashlib.sha256).digest()
    try:
        signature = _b64d(raw_signature)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64d(body).decode('utf-8'))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    expires_at = payload.get('exp')
    if not isinstance(expires_at, int) or expires_at <= (now if now is not None else int(time.time())):
        return None
    return payload