import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.urls import path  # noqa: E402

from accounts.ws_auth import JWTQueryAuthMiddleware  # noqa: E402
from graph.consumers import ClassConsumer  # noqa: E402

websocket_urlpatterns = [path("ws/classes/<int:class_id>/", ClassConsumer.as_asgi())]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTQueryAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
