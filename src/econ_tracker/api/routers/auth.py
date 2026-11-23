"""Authentication routes: register, login, current user profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.api.deps import AppContainer, get_container, get_current_user, get_session
from econ_tracker.api.errors import COMMON_ERROR_RESPONSES
from econ_tracker.services.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from econ_tracker.storage.orm_models import UserORM

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"], responses=COMMON_ERROR_RESPONSES)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await container.auth_service.register(
        session,
        username=payload.username,
        password=payload.password,
    )
    token = container.auth_service.create_access_token(user)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    container: AppContainer = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user, token = await container.auth_service.authenticate(
        session,
        username=payload.username,
        password=payload.password,
    )
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def me(user: UserORM = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
