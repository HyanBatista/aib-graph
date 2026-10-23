"""Aggregates for the dashboards. Classes are small (tens of students, tens of nodes), so this runs in Python."""

from collections import Counter, defaultdict
from statistics import mean, median

from assessment.models import Test, TestAttempt
from classes.models import Membership
from graph.models import GraphNode, NodeProgress, StudentQuestion


def _avg(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def _median(values):
    values = [v for v in values if v is not None]
    return round(median(values), 4) if values else None


def _student_name(user):
    return user.full_name or user.email


def class_metrics(classroom):
    students = [m.user for m in Membership.objects.filter(classroom=classroom, role=Membership.Role.STUDENT).select_related("user")]
    student_ids = {s.id for s in students}
    nodes = list(GraphNode.objects.filter(classroom=classroom).select_related("topic"))
    progress = [p for p in NodeProgress.objects.filter(node__classroom=classroom) if p.student_id in student_ids]
    questions = [q for q in StudentQuestion.objects.filter(node__classroom=classroom) if q.student_id in student_ids]
    test = Test.objects.filter(classroom=classroom).first()
    attempts = list(TestAttempt.objects.filter(test=test)) if test else []
    total_topics = classroom.book.topics.count() if hasattr(classroom, "book") else 0

    by_node = defaultdict(list)
    for p in progress:
        by_node[p.node_id].append(p)
    q_by_node = Counter(q.node_id for q in questions)
    per_node = []
    for n in nodes:
        ps = by_node[n.id]
        per_node.append({
            "node_id": n.id,
            "title": n.topic.title,
            "visits": len(ps),
            "completions": sum(1 for p in ps if p.completed_at),
            "avg_score": _avg([p.quiz_score for p in ps]),
            "median_score": _median([p.quiz_score for p in ps]),
            "questions": q_by_node[n.id],
        })

    growth, count = [], 0
    for day, n_new in sorted(Counter(n.created_at.date() for n in nodes).items()):
        count += n_new
        growth.append({"date": day.isoformat(), "nodes": count})

    attempt_by_student = {a.student_id: a for a in attempts}
    prog_by_student = defaultdict(list)
    for p in progress:
        prog_by_student[p.student_id].append(p)
    q_by_student = defaultdict(list)
    for q in questions:
        q_by_student[q.student_id].append(q)
    participation = []
    for s in students:
        ps, qs = prog_by_student[s.id], q_by_student[s.id]
        attempt = attempt_by_student.get(s.id)
        participation.append({
            "student_id": s.id,
            "name": _student_name(s),
            "visited": len(ps),
            "completed": sum(1 for p in ps if p.completed_at),
            "avg_score": _avg([p.quiz_score for p in ps]),
            "questions": len(qs),
            "nodes_created": sum(1 for q in qs if q.outcome == StudentQuestion.Outcome.CREATED_NODE),
            "test_score": attempt.score if attempt else None,
        })

    test_scores = [a.score for a in attempts if a.score is not None]
    buckets = [0] * 10
    for s in test_scores:
        buckets[min(int(s * 10), 9)] += 1

    return {
        "summary": {
            "students": len(students),
            "nodes": len(nodes),
            "edges": classroom.edges.count(),
            "topics_total": total_topics,
            "coverage": round(len(nodes) / total_topics, 4) if total_topics else 0,
            "avg_quiz": _avg([p.quiz_score for p in progress]),
            "completion_rate": round(
                sum(1 for p in progress if p.completed_at) / (len(students) * len(nodes)), 4
            ) if students and nodes else 0,
            "questions": len(questions),
        },
        "question_outcomes": dict(Counter(q.outcome for q in questions)),
        "growth": growth,
        "per_node": per_node,
        "participation": participation,
        "mastery": [
            {"student_id": p.student_id, "node_id": p.node_id, "score": p.quiz_score}
            for p in progress if p.quiz_score is not None
        ],
        "test": {
            "status": test.status if test else None,
            "attempts": len(attempts),
            "avg_score": _avg(test_scores),
            "median_score": _median(test_scores),
            "distribution": [{"bucket": f"{i * 10}-{i * 10 + 10}%", "count": c} for i, c in enumerate(buckets)],
        },
    }


def student_metrics(classroom, student):
    nodes = list(GraphNode.objects.filter(classroom=classroom).select_related("topic"))
    progress = {p.node_id: p for p in NodeProgress.objects.filter(node__classroom=classroom, student=student)}
    questions = list(StudentQuestion.objects.filter(node__classroom=classroom, student=student).select_related("node__topic", "target_node__topic"))
    test = Test.objects.filter(classroom=classroom).first()
    attempt = TestAttempt.objects.filter(test=test, student=student).first() if test else None

    class_avg = {
        row["node_id"]: row["avg_score"] for row in class_metrics(classroom)["per_node"]
    }
    per_node = []
    for n in nodes:
        p = progress.get(n.id)
        per_node.append({
            "node_id": n.id,
            "title": n.topic.title,
            "state": "completed" if p and p.completed_at else "in_progress" if p else "new",
            "quiz_score": p.quiz_score if p else None,
            "class_avg": class_avg.get(n.id),
            "question_done": bool(p and p.question_done),
        })

    test_by_node = defaultdict(list)
    if attempt:
        for a in attempt.answers.select_related("item"):
            if a.score is not None:
                test_by_node[a.item.node_id].append(a.score)
    # Mastery mixes the node quiz and the final test, when there is one.
    for row in per_node:
        scores = [s for s in [row["quiz_score"], _avg(test_by_node.get(row["node_id"], []))] if s is not None]
        row["mastery"] = _avg(scores)

    ps = list(progress.values())
    return {
        "student": {"id": student.id, "name": _student_name(student), "email": student.email},
        "summary": {
            "nodes_total": len(nodes),
            "visited": len(ps),
            "completed": sum(1 for p in ps if p.completed_at),
            "avg_score": _avg([p.quiz_score for p in ps]),
            "questions": len(questions),
            "nodes_created": sum(1 for q in questions if q.outcome == StudentQuestion.Outcome.CREATED_NODE),
            "test_score": attempt.score if attempt else None,
        },
        "per_node": per_node,
        "questions": [
            {
                "id": q.id, "node_title": q.node.topic.title, "text": q.text, "outcome": q.outcome,
                "target_title": q.target_node.topic.title if q.target_node else None,
                "created_at": q.created_at.isoformat(),
            }
            for q in questions
        ],
    }
