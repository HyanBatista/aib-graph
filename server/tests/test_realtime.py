import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from accounts.tokens import issue_tokens
from config.asgi import application
from graph.models import GraphNode

pytestmark = pytest.mark.django_db(transaction=True)


async def connect(user, class_id):
    token = await sync_to_async(lambda: issue_tokens(user)["access"])()
    comm = WebsocketCommunicator(application, f"/ws/classes/{class_id}/?token={token}")
    connected, _ = await comm.connect()
    return comm, connected


async def next_event(comm, name, attempts=20):
    for _ in range(attempts):
        message = await comm.receive_json_from(timeout=5)
        if message["event"] == name:
            return message["payload"]
    raise AssertionError(f"no {name} event")


async def test_new_node_is_pushed_to_other_members(growing_class, people, api):
    watcher, ok = await connect(people["s2"], growing_class)
    assert ok
    assert (await watcher.receive_json_from())["event"] == "connected"
    asker, ok = await connect(people["s1"], growing_class)
    assert ok
    await asker.receive_json_from()

    root = await sync_to_async(lambda: GraphNode.objects.get(classroom_id=growing_class))()
    status, q = await sync_to_async(
        lambda: api(people["s1"]).post(f"/classes/{growing_class}/nodes/{root.id}/question", {"text": "What is an algorithm exactly?"})
    )()
    assert q["outcome"] == "created_node"

    created = await next_event(watcher, "node.created")
    assert created["node"]["title"] == "What Is an Algorithm"
    assert (await next_event(watcher, "node.ready"))["node"]["ready"] is True
    answered = await next_event(asker, "question.answered")
    assert answered["question"]["id"] == q["id"]
    await watcher.disconnect()
    await asker.disconnect()


async def test_outsiders_and_anonymous_are_rejected(growing_class, people):
    comm, ok = await connect(people["outsider"], growing_class)
    assert not ok
    comm = WebsocketCommunicator(application, f"/ws/classes/{growing_class}/")
    connected, _ = await comm.connect()
    assert not connected
