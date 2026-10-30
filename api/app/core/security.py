from datetime import datetime, timedelta, timezone
import jwt
from jwt.exceptions import InvalidTokenError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from app.core.config import settings

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=60)},
        settings.jwt_secret,
        algorithm=_ALGORITHM,
    )


def decode_access_token(token: str) -> int | None:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]})
        if not str(claims["sub"]).isdigit():
            return None
        return int(claims["sub"])
    except (InvalidTokenError, ValueError):
        return None
