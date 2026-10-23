from django.conf import settings
from django.db import models

from classes.models import Classroom
from graph.models import GraphNode


class Test(models.Model):
    class Status(models.TextChoices):
        GENERATING = "generating"
        DRAFT = "draft"
        PUBLISHED = "published"
        CLOSED = "closed"

    classroom = models.OneToOneField(Classroom, on_delete=models.CASCADE, related_name="test")
    title = models.CharField(max_length=300)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.GENERATING)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)


class TestItem(models.Model):
    class Kind(models.TextChoices):
        MCQ = "mcq"
        OPEN = "open"

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="items")
    node = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="test_items")
    order = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    prompt = models.TextField()
    options = models.JSONField(default=list, blank=True)
    answer_index = models.IntegerField(null=True, blank=True)  # mcq
    rubric = models.TextField(blank=True)  # open
    points = models.FloatField(default=1)

    class Meta:
        ordering = ["order", "id"]


class TestAttempt(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="test_attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)  # 0..1, set once every answer is graded

    class Meta:
        constraints = [models.UniqueConstraint(fields=["test", "student"], name="one_attempt_per_student")]

    def recompute_score(self):
        answers = list(self.answers.select_related("item"))
        if not answers or any(a.score is None for a in answers):
            self.score = None
            return
        total = sum(a.item.points for a in answers)
        self.score = sum(a.score * a.item.points for a in answers) / total if total else 0


class ItemAnswer(models.Model):
    class GradedBy(models.TextChoices):
        AUTO = "auto"
        AI = "ai"
        ASSISTANT = "assistant"
        PROFESSOR = "professor"

    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name="answers")
    item = models.ForeignKey(TestItem, on_delete=models.CASCADE, related_name="answers")
    choice = models.IntegerField(null=True, blank=True)
    text = models.TextField(blank=True)
    score = models.FloatField(null=True, blank=True)  # 0..1
    feedback = models.TextField(blank=True)
    graded_by = models.CharField(max_length=16, choices=GradedBy.choices, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "item"], name="one_answer_per_item")]
