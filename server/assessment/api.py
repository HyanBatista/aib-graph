from django.db import IntegrityError, transaction
from django.utils import timezone
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from classes.models import Classroom, Membership
from classes.permissions import STAFF, get_membership, require_role, require_status
from graph.realtime import broadcast

from . import services
from .models import ItemAnswer, Test, TestAttempt, TestItem
from .tasks import generate_test_task

router = Router(tags=["tests"])
Role = Membership.Role


class ItemIn(Schema):
    node_id: int
    kind: str
    prompt: str
    options: list[str] = []
    answer_index: int | None = None
    rubric: str = ""
    points: float = 1


class AnswerIn(Schema):
    item_id: int
    choice: int | None = None
    text: str = ""


class AttemptIn(Schema):
    answers: list[AnswerIn]


class GradeIn(Schema):
    score: float
    feedback: str | None = None


def item_out(item, with_key):
    data = {
        "id": item.id, "node_id": item.node_id, "node_title": item.node.topic.title, "order": item.order,
        "kind": item.kind, "prompt": item.prompt, "options": item.options, "points": item.points,
    }
    if with_key:
        data.update(answer_index=item.answer_index, rubric=item.rubric)
    return data


def answer_out(a):
    return {
        "id": a.id, "item_id": a.item_id, "choice": a.choice, "text": a.text,
        "score": a.score, "feedback": a.feedback, "graded_by": a.graded_by,
    }


def attempt_out(attempt, with_answers=True):
    data = {
        "id": attempt.id,
        "student_id": attempt.student_id,
        "student": attempt.student.full_name or attempt.student.email,
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "score": attempt.score,
        "pending": attempt.answers.filter(score__isnull=True).count(),
    }
    if with_answers:
        data["answers"] = [answer_out(a) for a in attempt.answers.order_by("item__order", "item_id")]
    return data


def get_test(classroom):
    test = Test.objects.filter(classroom=classroom).first()
    if test is None:
        raise HttpError(404, "No test yet")
    return test


def validate_item(data, classroom):
    if not classroom.nodes.filter(id=data.node_id).exists():
        raise HttpError(400, "Unknown node")
    if data.kind not in (TestItem.Kind.MCQ, TestItem.Kind.OPEN):
        raise HttpError(400, "kind must be 'mcq' or 'open'")
    if not data.prompt.strip():
        raise HttpError(400, "The question can't be empty")
    if data.kind == TestItem.Kind.MCQ and (
        len(data.options) < 2 or data.answer_index is None or not 0 <= data.answer_index < len(data.options)
    ):
        raise HttpError(400, "A multiple-choice item needs 2+ options and a valid answer")
    if data.kind == TestItem.Kind.OPEN and not data.rubric.strip():
        raise HttpError(400, "An open item needs a rubric")
    if data.points <= 0:
        raise HttpError(400, "Points must be positive")


@router.get("/{class_id}/test")
def test_detail(request, class_id: int):
    membership = get_membership(request.auth, class_id)
    classroom = membership.classroom
    test = Test.objects.filter(classroom=classroom).first()
    is_staff = membership.role in STAFF
    if test is None or (not is_staff and test.status in (Test.Status.GENERATING, Test.Status.DRAFT)):
        return {"test": None}
    items = test.items.select_related("node__topic")
    data = {
        "id": test.id, "title": test.title, "status": test.status,
        "published_at": test.published_at.isoformat() if test.published_at else None,
        "items": [item_out(i, with_key=is_staff) for i in items],
        "covered_nodes": len({i.node_id for i in items}),
        "total_nodes": classroom.nodes.count(),
    }
    if is_staff:
        data["attempts"] = [attempt_out(a, with_answers=False) for a in test.attempts.select_related("student")]
    else:
        mine = test.attempts.filter(student=request.auth).first()
        data["my_attempt"] = attempt_out(mine) if mine else None
        if mine:  # the key is revealed once the student has submitted
            data["items"] = [item_out(i, with_key=True) for i in items]
    return {"test": data}


@router.post("/{class_id}/test/generate")
def generate(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), Role.PROFESSOR)
    classroom = require_status(membership.classroom, Classroom.Status.FROZEN)
    with transaction.atomic():
        test, _ = Test.objects.get_or_create(classroom=classroom, defaults={"title": f"{classroom.name} — final test"})
        if test.status in (Test.Status.PUBLISHED, Test.Status.CLOSED):
            raise HttpError(409, "The test is already published")
        test.status = Test.Status.GENERATING
        test.save(update_fields=["status"])
        transaction.on_commit(lambda: generate_test_task.delay(classroom.id))
    return test_detail(request, class_id)


@router.post("/{class_id}/test/items")
def add_item(request, class_id: int, data: ItemIn):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    test = get_test(membership.classroom)
    if test.status != Test.Status.DRAFT:
        raise HttpError(409, "Only a draft test can be edited")
    validate_item(data, membership.classroom)
    last = test.items.order_by("-order").first()
    item = TestItem.objects.create(test=test, order=(last.order + 1) if last else 0, **data.dict())
    return item_out(TestItem.objects.select_related("node__topic").get(id=item.id), with_key=True)


@router.put("/{class_id}/test/items/{item_id}")
def update_item(request, class_id: int, item_id: int, data: ItemIn):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    test = get_test(membership.classroom)
    if test.status != Test.Status.DRAFT:
        raise HttpError(409, "Only a draft test can be edited")
    item = test.items.filter(id=item_id).first()
    if item is None:
        raise HttpError(404, "Item not found")
    validate_item(data, membership.classroom)
    for field, value in data.dict().items():
        setattr(item, field, value)
    if item.kind == TestItem.Kind.OPEN:
        item.options, item.answer_index = [], None
    item.save()
    return item_out(TestItem.objects.select_related("node__topic").get(id=item.id), with_key=True)


@router.delete("/{class_id}/test/items/{item_id}", response={204: None})
def delete_item(request, class_id: int, item_id: int):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    test = get_test(membership.classroom)
    if test.status != Test.Status.DRAFT:
        raise HttpError(409, "Only a draft test can be edited")
    test.items.filter(id=item_id).delete()
    return Status(204, None)


@router.post("/{class_id}/test/publish")
def publish(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), Role.PROFESSOR)
    test = get_test(membership.classroom)
    if test.status != Test.Status.DRAFT:
        raise HttpError(409, "Only a draft test can be published")
    covered = set(test.items.values_list("node_id", flat=True))
    missing = membership.classroom.nodes.exclude(id__in=covered).count()
    if missing:
        raise HttpError(400, f"{missing} node(s) have no test item; every node must be covered")
    test.status = Test.Status.PUBLISHED
    test.published_at = timezone.now()
    test.save(update_fields=["status", "published_at"])
    broadcast(class_id, "test.published", {"test_id": test.id})
    return test_detail(request, class_id)


@router.post("/{class_id}/test/close")
def close(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), Role.PROFESSOR)
    test = get_test(membership.classroom)
    if test.status != Test.Status.PUBLISHED:
        raise HttpError(409, "Only a published test can be closed")
    test.status = Test.Status.CLOSED
    test.save(update_fields=["status"])
    broadcast(class_id, "test.closed", {"test_id": test.id})
    return test_detail(request, class_id)


@router.post("/{class_id}/test/attempt")
def submit(request, class_id: int, data: AttemptIn):
    membership = require_role(get_membership(request.auth, class_id), Role.STUDENT)
    test = get_test(membership.classroom)
    if test.status != Test.Status.PUBLISHED:
        raise HttpError(409, "The test is not open")
    answers = {a.item_id: {"choice": a.choice, "text": a.text} for a in data.answers}
    try:
        services.submit_attempt(test, request.auth, answers)
    except IntegrityError:  # `one_attempt_per_student`, also for a concurrent double submit
        raise HttpError(409, "You already took this test")
    broadcast(class_id, "metrics.changed", {})
    return test_detail(request, class_id)


@router.get("/{class_id}/test/attempts/{attempt_id}")
def attempt_detail(request, class_id: int, attempt_id: int):
    membership = get_membership(request.auth, class_id)
    attempt = TestAttempt.objects.select_related("student").filter(id=attempt_id, test__classroom_id=class_id).first()
    if attempt is None or (membership.role not in STAFF and attempt.student_id != request.auth.id):
        raise HttpError(404, "Attempt not found")
    return attempt_out(attempt)


@router.patch("/{class_id}/test/answers/{answer_id}")
def grade_answer(request, class_id: int, answer_id: int, data: GradeIn):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    answer = ItemAnswer.objects.select_related("attempt").filter(id=answer_id, attempt__test__classroom_id=class_id).first()
    if answer is None:
        raise HttpError(404, "Answer not found")
    role = ItemAnswer.GradedBy.PROFESSOR if membership.role == Role.PROFESSOR else ItemAnswer.GradedBy.ASSISTANT
    answer = services.override_grade(answer, data.score, data.feedback, role)
    broadcast(class_id, "metrics.changed", {})
    return answer_out(answer)
