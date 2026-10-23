"""Final test: generated from the frozen graph so that every node is covered."""

import logging

from django.db import transaction
from django.utils import timezone

from classes.models import Classroom
from graph.realtime import broadcast, send_to_user
from llm.client import LLMError, get_llm

from .models import ItemAnswer, Test, TestAttempt, TestItem

log = logging.getLogger(__name__)

ITEMS_PER_NODE = 2


def lessons_payload(classroom):
    return [
        {
            "id": n.id,
            "title": n.topic.title,
            "summary": n.topic.summary,
            "key_ideas": n.lesson_md.split("Key ideas")[-1][:600] if "Key ideas" in n.lesson_md else n.lesson_md[:600],
            "quiz": n.quiz,
        }
        for n in classroom.nodes.select_related("topic").filter(ready=True)
    ]


def valid_item(d, node_ids):
    if d.node_id not in node_ids or not d.prompt.strip():
        return False
    if d.kind == "mcq":
        return len(d.options) >= 2 and d.answer_index is not None and 0 <= d.answer_index < len(d.options)
    return bool(d.rubric.strip())


def fallback_item(node):
    """Used for any node the model left out, so the test always covers the whole graph."""
    if node.quiz:
        q = node.quiz[0]
        return dict(kind=TestItem.Kind.MCQ, prompt=q["prompt"], options=q["options"], answer_index=q["answer_index"])
    return dict(
        kind=TestItem.Kind.OPEN,
        prompt=f'Explain the main idea of "{node.topic.title}".',
        rubric=node.topic.summary or node.topic.title,
    )


def generate_test(classroom_id):
    classroom = Classroom.objects.get(id=classroom_id)
    test = classroom.test
    nodes = {n.id: n for n in classroom.nodes.select_related("topic").filter(ready=True)}
    try:
        draft = get_llm().generate_test(lessons_payload(classroom), classroom.language, ITEMS_PER_NODE)
        drafts = [d for d in draft.items if valid_item(d, nodes)]
    except LLMError as exc:
        log.warning("Test generation failed, using fallback items: %s", exc)
        drafts = []

    with transaction.atomic():
        test.items.all().delete()
        order = 0
        covered = set()
        # Keep the test in graph order: items grouped by node, nodes by creation time.
        for node_id in nodes:
            for d in (d for d in drafts if d.node_id == node_id):
                TestItem.objects.create(
                    test=test, node_id=node_id, order=order, kind=d.kind, prompt=d.prompt.strip(),
                    options=d.options if d.kind == "mcq" else [],
                    answer_index=d.answer_index if d.kind == "mcq" else None,
                    rubric=d.rubric if d.kind == "open" else "",
                )
                order += 1
                covered.add(node_id)
            if node_id not in covered:
                TestItem.objects.create(test=test, node_id=node_id, order=order, **fallback_item(nodes[node_id]))
                order += 1
        test.status = Test.Status.DRAFT
        test.save(update_fields=["status"])
        broadcast(classroom.id, "test.generated", {"test_id": test.id, "items": order})


def grade_choice(item, choice):
    return 1.0 if choice == item.answer_index else 0.0


@transaction.atomic
def submit_attempt(test, student, answers):
    """`answers`: {item_id: {"choice": int|None, "text": str}}. MCQ is graded now, open answers by the AI later."""
    attempt = TestAttempt.objects.create(test=test, student=student, submitted_at=timezone.now())
    needs_ai = False
    for item in test.items.all():
        given = answers.get(item.id, {})
        answer = ItemAnswer(attempt=attempt, item=item, choice=given.get("choice"), text=(given.get("text") or "").strip())
        if item.kind == TestItem.Kind.MCQ:
            answer.score = grade_choice(item, answer.choice)
            answer.graded_by = ItemAnswer.GradedBy.AUTO
        elif not answer.text:
            answer.score = 0.0
            answer.feedback = "No answer."
            answer.graded_by = ItemAnswer.GradedBy.AUTO
        else:
            needs_ai = True
        answer.save()
    attempt.recompute_score()
    attempt.save(update_fields=["score"])
    if needs_ai:
        from .tasks import grade_attempt_task

        transaction.on_commit(lambda: grade_attempt_task.delay(attempt.id))
    return attempt


def grade_attempt(attempt_id):
    attempt = TestAttempt.objects.select_related("test__classroom").get(id=attempt_id)
    classroom = attempt.test.classroom
    llm = get_llm()
    for answer in attempt.answers.select_related("item").filter(score__isnull=True):
        try:
            grade = llm.grade_open(answer.item.prompt, answer.item.rubric, answer.text, classroom.language)
        except LLMError as exc:
            log.warning("Grading answer %s failed: %s", answer.id, exc)
            continue  # stays ungraded; staff can grade it by hand
        answer.score = min(1.0, max(0.0, grade.score))
        answer.feedback = grade.feedback
        answer.graded_by = ItemAnswer.GradedBy.AI
        answer.save(update_fields=["score", "feedback", "graded_by"])
    attempt.recompute_score()
    attempt.save(update_fields=["score"])
    send_to_user(attempt.student_id, classroom.id, "test.graded", {"attempt_id": attempt.id, "score": attempt.score})
    broadcast(classroom.id, "metrics.changed", {})


def override_grade(answer, score, feedback, role):
    answer.score = min(1.0, max(0.0, score))
    if feedback is not None:
        answer.feedback = feedback
    answer.graded_by = role
    answer.save(update_fields=["score", "feedback", "graded_by"])
    attempt = answer.attempt
    attempt.recompute_score()
    attempt.save(update_fields=["score"])
    return answer
