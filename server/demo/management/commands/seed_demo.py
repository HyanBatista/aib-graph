"""Seed demo users and three classes, one per lifecycle stage. Needs no LLM key.

    uv run python manage.py seed_demo [--reset]
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assessment.models import ItemAnswer, Test, TestAttempt, TestItem
from books.models import Book
from books.services import read_pages, save_index, save_relations
from classes.models import Classroom, Membership
from demo.course import SAMPLE_PDF, chapter_quiz, index_payload, layout, lesson_md, load_course, prerequisites
from graph.models import GraphEdge, GraphNode, NodeProgress, StudentQuestion
from graph.services import AVAILABLE, topic_states
from llm.client import FakeLLM

DEMO_PASSWORD = "demo1234"
DEMO_DOMAIN = "@demo.local"

STAFF = [
    ("prof@demo.local", "Prof. Marina Costa", Membership.Role.PROFESSOR),
    ("ta1@demo.local", "Rafael Lima (TA)", Membership.Role.ASSISTANT),
    ("ta2@demo.local", "Júlia Souza (TA)", Membership.Role.ASSISTANT),
]
# email, name, skill (probability of answering a question right)
STUDENTS = [
    ("ana@demo.local", "Ana Silva", 0.92),
    ("bruno@demo.local", "Bruno Santos", 0.76),
    ("carla@demo.local", "Carla Oliveira", 0.64),
    ("diego@demo.local", "Diego Pereira", 0.52),
    ("elisa@demo.local", "Elisa Rocha", 0.84),
    ("felipe@demo.local", "Felipe Alves", 0.4),
]

# Discovery order of the Live class. It stops before "Hash Tables", "Merge Sort" and
# "Graph Algorithms", which stay available so a live question can create them.
LIVE_ORDER = [
    "Foundations of Algorithms", "What Is an Algorithm", "Asymptotic Analysis", "Pseudocode and Correctness",
    "Big-O Notation", "Loop Invariants", "Big-Omega and Big-Theta", "Sorting", "Analyzing Loops and Recursion",
    "Insertion Sort", "Data Structures", "Stacks and Queues",
]

OFF_TOPIC_QUESTIONS = [
    "Will this be on the exam?",
    "Is there a video that explains this?",
    "Which programming language is best for this?",
]

User = get_user_model()


def stamp(obj, **fields):
    """Overwrite auto_now_add timestamps so the demo has a history."""
    type(obj).objects.filter(pk=obj.pk).update(**fields)
    for k, v in fields.items():
        setattr(obj, k, v)


class Command(BaseCommand):
    help = "Create demo users and classes (Review, Live, Frozen) from demo/fixtures."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, reset=False, **options):
        if reset:
            Classroom.objects.filter(is_demo=True).delete()
            User.objects.filter(email__endswith=DEMO_DOMAIN).delete()
            self.stdout.write("Removed previous demo data.")

        users = self.ensure_users()
        if Classroom.objects.filter(is_demo=True).exists():
            self.stdout.write(self.style.WARNING("Demo classes already exist; users refreshed. Use --reset to rebuild."))
        else:
            self.rng = random.Random(42)
            self.now = timezone.now().replace(microsecond=0)
            with transaction.atomic():
                self.seed_review(users)
                self.seed_live(users)
                self.seed_frozen(users)
            self.stdout.write(self.style.SUCCESS("Demo classes created."))
        self.print_accounts()

    # --- users and classes ---------------------------------------------------

    def ensure_users(self):
        users = {}
        for email, name, *_ in STAFF + STUDENTS:
            user, _ = User.objects.get_or_create(email=email, defaults={"full_name": name})
            user.full_name = name
            user.set_password(DEMO_PASSWORD)
            user.save()
            users[email] = user
        return users

    def make_class(self, users, name, status):
        prof = users[STAFF[0][0]]
        classroom = Classroom.objects.create(name=name, professor=prof, status=status, is_demo=True, language="en")
        for email, _, role in STAFF:
            Membership.objects.create(user=users[email], classroom=classroom, role=role)
        for email, *_ in STUDENTS:
            Membership.objects.create(user=users[email], classroom=classroom, role=Membership.Role.STUDENT)
        with SAMPLE_PDF.open("rb") as fh:
            book = Book(classroom=classroom, title=load_course()["book_title"])
            book.pdf_file.save("sample_book.pdf", File(fh), save=False)
        book.pages_text = read_pages(SAMPLE_PDF)
        book.page_count = len(book.pages_text)
        book.save()
        save_index(book, index_payload())
        return classroom

    def add_relations(self, classroom):
        ids = {t.title: t.id for t in classroom.book.topics.all()}
        save_relations(
            classroom.book,
            [{"src": ids[a], "dst": ids[b], "kind": "prerequisite"} for a, b in prerequisites()],
        )

    def seed_review(self, users):
        self.make_class(users, "Intro to Algorithms — Review", Classroom.Status.REVIEW)

    def seed_live(self, users):
        classroom = self.make_class(users, "Intro to Algorithms — Live", Classroom.Status.GROWING)
        self.add_relations(classroom)
        self.grow(classroom, users, LIVE_ORDER, days=14, visit_rate=0.7)

    def seed_frozen(self, users):
        classroom = self.make_class(users, "Intro to Algorithms — Frozen", Classroom.Status.GROWING)
        self.add_relations(classroom)
        self.grow(classroom, users, self.full_order(classroom), days=30, visit_rate=1.0)
        classroom.status = Classroom.Status.FROZEN
        classroom.frozen_at = self.now - timedelta(days=3)
        classroom.save(update_fields=["status", "frozen_at"])
        self.make_test(classroom, users)

    def full_order(self, classroom):
        """Every topic, in an order that respects prerequisites, shuffled among available ones."""
        reading = [t["title"] for t in layout()]
        requires = {}
        for a, b in prerequisites():
            requires.setdefault(b, set()).add(a)
        order, done = [], set()
        while len(order) < len(reading):
            available = [t for t in reading if t not in done and requires.get(t, set()) <= done]
            pick = available[0] if not order else self.rng.choice(available[:3])
            order.append(pick)
            done.add(pick)
        return order

    # --- graph growth --------------------------------------------------------

    def grow(self, classroom, users, order, days, visit_rate):
        topics = {t.title: t for t in classroom.book.topics.all()}
        fixture = {t["title"]: t for t in layout()}
        chapters = {c["title"]: c for c in load_course()["chapters"]}
        requires = {}
        for a, b in prerequisites():
            requires.setdefault(b, []).append(a)
        students = [users[email] for email, *_ in STUDENTS]
        skill = {users[email].id: s for email, _, s in STUDENTS}
        start = self.now - timedelta(days=days)
        step = timedelta(days=days) / (len(order) + 1)
        nodes = {}

        for k, title in enumerate(order):
            topic = topics[title]
            state = topic_states(classroom)[topic.id]
            assert state == AVAILABLE, f"{title} is {state} when the seed creates it"
            data = fixture[title]
            created_at = start + step * k + timedelta(hours=self.rng.randint(0, 10))
            quiz = data["quiz"] if "quiz" in data else chapter_quiz(chapters[title])
            node = GraphNode.objects.create(classroom=classroom, topic=topic, lesson_md=lesson_md(data), quiz=quiz, ready=True)
            stamp(node, created_at=created_at)

            parent = next((nodes[p] for p in reversed(requires.get(title, [])) if p in nodes), None)
            if parent is not None:
                # One question per student and node, as in the real app.
                asked = set(parent.questions.values_list("student_id", flat=True))
                askers = [s for s in students if s.id not in asked]
                q = None
                if askers:
                    q = self.ask(self.rng.choice(askers), parent, data["question"], StudentQuestion.Outcome.CREATED_NODE,
                                 topic, node, created_at - timedelta(minutes=self.rng.randint(1, 30)))
                    stamp(node, created_by_question=q)
                edge = GraphEdge.objects.create(classroom=classroom, src=parent, dst=node, origin_question=q)
                stamp(edge, created_at=created_at)
            nodes[title] = node

        # Students study the nodes that existed during the period.
        for node in nodes.values():
            for student in students:
                if self.rng.random() > visit_rate:
                    continue
                opened = node.created_at + timedelta(hours=self.rng.randint(1, 72))
                if opened > self.now:
                    opened = self.now - timedelta(minutes=self.rng.randint(5, 600))
                self.study(student, node, skill[student.id], opened, topics, nodes)

        for node in nodes.values():
            for student in students:
                p = NodeProgress.objects.filter(student=student, node=node).first()
                if p and p.quiz_score is not None and p.question_done:
                    p.completed_at = max(p.quiz_submitted_at, p.opened_at)
                    p.save(update_fields=["completed_at"])

    def ask(self, student, node, text, outcome, topic, target, created_at):
        answer = f"Good question! This is covered in **{target.topic.title}**." if target else (
            "That goes beyond this book, but ask your professor in class."
        )
        q = StudentQuestion.objects.create(
            student=student, node=node, text=text, answer_md=answer, outcome=outcome,
            resolved_topic=topic, target_node=target,
        )
        stamp(q, created_at=created_at)
        progress, _ = NodeProgress.objects.get_or_create(student=student, node=node)
        if not progress.question_done:
            progress.question_done = True
            progress.save(update_fields=["question_done"])
        return q

    def study(self, student, node, skill, opened, topics, nodes):
        progress, _ = NodeProgress.objects.get_or_create(student=student, node=node)
        stamp(progress, opened_at=opened)
        level_penalty = 0.04 * [c["title"] for c in load_course()["chapters"]].index(
            node.topic.parent.title if node.topic.parent else node.topic.title
        )
        if self.rng.random() < 0.9:
            answers = []
            for q in node.quiz:
                right = self.rng.random() < max(0.1, skill - level_penalty)
                wrong = [i for i in range(len(q["options"])) if i != q["answer_index"]]
                answers.append(q["answer_index"] if right else self.rng.choice(wrong))
            progress.quiz_answers = answers
            progress.quiz_score = sum(a == q["answer_index"] for a, q in zip(answers, node.quiz)) / len(node.quiz)
            progress.quiz_submitted_at = opened + timedelta(minutes=self.rng.randint(5, 40))
            progress.save(update_fields=["quiz_answers", "quiz_score", "quiz_submitted_at"])

        already_asked = StudentQuestion.objects.filter(student=student, node=node).exists()
        if already_asked or self.rng.random() > 0.8:
            return
        asked_at = opened + timedelta(minutes=self.rng.randint(10, 60))
        covered = [n for n in nodes.values() if n.id != node.id and n.created_at <= asked_at]
        if covered and self.rng.random() < 0.35:
            target = self.rng.choice(covered)
            fixture = {t["title"]: t for t in layout()}
            text = fixture[target.topic.title]["question"]
            self.ask(student, node, text, StudentQuestion.Outcome.LINKED_EXISTING, target.topic, target, asked_at)
            GraphEdge.objects.get_or_create(
                src=node, dst=target, defaults={"classroom": node.classroom, "kind": GraphEdge.Kind.LINK}
            )
        else:
            self.ask(student, node, self.rng.choice(OFF_TOPIC_QUESTIONS), StudentQuestion.Outcome.ANSWERED_ONLY,
                     None, None, asked_at)

    # --- final test ----------------------------------------------------------

    def make_test(self, classroom, users):
        chapters = {c["title"]: c for c in load_course()["chapters"]}
        test = Test.objects.create(classroom=classroom, title=f"{classroom.name} — final test",
                                   status=Test.Status.PUBLISHED, published_at=self.now - timedelta(days=2))
        order = 0
        for node in classroom.nodes.select_related("topic").order_by("created_at"):
            q = node.quiz[-1]
            TestItem.objects.create(test=test, node=node, order=order, kind=TestItem.Kind.MCQ, prompt=q["prompt"],
                                    options=q["options"], answer_index=q["answer_index"])
            order += 1
            if node.topic.title in chapters:
                item = chapters[node.topic.title]["open_item"]
                TestItem.objects.create(test=test, node=node, order=order, kind=TestItem.Kind.OPEN, prompt=item["prompt"],
                                        rubric=item["rubric"], points=2)
                order += 1

        fake = FakeLLM()
        for email, _, skill in STUDENTS:
            student = users[email]
            attempt = TestAttempt.objects.create(test=test, student=student,
                                                 submitted_at=self.now - timedelta(days=1, hours=self.rng.randint(0, 20)))
            for item in test.items.all():
                if item.kind == TestItem.Kind.MCQ:
                    right = self.rng.random() < skill
                    wrong = [i for i in range(len(item.options)) if i != item.answer_index]
                    choice = item.answer_index if right else self.rng.choice(wrong)
                    ItemAnswer.objects.create(attempt=attempt, item=item, choice=choice, score=float(right),
                                              graded_by=ItemAnswer.GradedBy.AUTO)
                else:
                    words = item.rubric.split()
                    keep = max(4, int(len(words) * skill * self.rng.uniform(0.6, 1.0)))
                    text = " ".join(words[:keep])
                    grade = fake.grade_open(item.prompt, item.rubric, text, "en")
                    ItemAnswer.objects.create(attempt=attempt, item=item, text=text, score=grade.score,
                                              feedback=grade.feedback, graded_by=ItemAnswer.GradedBy.AI)
            attempt.recompute_score()
            attempt.save(update_fields=["score"])

        # One answer reviewed by an assistant, to show grade overrides.
        diego = users["diego@demo.local"]
        answer = ItemAnswer.objects.filter(attempt__student=diego, attempt__test=test, item__kind=TestItem.Kind.OPEN).first()
        if answer:
            answer.score = 0.8
            answer.feedback = "Reviewed by TA: the idea is right, but give an example next time."
            answer.graded_by = ItemAnswer.GradedBy.ASSISTANT
            answer.save()
            answer.attempt.recompute_score()
            answer.attempt.save(update_fields=["score"])

    def print_accounts(self):
        self.stdout.write("\nDemo accounts (password: %s)" % DEMO_PASSWORD)
        for email, name, role in STAFF:
            self.stdout.write(f"  {role:<10} {email:<22} {name}")
        for email, name, _ in STUDENTS:
            self.stdout.write(f"  {'student':<10} {email:<22} {name}")

