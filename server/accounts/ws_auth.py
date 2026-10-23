from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from .tokens import user_from_token


class JWTQueryAuthMiddleware:
    """Authenticates websocket connections from `?token=<access jwt>`."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        token = parse_qs(scope.get("query_string", b"").decode()).get("token", [None])[0]
        user = await database_sync_to_async(user_from_token)(token) if token else None
        scope["user"] = user or AnonymousUser()
        return await self.inner(scope, receive, send)
