import secrets

from django.conf import settings
from django.db import models


def new_invite_code():
    return secrets.token_hex(3).upper()


class Classroom(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"  # created, no book yet
        INDEXING = "indexing"  # book uploaded, index being extracted
        REVIEW = "review"  # index ready, waiting for professor approval
        BUILDING = "building"  # knowledge graph + first node being generated
        GROWING = "growing"  # students are growing the graph
        COMPLETE = "complete"  # every index topic has a node
        FROZEN = "frozen"  # professor froze the graph

    name = models.CharField(max_length=200)
    professor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_classes")
    language = models.CharField(max_length=8, default="en")  # language of the book and generated content
    invite_code = models.CharField(max_length=12, unique=True, default=new_invite_code)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    status_detail = models.CharField(max_length=500, blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    frozen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        PROFESSOR = "professor"
        ASSISTANT = "assistant"
        STUDENT = "student"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "classroom"], name="unique_membership")]

    @property
    def is_staff_role(self):
        return self.role in (self.Role.PROFESSOR, self.Role.ASSISTANT)
