from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from .config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(account_id: int, role: str = "student") -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(account_id), "role": role, "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


def read_student_id(token: str) -> int | None:
    try:
        return int(jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None


def read_identity(token: str) -> tuple[str, int] | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        role = payload.get("role", "student")
        account_id = int(payload["sub"])
        if role not in {"student", "teacher", "admin"}:
            return None
        return role, account_id
    except (JWTError, KeyError, TypeError, ValueError):
        return None
