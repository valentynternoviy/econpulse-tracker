"""Authentication & JWT token management service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.config import Settings
from econ_tracker.domain.enums import UserRole
from econ_tracker.domain.exceptions import AuthenticationError, ConflictError
from econ_tracker.storage.orm_models import UserORM


class AuthService:
    """Handle user registration, credential verification, and JWT tokens."""

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.secret_key.get_secret_value()
        self._algorithm = settings.jwt_algorithm
        self._expire_minutes = settings.jwt_expire_minutes

    @staticmethod
    def hash_password(plain: str) -> str:
        return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False

    def create_access_token(self, user: UserORM) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(minutes=self._expire_minutes),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            decoded: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
            )
            return decoded
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired access token") from exc

    async def register(
        self,
        session: AsyncSession,
        *,
        username: str,
        password: str,
        role: UserRole = UserRole.USER,
    ) -> UserORM:
        existing = await session.scalar(select(UserORM).where(UserORM.username == username))
        if existing is not None:
            raise ConflictError(f"Username '{username}' is already taken")
        user = UserORM(
            username=username,
            password_hash=self.hash_password(password),
            role=role.value,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def authenticate(
        self,
        session: AsyncSession,
        *,
        username: str,
        password: str,
    ) -> tuple[UserORM, str]:
        user = await session.scalar(select(UserORM).where(UserORM.username == username))
        if user is None or not self.verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username or password")
        token = self.create_access_token(user)
        return user, token

    async def get_user_by_id(self, session: AsyncSession, user_id: int) -> UserORM:
        user = await session.get(UserORM, user_id)
        if user is None:
            raise AuthenticationError("Authenticated user no longer exists")
        return user
