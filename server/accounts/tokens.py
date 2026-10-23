from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model

ALGORITHM = "HS256"


def _encode(user_id, kind, ttl):
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": kind, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def issue_tokens(user):
    return {
        "access": _encode(user.id, "access", timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES)),
        "refresh": _encode(user.id, "refresh", timedelta(days=settings.JWT_REFRESH_TTL_DAYS)),
    }


def user_from_token(token, kind="access"):
    """Return the active user for a valid token of the given kind, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != kind:
        return None
    return get_user_model().objects.filter(id=payload.get("sub"), is_active=True).first()
