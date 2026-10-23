from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify
from ninja import Router, Schema
from ninja.errors import HttpError

from books.models import IndexTopic
from classes.models import Classroom, Membership
from classes.permissions import STAFF, get_membership, require_role, require_status

from . import services
from .egf import export_egf
from .models import GraphNode, NodeProgress, StudentQuestion
from .realtime import broadcast
from .tasks import generate_node_content_task, handle_question_task

router = Router(tags=["graph"])
Status = Classroom.Status
GRAPH_STATUSES = (Status.GROWING, Status.COMPLETE, Status.FROZEN)


class QuizIn(Schema):
    answers: list[int | None]


class QuestionIn(Schema):
    text: str


def get_node(classroom, node_id):
    node = GraphNode.objects.select_related("topic").filter(classroom=classroom, id=node_id).first()
    if node is None:
        raise HttpError(404, "Node not found")
    return node


@router.get("/{class_id}/graph")
def get_graph(request, class_id: int):
    membership = get_membership(request.auth, class_id)
    classroom = membership.classroom
    nodes = list(classroom.nodes.select_related("topic", "created_by_question__student"))
    is_staff = membership.role in STAFF

    mine = {p.node_id: p for p in NodeProgress.objects.filter(student=request.auth, node__classroom=classroom)}
    stats = {
        row["node"]: row
        for row in NodeProgress.objects.filter(node__classroom=classroom)
        .values("node")
        .annotate(avg_score=Avg("quiz_score"), visits=Count("id"))
    }
    result_nodes = []
    for n in nodes:
        data = services.node_summary(n)
        q = n.created_by_question
        data["created_by"] = (q.student.full_name or q.student.email) if q else None
        data["avg_score"] = stats.get(n.id, {}).get("avg_score")
        data["visits"] = stats.get(n.id, {}).get("visits", 0)
        p = mine.get(n.id)
        data["my_state"] = (
            "completed" if p and p.completed_at else "in_progress" if p else "new"
        )
        data["my_score"] = p.quiz_score if p else None
        result_nodes.append(data)

    total = classroom.book.topics.count() if hasattr(classroom, "book") else 0
    payload = {
        "status": classroom.status,
        "nodes": result_nodes,
        "edges": [services.edge_summary(e) for e in classroom.edges.all()],
        "coverage": {"covered": len(nodes), "total": total},
    }
    if is_staff and classroom.status in GRAPH_STATUSES:
        states = services.topic_states(classroom)
        payload["uncovered"] = [
            {"topic_id": t.id, "title": t.title, "level": t.level, "state": states[t.id]}
            for t in classroom.book.topics.all()
            if states[t.id] != services.COVERED
        ]
    return payload


@router.get("/{class_id}/nodes/{node_id}")
def node_detail(request, class_id: int, node_id: int):
    membership = get_membership(request.auth, class_id)
    node = get_node(membership.classroom, node_id)
    progress = NodeProgress.objects.filter(student=request.auth, node=node).first()
    reveal = membership.role in STAFF or (progress and progress.quiz_submitted_at)
    quiz = [
        q if reveal else {"prompt": q["prompt"], "options": q["options"]}
        for q in node.quiz
    ]
    my_question = StudentQuestion.objects.filter(student=request.auth, node=node).exclude(
        outcome=StudentQuestion.Outcome.FAILED
    ).first()
    questions = []
    if membership.role in STAFF:
        questions = [
            {**services.question_summary(q), "student": q.student.full_name or q.student.email}
            for q in node.questions.select_related("student")
        ]
    parent = node.topic.parent
    return {
        **services.node_summary(node),
        "summary": node.topic.summary,
        "parent_title": parent.title if parent else None,
        "page_start": node.topic.page_start,
        "page_end": node.topic.page_end,
        "lesson_md": node.lesson_md,
        "quiz": quiz,
        "progress": progress_out(progress),
        "my_question": services.question_summary(my_question) if my_question else None,
        "questions": questions,
        "can_ask": membership.role == Membership.Role.STUDENT
        and membership.classroom.status in (Status.GROWING, Status.COMPLETE)
        and node.ready
        and my_question is None,
    }


def progress_out(p):
    if p is None:
        return None
    return {
        "quiz_score": p.quiz_score,
        "quiz_answers": p.quiz_answers,
        "question_done": p.question_done,
        "completed": p.completed_at is not None,
    }


@router.post("/{class_id}/nodes/{node_id}/open")
def open_node(request, class_id: int, node_id: int):
    membership = get_membership(request.auth, class_id)
    node = get_node(membership.classroom, node_id)
    if membership.role != Membership.Role.STUDENT:
        return {"progress": None}
    progress, created = NodeProgress.objects.get_or_create(student=request.auth, node=node)
    if created:
        broadcast(class_id, "metrics.changed", {})
    return {"progress": progress_out(progress)}


@router.post("/{class_id}/nodes/{node_id}/quiz")
def submit_quiz(request, class_id: int, node_id: int, data: QuizIn):
    membership = require_role(get_membership(request.auth, class_id), Membership.Role.STUDENT)
    node = get_node(membership.classroom, node_id)
    if not node.ready or not node.quiz:
        raise HttpError(409, "This node has no quiz yet")
    if len(data.answers) != len(node.quiz):
        raise HttpError(400, f"Expected {len(node.quiz)} answers")
    with transaction.atomic():
        progress, _ = NodeProgress.objects.select_for_update().get_or_create(student=request.auth, node=node)
        if progress.quiz_submitted_at:
            raise HttpError(409, "You already submitted this quiz")
        correct = [a == q["answer_index"] for a, q in zip(data.answers, node.quiz)]
        progress.quiz_answers = data.answers
        progress.quiz_score = sum(correct) / len(correct)
        progress.quiz_submitted_at = timezone.now()
        progress.refresh_completion(progress.quiz_submitted_at)
        progress.save()
        broadcast(class_id, "metrics.changed", {})
    return {
        "score": progress.quiz_score,
        "results": [
            {"correct": c, "answer_index": q["answer_index"], "feedback": q.get("feedback", "")}
            for c, q in zip(correct, node.quiz)
        ],
        "progress": progress_out(progress),
    }


@router.post("/{class_id}/nodes/{node_id}/question")
def ask_question(request, class_id: int, node_id: int, data: QuestionIn):
    membership = require_role(get_membership(request.auth, class_id), Membership.Role.STUDENT)
    classroom = require_status(membership.classroom, Status.GROWING, Status.COMPLETE)
    node = get_node(classroom, node_id)
    text = data.text.strip()
    if len(text) < 5:
        raise HttpError(400, "Please write a real question")
    if not node.ready:
        raise HttpError(409, "This node is still being generated")
    try:
        with transaction.atomic():
            NodeProgress.objects.get_or_create(student=request.auth, node=node)
            # The `one_question_per_node` constraint rejects a second question, even a concurrent one.
            question = StudentQuestion.objects.create(student=request.auth, node=node, text=text[:2000])
            transaction.on_commit(lambda: handle_question_task.delay(question.id))
    except IntegrityError:
        raise HttpError(409, "You already asked your question on this node")
    question.refresh_from_db()
    return services.question_summary(question)


@router.post("/{class_id}/topics/{topic_id}/expand")
def expand_topic(request, class_id: int, topic_id: int):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    classroom = require_status(membership.classroom, Status.GROWING)
    topic = IndexTopic.objects.filter(id=topic_id, book__classroom=classroom).first()
    if topic is None:
        raise HttpError(404, "Topic not found")
    node, created = services.expand_topic(classroom, topic)
    if not created:
        raise HttpError(409, "This topic already has a node")
    return services.node_summary(node)


@router.post("/{class_id}/nodes/{node_id}/regenerate")
def regenerate_node(request, class_id: int, node_id: int):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    classroom = require_status(membership.classroom, Status.GROWING, Status.COMPLETE)
    node = get_node(classroom, node_id)
    if node.progress.filter(quiz_submitted_at__isnull=False).exists():
        raise HttpError(409, "Students already answered this node's quiz")
    node.ready = False
    node.save(update_fields=["ready"])
    transaction.on_commit(lambda: generate_node_content_task.delay(node.id))
    return services.node_summary(node)


@router.get("/{class_id}/export.egf")
def export(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    classroom = require_status(membership.classroom, *GRAPH_STATUSES)
    response = JsonResponse(export_egf(classroom), json_dumps_params={"ensure_ascii": False, "indent": 2})
    filename = f"{slugify(classroom.name) or 'course'}.egf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
