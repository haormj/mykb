"""Account registration, login and session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...auth.service import AccountError, authenticate, register_account
from ...auth.tokens import TokenService
from ...db.models import User
from ..deps import AuthUser, get_current_user, get_session, get_token_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str
    password: str
    email: str | None = None
    display_name: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
    }


def _request_meta(request: Request) -> tuple[str | None, str | None]:
    agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return agent, ip


@router.post("/register")
def register(
    payload: RegisterIn,
    request: Request,
    session: Session = Depends(get_session),
    tokens: TokenService = Depends(get_token_service),
) -> dict:
    try:
        user = register_account(
            session,
            username=payload.username,
            password=payload.password,
            email=payload.email,
            display_name=payload.display_name,
        )
    except AccountError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    agent, ip = _request_meta(request)
    token = tokens.create(session, user.id, user_agent=agent, ip_address=ip)
    session.commit()
    return {"token": token, "user": _user_payload(user)}


@router.post("/login")
def login(
    payload: LoginIn,
    request: Request,
    session: Session = Depends(get_session),
    tokens: TokenService = Depends(get_token_service),
) -> dict:
    user = authenticate(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    agent, ip = _request_meta(request)
    token = tokens.create(session, user.id, user_agent=agent, ip_address=ip)
    session.commit()
    return {"token": token, "user": _user_payload(user)}


@router.post("/logout")
def logout(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    session: Session = Depends(get_session),
    tokens: TokenService = Depends(get_token_service),
) -> dict:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        tokens.revoke(session, header[len("Bearer ") :].strip())
        session.commit()
    return {"ok": True}


@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "roles": user.roles,
        "permissions": user.permissions,
    }
