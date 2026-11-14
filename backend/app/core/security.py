from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.core.config import Settings
from app.repositories.users import User

passwords = PasswordHash.recommended()


def set_session_cookie(response: Response, user: User, config: Settings):
    now = datetime.now(timezone.utc)
    seconds = user.settings.session_lifetime_hours * 3600
    token = jwt.encode(
        {
            "sub": user.id,
            "ver": user.auth_version,
            "iat": now,
            "exp": now + timedelta(seconds=seconds),
            "iss": config.jwt_issuer,
            "jti": str(uuid4()),
        },
        config.jwt_secret,
        algorithm="HS256",
    )
    response.set_cookie(
        config.cookie_name,
        token,
        max_age=seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/api/v1",
    )


def clear_session_cookie(response: Response, config: Settings):
    response.delete_cookie(
        config.cookie_name,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/api/v1",
    )
