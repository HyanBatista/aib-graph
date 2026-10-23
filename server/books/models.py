from django.db import models

from classes.models import Classroom


class Book(models.Model):
    classroom = models.OneToOneField(Classroom, on_delete=models.CASCADE, related_name="book")
    title = models.CharField(max_length=300, blank=True)
    pdf_file = models.FileField(upload_to="books/")
    page_count = models.PositiveIntegerField(default=0)
    # Text of each page, used to ground prompts and to show source pages.
    pages_text = models.JSONField(default=list, blank=True)
    gemini_file_uri = models.CharField(max_length=500, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def text_for_pages(self, start, end, limit=60_000):
        start = max(start, 1)
        end = min(end or start, len(self.pages_text))
        chunks = [f"[page {n}]\n{self.pages_text[n - 1]}" for n in range(start, end + 1)]
        return "\n\n".join(chunks)[:limit]


class IndexTopic(models.Model):
    """One entry of the book index. Each topic (inner or leaf) becomes one graph node."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="topics")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    order = models.PositiveIntegerField(default=0)  # global reading order across the whole index
    level = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True)
    page_start = models.PositiveIntegerField(default=1)
    page_end = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class TopicRelation(models.Model):
    """Edge of the knowledge graph extracted from the book."""

    class Kind(models.TextChoices):
        PREREQUISITE = "prerequisite"  # src must be learned before dst
        RELATED = "related"

    src = models.ForeignKey(IndexTopic, on_delete=models.CASCADE, related_name="outgoing")
    dst = models.ForeignKey(IndexTopic, on_delete=models.CASCADE, related_name="incoming")
    kind = models.CharField(max_length=16, choices=Kind.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["src", "dst", "kind"], name="unique_topic_relation")]
