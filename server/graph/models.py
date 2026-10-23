from django.conf import settings
from django.db import models

from books.models import IndexTopic
from classes.models import Classroom


class GraphNode(models.Model):
    """A topic of the index materialized as a learning activity: a lesson plus a quiz."""

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="nodes")
    topic = models.ForeignKey(IndexTopic, on_delete=models.CASCADE, related_name="nodes")
    lesson_md = models.TextField(blank=True)
    # [{"prompt": str, "options": [str], "answer": int, "feedback": str}]
    quiz = models.JSONField(default=list, blank=True)
    ready = models.BooleanField(default=False)  # False while the content is being generated
    created_by_question = models.ForeignKey(
        "StudentQuestion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["classroom", "topic"], name="one_node_per_topic")]

    def __str__(self):
        return self.topic.title


class GraphEdge(models.Model):
    class Kind(models.TextChoices):
        GROWTH = "growth"  # the edge along which the destination node was created
        LINK = "link"  # a later question connected two existing nodes

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="edges")
    src = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="outgoing")
    dst = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="incoming")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.GROWTH)
    origin_question = models.ForeignKey(
        "StudentQuestion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["src", "dst"], name="unique_edge")]


class NodeProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress")
    node = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="progress")
    opened_at = models.DateTimeField(auto_now_add=True)
    quiz_score = models.FloatField(null=True, blank=True)  # 0..1
    quiz_answers = models.JSONField(default=list, blank=True)
    quiz_submitted_at = models.DateTimeField(null=True, blank=True)
    question_done = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "node"], name="unique_progress")]

    def refresh_completion(self, now):
        if self.completed_at is None and self.quiz_score is not None and self.question_done:
            self.completed_at = now


class StudentQuestion(models.Model):
    class Outcome(models.TextChoices):
        PENDING = "pending"
        CREATED_NODE = "created_node"
        LINKED_EXISTING = "linked_existing"
        ANSWERED_ONLY = "answered_only"
        FAILED = "failed"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="questions")
    node = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    answer_md = models.TextField(blank=True)
    resolved_topic = models.ForeignKey(IndexTopic, null=True, blank=True, on_delete=models.SET_NULL)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.PENDING)
    target_node = models.ForeignKey(GraphNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            # One question per student and node; a failed one can be asked again.
            models.UniqueConstraint(
                fields=["student", "node"], condition=~models.Q(outcome="failed"), name="one_question_per_node"
            )
        ]
