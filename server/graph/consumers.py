from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from classes.models import Membership

from .realtime import class_group, user_group


class ClassConsumer(AsyncJsonWebsocketConsumer):
    """One socket per open class. Server → client only; clients act through the REST API."""

    async def connect(self):
        user = self.scope.get("user")
        self.class_id = int(self.scope["url_route"]["kwargs"]["class_id"])
        if not user or not user.is_authenticated or not await self._is_member(user.id):
            await self.close(code=4403)
            return
        self.groups_joined = [class_group(self.class_id), user_group(user.id)]
        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "payload": {"class_id": self.class_id}})

    async def disconnect(self, code):
        for group in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"event": "pong", "payload": {}})

    async def push(self, message):
        # Personal events reach every socket of the user; only forward those of this class.
        if message["payload"].get("class_id") != self.class_id:
            return
        await self.send_json({"event": message["event"], "payload": message["payload"]})

    @database_sync_to_async
    def _is_member(self, user_id):
        return Membership.objects.filter(user_id=user_id, classroom_id=self.class_id).exists()
