import threading
import time

import pytest
from django.db import connection, transaction

from books.models import IndexTopic, TopicRelation
from classes.models import Classroom
from graph.models import GraphEdge, GraphNode, NodeProgress, StudentQuestion
from graph.services import AVAILABLE, COVERED, LOCKED, create_node_for_topic, topic_states


def node_by_title(class_id, title):
    return GraphNode.objects.get(classroom_id=class_id, topic__title=title)


def test_pipeline_builds_index_kg_and_first_node(growing_class, people, api):
    classroom = Classroom.objects.get(id=growing_class)
    assert classroom.status == Classroom.Status.GROWING
    assert classroom.book.topics.count() == 20  # from the sample PDF's bookmarks
    assert TopicRelation.objects.filter(src__book=classroom.book).exists()

    nodes = list(classroom.nodes.all())
    assert len(nodes) == 1
    root = nodes[0]
    assert root.topic.title == "Foundations of Algorithms"
    assert root.ready and root.lesson_md and root.quiz

    status, graph = api(people["s1"]).get(f"/classes/{growing_class}/graph")
    assert status == 200
    assert graph["coverage"] == {"covered": 1, "total": 20}


def test_index_can_be_edited_during_review(people, api, transactional_db):
    from demo.course import SAMPLE_PDF

    prof = api(people["prof"])
    class_id = prof.post("/classes", {"name": "Edit me"})[1]["id"]
    prof.upload(f"/classes/{class_id}/book", SAMPLE_PDF)
    status, index = prof.put(f"/classes/{class_id}/index", {"topics": [
        {"title": "Only topic", "summary": "s", "page_start": 2, "page_end": 3,
         "subtopics": [{"title": "Sub", "page_start": 3, "page_end": 99}]},
    ]})
    assert status == 200
    assert [t["title"] for t in index["topics"]] == ["Only topic", "Sub"]
    assert index["topics"][1]["page_end"] == 21  # clamped to the page count

    student = people["s1"]
    from classes.models import Membership

    Membership.objects.create(user=student, classroom_id=class_id, role="student")
    assert api(student).post(f"/classes/{class_id}/index/approve")[0] == 403


def ask(api, user, class_id, node, text):
    return api(user).post(f"/classes/{class_id}/nodes/{node.id}/question", {"text": text})


def test_question_on_available_topic_creates_node(growing_class, people, api):
    root = node_by_title(growing_class, "Foundations of Algorithms")
    status, q = ask(api, people["s1"], growing_class, root, "What is an algorithm exactly?")
    assert status == 200, q
    assert q["outcome"] == "created_node"
    new = GraphNode.objects.get(id=q["target_node_id"])
    assert new.topic.title == "What Is an Algorithm"
    assert new.ready and new.created_by_question_id == q["id"]
    edge = GraphEdge.objects.get(src=root, dst=new)
    assert edge.kind == GraphEdge.Kind.GROWTH
    assert NodeProgress.objects.get(student=people["s1"], node=root).question_done


def test_question_on_covered_topic_links_existing(growing_class, people, api):
    root = node_by_title(growing_class, "Foundations of Algorithms")
    ask(api, people["s1"], growing_class, root, "What is an algorithm exactly?")
    child = node_by_title(growing_class, "What Is an Algorithm")
    status, q = ask(api, people["s2"], growing_class, child, "Tell me more about the foundations")
    assert q["outcome"] == "linked_existing"
    assert q["target_node_id"] == root.id
    assert GraphEdge.objects.get(src=child, dst=root).kind == GraphEdge.Kind.LINK


def test_off_book_question_is_only_answered(growing_class, people, api):
    root = node_by_title(growing_class, "Foundations of Algorithms")
    status, q = ask(api, people["s1"], growing_class, root, "Who won the football cup?")
    assert q["outcome"] == "answered_only"
    assert GraphNode.objects.filter(classroom_id=growing_class).count() == 1


def test_question_on_locked_topic_opens_nearest_prerequisite(growing_class, people, api):
    classroom = Classroom.objects.get(id=growing_class)
    dijkstra = IndexTopic.objects.get(book=classroom.book, title="Shortest Paths with Dijkstra")
    assert topic_states(classroom)[dijkstra.id] == LOCKED
    root = node_by_title(growing_class, "Foundations of Algorithms")
    status, q = ask(api, people["s1"], growing_class, root, "How does Dijkstra find shortest paths?")
    assert q["outcome"] == "created_node"
    assert q["resolved_topic_id"] == dijkstra.id
    created = GraphNode.objects.get(id=q["target_node_id"])
    assert created.topic_id != dijkstra.id
    assert topic_states(classroom)[created.topic_id] == COVERED
    assert "first opens" in q["answer_md"]


def test_one_question_per_node(growing_class, people, api):
    root = node_by_title(growing_class, "Foundations of Algorithms")
    assert ask(api, people["s1"], growing_class, root, "Who won the football cup?")[0] == 200
    assert ask(api, people["s1"], growing_class, root, "And the next one?")[0] == 409
    assert ask(api, people["ta"], growing_class, root, "Staff can't ask questions")[0] == 403


def test_completion_and_freeze(growing_class, people, api):
    classroom = Classroom.objects.get(id=growing_class)
    ta = api(people["ta"])
    # Staff expands topics in prerequisite order until everything is covered.
    while True:
        states = topic_states(classroom)
        available = [tid for tid, s in states.items() if s == AVAILABLE]
        if not available:
            break
        status, body = ta.post(f"/classes/{growing_class}/topics/{available[0]}/expand")
        assert status == 200, body
    classroom.refresh_from_db()
    assert classroom.status == Classroom.Status.COMPLETE
    assert classroom.nodes.count() == 20

    assert api(people["ta"]).post(f"/classes/{growing_class}/freeze")[0] == 403
    status, body = api(people["prof"]).post(f"/classes/{growing_class}/freeze")
    assert status == 200 and body["status"] == "frozen"
    root = node_by_title(growing_class, "Foundations of Algorithms")
    assert ask(api, people["s1"], growing_class, root, "Is this still allowed?")[0] == 409


def test_quiz_scoring_and_completion(growing_class, people, api):
    root = node_by_title(growing_class, "Foundations of Algorithms")
    s1 = api(people["s1"])
    status, detail = s1.get(f"/classes/{growing_class}/nodes/{root.id}")
    assert "answer_index" not in detail["quiz"][0]  # hidden before submitting
    answers = [q["answer_index"] for q in root.quiz]
    answers[0] = (answers[0] + 1) % len(root.quiz[0]["options"])
    status, result = s1.post(f"/classes/{growing_class}/nodes/{root.id}/quiz", {"answers": answers})
    assert status == 200
    assert result["score"] == pytest.approx((len(answers) - 1) / len(answers))
    assert not result["progress"]["completed"]
    assert s1.post(f"/classes/{growing_class}/nodes/{root.id}/quiz", {"answers": answers})[0] == 409

    ask(api, people["s1"], growing_class, root, "Who won the football cup?")
    progress = NodeProgress.objects.get(student=people["s1"], node=root)
    assert progress.completed_at is not None


@pytest.mark.skipif(connection.vendor == "sqlite", reason="needs a database with real concurrent writers")
def test_concurrent_questions_create_a_single_node(growing_class):
    classroom = Classroom.objects.get(id=growing_class)
    topic = IndexTopic.objects.get(book=classroom.book, title="What Is an Algorithm")
    root = classroom.nodes.get()
    barrier = threading.Barrier(4)
    results = []

    def worker():
        from django.db import connection as conn

        try:
            barrier.wait()
            results.append(create_node_for_topic(classroom, topic, from_node=root)[1])
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    assert GraphNode.objects.filter(classroom=classroom, topic=topic).count() == 1


def test_get_or_create_is_idempotent(growing_class):
    classroom = Classroom.objects.get(id=growing_class)
    topic = IndexTopic.objects.get(book=classroom.book, title="What Is an Algorithm")
    root = classroom.nodes.get()
    assert create_node_for_topic(classroom, topic, from_node=root)[1] is True
    assert create_node_for_topic(classroom, topic, from_node=root)[1] is False
    assert GraphNode.objects.filter(classroom=classroom, topic=topic).count() == 1


def test_permissions(growing_class, people, api):
    outsider, student = api(people["outsider"]), api(people["s1"])
    assert outsider.get(f"/classes/{growing_class}/graph")[0] == 404
    assert student.get(f"/classes/{growing_class}/metrics")[0] == 403
    assert student.get(f"/classes/{growing_class}/members")[0] == 403
    assert student.post(f"/classes/{growing_class}/freeze")[0] == 403
    topic = Classroom.objects.get(id=growing_class).book.topics.last()
    assert student.post(f"/classes/{growing_class}/topics/{topic.id}/expand")[0] == 403
    assert student.get(f"/classes/{growing_class}/metrics/students/{people['s2'].id}")[0] == 403
    assert student.get(f"/classes/{growing_class}/metrics/students/{people['s1'].id}")[0] == 200


def test_join_by_invite_code(growing_class, people, api):
    code = api(people["prof"]).get(f"/classes/{growing_class}")[1]["invite_code"]
    assert api(people["s1"]).get(f"/classes/{growing_class}")[1]["invite_code"] is None
    status, body = api(people["outsider"]).post("/classes/join", {"invite_code": code.lower()})
    assert status == 200 and body["role"] == "student"
    status, body = api(people["prof"]).patch(f"/classes/{growing_class}/members/{people['outsider'].id}", {"role": "assistant"})
    assert body["role"] == "assistant"


def test_failed_llm_question_can_be_retried(growing_class, people, api, monkeypatch):
    from llm.client import FakeLLM, LLMError

    def boom(*a, **k):
        raise LLMError("quota")

    monkeypatch.setattr(FakeLLM, "route_question", boom)
    root = node_by_title(growing_class, "Foundations of Algorithms")
    status, q = ask(api, people["s1"], growing_class, root, "What is an algorithm exactly?")
    assert q["outcome"] == "failed"
    monkeypatch.undo()
    status, q = ask(api, people["s1"], growing_class, root, "What is an algorithm exactly?")
    assert q["outcome"] == "created_node"
    assert StudentQuestion.objects.filter(student=people["s1"], node=root).count() == 2


def test_freeze_while_a_question_is_routed_creates_nothing(growing_class, people, api, monkeypatch):
    from llm.client import FakeLLM

    from graph.services import freeze

    route = FakeLLM.route_question

    def route_then_freeze(self, *args, **kwargs):
        # The professor freezes the graph while the LLM is still answering.
        freeze(Classroom.objects.get(id=growing_class))
        return route(self, *args, **kwargs)

    monkeypatch.setattr(FakeLLM, "route_question", route_then_freeze)
    root = node_by_title(growing_class, "Foundations of Algorithms")
    status, q = ask(api, people["s1"], growing_class, root, "What is an algorithm exactly?")
    assert status == 200, q
    assert q["outcome"] == "answered_only" and q["answer_md"]
    assert GraphNode.objects.filter(classroom_id=growing_class).count() == 1
    assert not GraphEdge.objects.filter(classroom_id=growing_class).exists()
    assert Classroom.objects.get(id=growing_class).status == Classroom.Status.FROZEN


def test_frozen_class_does_not_grow_from_services(growing_class):
    from graph.services import freeze

    classroom = Classroom.objects.get(id=growing_class)
    assert freeze(classroom) is True
    assert freeze(classroom) is False  # already frozen
    topic = IndexTopic.objects.get(book=classroom.book, title="What Is an Algorithm")
    assert create_node_for_topic(classroom, topic, from_node=classroom.nodes.get()) == (None, False)
    assert classroom.nodes.count() == 1


def test_one_question_per_node_is_enforced_by_the_database(growing_class, people):
    from django.db import IntegrityError, transaction

    root = node_by_title(growing_class, "Foundations of Algorithms")
    StudentQuestion.objects.create(student=people["s1"], node=root, text="first", outcome="failed")
    StudentQuestion.objects.create(student=people["s1"], node=root, text="second")  # retry after a failure
    with pytest.raises(IntegrityError), transaction.atomic():
        StudentQuestion.objects.create(student=people["s1"], node=root, text="third")


@pytest.mark.skipif(connection.vendor == "sqlite", reason="needs a database with real concurrent writers")
def test_concurrent_creation_of_the_last_topics_completes_the_graph(growing_class):
    classroom = Classroom.objects.get(id=growing_class)
    root = classroom.nodes.get()
    missing = list(classroom.book.topics.exclude(nodes__classroom=classroom).order_by("order"))
    for topic in missing[:-2]:
        create_node_for_topic(classroom, topic, from_node=root)
    last_two = missing[-2:]
    assert Classroom.objects.get(id=growing_class).status == Classroom.Status.GROWING
    barrier = threading.Barrier(2)

    def worker(topic):
        from django.db import connection as conn

        try:
            barrier.wait()
            # Like `handle_question`: the node is created inside a longer transaction.
            with transaction.atomic():
                create_node_for_topic(Classroom.objects.get(id=growing_class), topic, from_node=root)
                time.sleep(0.3)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(t,)) for t in last_two]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert classroom.nodes.count() == classroom.book.topics.count()
    assert Classroom.objects.get(id=growing_class).status == Classroom.Status.COMPLETE
