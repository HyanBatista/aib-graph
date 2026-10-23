"""Growing the class graph: one node per index topic, created from students' questions."""

import logging
from collections import deque

from django.db import transaction
from django.utils import timezone

from books.models import IndexTopic, TopicRelation
from classes.models import Classroom
from llm.client import LLMError, get_llm

from .models import GraphEdge, GraphNode, NodeProgress, StudentQuestion
from .realtime import broadcast, send_to_user

log = logging.getLogger(__name__)

COVERED, AVAILABLE, LOCKED = "covered", "available", "locked"


def prerequisites_map(book):
    """topic id -> set of prerequisite topic ids."""
    result = {}
    for src, dst in TopicRelation.objects.filter(src__book=book, kind=TopicRelation.Kind.PREREQUISITE).values_list("src", "dst"):
        result.setdefault(dst, set()).add(src)
    return result


def topic_states(classroom):
    """topic id -> covered (has a node) | available (prerequisites covered) | locked."""
    book = classroom.book
    covered = set(classroom.nodes.values_list("topic_id", flat=True))
    prereqs = prerequisites_map(book)
    states = {}
    for tid in book.topics.values_list("id", flat=True):
        if tid in covered:
            states[tid] = COVERED
        elif prereqs.get(tid, set()) <= covered:
            states[tid] = AVAILABLE
        else:
            states[tid] = LOCKED
    return states


def root_topic(book):
    prereqs = prerequisites_map(book)
    topics = list(book.topics.all())
    return next((t for t in topics if not prereqs.get(t.id)), topics[0])


def nearest_available(target_id, states, prereqs):
    """Walk prerequisites back from a locked topic to the closest one that can be taught now."""
    queue, seen = deque([target_id]), {target_id}
    while queue:
        tid = queue.popleft()
        if states.get(tid) == AVAILABLE:
            return tid
        for p in sorted(prereqs.get(tid, ())):
            if p not in seen and states.get(p) != COVERED:
                seen.add(p)
                queue.append(p)
    return target_id


def node_summary(node):
    """Shape of a node in graph listings and websocket events."""
    return {
        "id": node.id,
        "topic_id": node.topic_id,
        "title": node.topic.title,
        "level": node.topic.level,
        "parent_topic_id": node.topic.parent_id,
        "ready": node.ready,
        "created_at": node.created_at.isoformat(),
        "created_by_question_id": node.created_by_question_id,
    }


def edge_summary(edge):
    return {
        "id": edge.id, "src": edge.src_id, "dst": edge.dst_id, "kind": edge.kind,
        "origin_question_id": edge.origin_question_id,
    }


def add_edge(classroom, src, dst, question=None, kind=GraphEdge.Kind.GROWTH):
    if src is None or src.id == dst.id:
        return None
    edge, created = GraphEdge.objects.get_or_create(
        src=src, dst=dst, defaults={"classroom": classroom, "origin_question": question, "kind": kind}
    )
    if created:
        broadcast(classroom.id, "edge.created", {"edge": edge_summary(edge)})
    return edge


def lock_classroom(classroom):
    """Lock the class row until the transaction ends and refresh its status.

    Everything that grows the graph or changes its status takes this lock, so node
    creation, completion and freeze happen one at a time and always see each other.
    """
    classroom.status = Classroom.objects.select_for_update().values_list("status", flat=True).get(id=classroom.id)
    return classroom


def create_node_for_topic(classroom, topic, from_node=None, question=None):
    """Create the node of `topic` (once per class, even under concurrent requests) and link it.

    Returns (None, False) when the class no longer grows (complete or frozen) and the topic has no node.
    """
    with transaction.atomic():
        lock_classroom(classroom)
        if classroom.status != Classroom.Status.GROWING:
            node = classroom.nodes.filter(topic=topic).first()
            if node is not None:
                add_edge(classroom, from_node, node, question, GraphEdge.Kind.LINK)
            return node, False
        node, created = GraphNode.objects.get_or_create(
            classroom=classroom, topic=topic, defaults={"created_by_question": question}
        )
        if created:
            broadcast(classroom.id, "node.created", {"node": node_summary(node)})
            from .tasks import generate_node_content_task

            transaction.on_commit(lambda: generate_node_content_task.delay(node.id))
        add_edge(classroom, from_node, node, question, GraphEdge.Kind.GROWTH if created else GraphEdge.Kind.LINK)
        # Still under the class lock: a concurrent creator of the last missing topic waits
        # for this commit, then sees this node, so one of the two always completes the graph.
        if created:
            check_completion(classroom)
    return node, created


def generate_node_content(node_id):
    node = GraphNode.objects.select_related("topic", "classroom__book").get(id=node_id)
    classroom, topic, book = node.classroom, node.topic, node.classroom.book
    prereq_ids = prerequisites_map(book).get(topic.id, set())
    seen = list(IndexTopic.objects.filter(id__in=prereq_ids).values_list("title", flat=True))
    seen += [t for t in classroom.nodes.exclude(id=node.id).values_list("topic__title", flat=True) if t not in seen][:10]
    topic_data = {"title": topic.title, "summary": topic.summary, "page_start": topic.page_start, "page_end": topic.page_end}
    try:
        draft = get_llm().generate_node(topic_data, book.text_for_pages(topic.page_start, topic.page_end), seen, classroom.language)
    except LLMError as exc:
        log.warning("Node %s content failed: %s", node.id, exc)
        broadcast(classroom.id, "node.failed", {"node_id": node.id, "error": str(exc)})
        return
    node.lesson_md = draft.lesson_md
    node.quiz = [q.model_dump() for q in clean_quiz(draft.quiz)]
    node.ready = True
    node.save(update_fields=["lesson_md", "quiz", "ready"])
    broadcast(classroom.id, "node.ready", {"node": node_summary(node)})


def clean_quiz(quiz):
    return [q for q in quiz if len(q.options) >= 2 and 0 <= q.answer_index < len(q.options)]


def check_completion(classroom):
    """Mark the class complete once every topic has a node. Call it holding `lock_classroom`."""
    if classroom.status != Classroom.Status.GROWING:
        return False
    if classroom.book.topics.exclude(nodes__classroom=classroom).exists():
        return False
    classroom.status = Classroom.Status.COMPLETE
    classroom.save(update_fields=["status"])
    broadcast(classroom.id, "graph.completed", {})
    broadcast(classroom.id, "class.status", {"status": classroom.status, "detail": ""})
    return True


def question_summary(q):
    return {
        "id": q.id,
        "node_id": q.node_id,
        "text": q.text,
        "answer_md": q.answer_md,
        "outcome": q.outcome,
        "resolved_topic_id": q.resolved_topic_id,
        "target_node_id": q.target_node_id,
        "created_at": q.created_at.isoformat(),
    }


def handle_question(question_id):
    q = StudentQuestion.objects.select_related("node__topic", "node__classroom__book").get(id=question_id)
    node, classroom = q.node, q.node.classroom
    book = classroom.book
    states = topic_states(classroom)
    topics = [
        {"id": t.id, "title": t.title, "summary": t.summary, "status": states[t.id]}
        for t in book.topics.all()
    ]
    current = {"id": node.topic_id, "title": node.topic.title}
    try:
        routing = get_llm().route_question(
            q.text, current, topics, book.text_for_pages(node.topic.page_start, node.topic.page_end, 20_000), classroom.language
        )
    except LLMError as exc:
        log.warning("Question %s failed: %s", q.id, exc)
        q.outcome = StudentQuestion.Outcome.FAILED
        q.answer_md = "Sorry, the assistant could not answer right now. Please ask again."
        q.save(update_fields=["outcome", "answer_md"])
        send_to_user(q.student_id, classroom.id, "question.answered", {"question": question_summary(q)})
        return

    target_id = routing.target_topic_id if routing.target_topic_id in states else None
    q.answer_md = routing.answer_md
    q.resolved_topic_id = target_id

    with transaction.atomic():
        # The LLM call took a while: the class may have been frozen or grown meanwhile.
        lock_classroom(classroom)
        can_grow = classroom.status == Classroom.Status.GROWING
        can_link = can_grow or classroom.status == Classroom.Status.COMPLETE
        if target_id is not None:
            states = topic_states(classroom)
        if target_id is None or not can_link:
            q.outcome = StudentQuestion.Outcome.ANSWERED_ONLY
        elif states[target_id] == COVERED:
            target = classroom.nodes.get(topic_id=target_id)
            q.target_node = target
            q.outcome = StudentQuestion.Outcome.LINKED_EXISTING
            q.save()
            add_edge(classroom, node, target, q, GraphEdge.Kind.LINK)
        elif not can_grow:
            q.outcome = StudentQuestion.Outcome.ANSWERED_ONLY
        else:
            topic_id = target_id
            if states[target_id] == LOCKED:
                topic_id = nearest_available(target_id, states, prerequisites_map(book))
            topic = IndexTopic.objects.get(id=topic_id)
            if topic_id != target_id:
                wanted = IndexTopic.objects.get(id=target_id)
                q.answer_md += f"\n\n> To get to **{wanted.title}**, the course first opens **{topic.title}**."
            q.save()
            target, created = create_node_for_topic(classroom, topic, from_node=node, question=q)
            q.target_node = target
            q.outcome = StudentQuestion.Outcome.CREATED_NODE if created else StudentQuestion.Outcome.LINKED_EXISTING
        q.save()
        mark_question_done(q.student_id, node)
    send_to_user(q.student_id, classroom.id, "question.answered", {"question": question_summary(q)})


def mark_question_done(student_id, node):
    progress, _ = NodeProgress.objects.get_or_create(student_id=student_id, node=node)
    progress.question_done = True
    progress.refresh_completion(timezone.now())
    progress.save()


def expand_topic(classroom, topic):
    """Staff fallback when students' questions don't reach a topic."""
    prereqs = prerequisites_map(classroom.book).get(topic.id, set())
    from_node = (
        classroom.nodes.filter(topic_id__in=prereqs).order_by("-created_at").first()
        or (classroom.nodes.filter(topic_id=topic.parent_id).first() if topic.parent_id else None)
        or classroom.nodes.order_by("created_at").first()
    )
    return create_node_for_topic(classroom, topic, from_node=from_node)


@transaction.atomic
def freeze(classroom):
    """Freeze the graph. Returns False if the class is no longer growing or complete."""
    lock_classroom(classroom)
    if classroom.status not in (Classroom.Status.GROWING, Classroom.Status.COMPLETE):
        return False
    classroom.status = Classroom.Status.FROZEN
    classroom.frozen_at = timezone.now()
    classroom.save(update_fields=["status", "frozen_at"])
    broadcast(classroom.id, "graph.frozen", {})
    broadcast(classroom.id, "class.status", {"status": classroom.status, "detail": ""})
    return True
