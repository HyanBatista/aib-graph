import pytest

from assessment.models import ItemAnswer
from assessment.models import Test as FinalTest
from classes.models import Classroom
from graph.services import AVAILABLE, expand_topic, topic_states


@pytest.fixture
def frozen_class(growing_class, people, api):
    classroom = Classroom.objects.get(id=growing_class)
    for _ in range(4):  # a few more nodes
        available = [tid for tid, s in topic_states(classroom).items() if s == AVAILABLE]
        expand_topic(classroom, classroom.book.topics.get(id=available[0]))
    assert api(people["prof"]).post(f"/classes/{growing_class}/freeze")[0] == 200
    return growing_class


def test_test_lifecycle(frozen_class, people, api):
    prof, ta, s1 = api(people["prof"]), api(people["ta"]), api(people["s1"])
    assert ta.post(f"/classes/{frozen_class}/test/generate")[0] == 403
    status, body = prof.post(f"/classes/{frozen_class}/test/generate")
    assert status == 200, body
    test = body["test"]
    assert test["status"] == "draft"
    assert test["covered_nodes"] == test["total_nodes"] == 5  # every node has an item
    assert s1.get(f"/classes/{frozen_class}/test")[1]["test"] is None  # drafts are hidden from students

    mcq = next(i for i in test["items"] if i["kind"] == "mcq")
    status, edited = ta.put(f"/classes/{frozen_class}/test/items/{mcq['id']}", {**mcq, "prompt": "Edited?", "points": 2})
    assert status == 200 and edited["prompt"] == "Edited?"
    bad = {**mcq, "answer_index": 9}
    assert ta.put(f"/classes/{frozen_class}/test/items/{mcq['id']}", bad)[0] == 400

    assert prof.post(f"/classes/{frozen_class}/test/publish")[0] == 200
    status, student_view = s1.get(f"/classes/{frozen_class}/test")
    items = student_view["test"]["items"]
    assert all("answer_index" not in i and "rubric" not in i for i in items)

    answers = []
    for item in items:
        if item["kind"] == "mcq":
            key = FinalTest.objects.get(id=test["id"]).items.get(id=item["id"]).answer_index
            answers.append({"item_id": item["id"], "choice": key})
        else:
            answers.append({"item_id": item["id"], "text": "something unrelated"})
    status, after = s1.post(f"/classes/{frozen_class}/test/attempt", {"answers": answers})
    assert status == 200, after
    attempt = after["test"]["my_attempt"]
    assert attempt["pending"] == 0  # open answers graded by the (fake) AI right away
    assert all(a["graded_by"] in ("auto", "ai") for a in attempt["answers"])
    assert 0 < attempt["score"] <= 1
    assert s1.post(f"/classes/{frozen_class}/test/attempt", {"answers": answers})[0] == 409

    open_answer = next((a for a in attempt["answers"] if a["graded_by"] == "ai"), None)
    if open_answer:
        status, graded = ta.patch(f"/classes/{frozen_class}/test/answers/{open_answer['id']}", {"score": 1, "feedback": "ok"})
        assert graded["graded_by"] == "assistant"
        assert ItemAnswer.objects.get(id=open_answer["id"]).attempt.score > attempt["score"]


def test_publish_requires_full_coverage(frozen_class, people, api):
    prof = api(people["prof"])
    test = prof.post(f"/classes/{frozen_class}/test/generate")[1]["test"]
    node_id = test["items"][0]["node_id"]
    for item in [i for i in test["items"] if i["node_id"] == node_id]:
        prof.delete(f"/classes/{frozen_class}/test/items/{item['id']}")
    status, body = prof.post(f"/classes/{frozen_class}/test/publish")
    assert status == 400 and "every node" in body["detail"]


def test_generate_needs_frozen_graph(growing_class, people, api):
    assert api(people["prof"]).post(f"/classes/{growing_class}/test/generate")[0] == 409
