from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyCookie
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    clear_session_cookie,
    passwords,
    set_session_cookie,
)
from app.repositories.users import User, UserRepository, UserSettings
from app.schemas.auth import AccountInput, LoginInput, PublicUser, RegisterInput, SettingsInput

router = APIRouter(tags=["account"])
cookie_auth = APIKeyCookie(name="fieldshift_access", auto_error=False)


def database_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


Database = Annotated[Session, Depends(database_session)]


def current_user(
    request: Request, database: Database, token: Annotated[str | None, Depends(cookie_auth)]
):
    try:
        claims = jwt.decode(
            token or "",
            request.app.state.config.jwt_secret,
            algorithms=["HS256"],
            issuer=request.app.state.config.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "ver", "jti"]},
        )
        user = UserRepository(database).by_id(claims["sub"])
        if user is None or claims["ver"] != user.auth_version:
            raise ValueError("Invalid session")
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError) as error:
        raise HTTPException(status_code=401, detail="Authentication required") from error


CurrentUser = Annotated[User, Depends(current_user)]


def commit_account(database: Session):
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from error


@router.post("/auth/register", response_model=PublicUser, status_code=201)
def register(payload: RegisterInput, request: Request, response: Response, database: Database):
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=passwords.hash(payload.password),
        settings=UserSettings(
            farm_name=payload.farm_name,
            location=payload.location,
            language=payload.language,
            latitude=payload.latitude,
            longitude=payload.longitude,
        ),
    )
    database.add(user)
    commit_account(database)
    set_session_cookie(response, user, request.app.state.config)
    return user


@router.post("/auth/login", response_model=PublicUser)
def login(payload: LoginInput, request: Request, response: Response, database: Database):
    user = UserRepository(database).by_email(payload.email)
    if user is None or not passwords.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    set_session_cookie(response, user, request.app.state.config)
    return user


@router.post("/auth/logout")
def logout(request: Request, response: Response, user: CurrentUser, database: Database):
    # Revoke all existing JWTs for this account, including copied cookies.
    database.execute(
        update(User).where(User.id == user.id).values(auth_version=User.auth_version + 1)
    )
    database.commit()
    clear_session_cookie(response, request.app.state.config)
    return {"message": "Logged out"}


@router.get("/auth/me", response_model=PublicUser)
def me(user: CurrentUser):
    return user


@router.put("/auth/me", response_model=PublicUser)
def update_account(payload: AccountInput, user: CurrentUser, database: Database):
    user.full_name = payload.full_name
    user.email = payload.email
    commit_account(database)
    return user


@router.get("/users/me/settings", response_model=SettingsInput)
def settings(user: CurrentUser):
    return user.settings


@router.put(
    "/users/me/settings",
    response_model=SettingsInput,
    description="Replace the signed-in user's preferences. Reissues the current session with the selected lifetime; other sessions retain their original expiry.",
)
def update_settings(
    payload: SettingsInput,
    request: Request,
    response: Response,
    user: CurrentUser,
    database: Database,
):
    for key, value in payload.model_dump().items():
        setattr(user.settings, key, value)
    database.commit()
    set_session_cookie(response, user, request.app.state.config)
    return user.settings
