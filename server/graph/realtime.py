"""Push events to desktop clients over the class websocket.

Events are sent after the current transaction commits, so clients never receive
an id they can't fetch yet.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction


def class_group(class_id):
    return f"class_{class_id}"


def user_group(user_id):
    return f"user_{user_id}"


def _send(group, event, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, {"type": "push", "event": event, "payload": payload})


def broadcast(class_id, event, payload=None):
    transaction.on_commit(lambda: _send(class_group(class_id), event, {"class_id": class_id, **(payload or {})}))


def send_to_user(user_id, class_id, event, payload=None):
    transaction.on_commit(lambda: _send(user_group(user_id), event, {"class_id": class_id, **(payload or {})}))
