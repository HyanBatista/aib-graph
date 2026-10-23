"""Book → index → knowledge graph."""

import logging

from django.db import transaction
from pypdf import PdfReader

from classes.models import Classroom
from graph.realtime import broadcast
from llm.client import LLMError, get_llm

from .models import Book, IndexTopic, TopicRelation

log = logging.getLogger(__name__)


def read_pages(path):
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def set_status(classroom, status, detail=""):
    classroom.status = status
    classroom.status_detail = detail
    classroom.save(update_fields=["status", "status_detail"])
    broadcast(classroom.id, "class.status", {"status": status, "detail": detail})


@transaction.atomic
def save_index(book, topics):
    """Replace the book index with `topics` (list of dicts shaped like `llm.schemas.TopicDraft`)."""
    book.topics.all().delete()
    last = max(book.page_count, 1)

    def clamp(n):
        return min(max(int(n or 1), 1), last)

    order = 0
    for t in topics:
        parent = IndexTopic.objects.create(
            book=book, order=order, level=0, title=t["title"].strip()[:300], summary=t.get("summary", ""),
            page_start=clamp(t.get("page_start")), page_end=clamp(t.get("page_end") or t.get("page_start")),
        )
        order += 1
        for s in t.get("subtopics", []):
            IndexTopic.objects.create(
                book=book, parent=parent, order=order, level=1, title=s["title"].strip()[:300],
                summary=s.get("summary", ""), page_start=clamp(s.get("page_start")),
                page_end=clamp(s.get("page_end") or s.get("page_start")),
            )
            order += 1


def ingest_book(classroom_id):
    classroom = Classroom.objects.get(id=classroom_id)
    book = classroom.book
    try:
        book.pages_text = read_pages(book.pdf_file.path)
    except Exception as exc:
        log.exception("Could not read PDF")
        set_status(classroom, Classroom.Status.DRAFT, f"Could not read the PDF: {exc}")
        return
    book.page_count = len(book.pages_text)
    book.save(update_fields=["pages_text", "page_count"])
    broadcast(classroom.id, "job.progress", {"job": "index", "message": f"Read {book.page_count} pages"})

    llm = get_llm()
    try:
        book.gemini_file_uri = llm.upload_pdf(book.pdf_file.path) or ""
        book.save(update_fields=["gemini_file_uri"])
        draft = llm.extract_index(book.pdf_file.path, book.pages_text, file_uri=book.gemini_file_uri or None)
    except LLMError as exc:
        set_status(classroom, Classroom.Status.DRAFT, f"Index extraction failed: {exc}")
        return
    if not draft.topics:
        set_status(classroom, Classroom.Status.DRAFT, "The AI could not find any topic in this book")
        return

    save_index(book, [t.model_dump() for t in draft.topics])
    book.title = draft.book_title[:300]
    book.save(update_fields=["title"])
    if draft.language:
        classroom.language = draft.language[:8]
        classroom.save(update_fields=["language"])
    set_status(classroom, Classroom.Status.REVIEW)
    broadcast(classroom.id, "index.ready", {"topics": book.topics.count()})


def topics_payload(book):
    return [
        {"id": t.id, "title": t.title, "summary": t.summary, "level": t.level, "parent_id": t.parent_id}
        for t in book.topics.all()
    ]


def acyclic_prerequisites(pairs, order):
    """Drop prerequisite pairs that would close a cycle. Forward edges (src earlier in the book) win."""
    kept = []
    adjacency = {}

    def reaches(a, b):
        stack, seen = [a], set()
        while stack:
            n = stack.pop()
            if n == b:
                return True
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adjacency.get(n, ()))
        return False

    for src, dst in sorted(pairs, key=lambda p: (order[p[0]] > order[p[1]], order[p[1]], order[p[0]])):
        if src == dst or reaches(dst, src):
            continue
        adjacency.setdefault(src, set()).add(dst)
        kept.append((src, dst))
    return kept


@transaction.atomic
def save_relations(book, relations):
    """Store validated relations: known ids only, no self loops, no prerequisite cycles."""
    topics = {t.id: t for t in book.topics.all()}
    order = {tid: t.order for tid, t in topics.items()}
    TopicRelation.objects.filter(src__book=book).delete()

    prereqs = {(r["src"], r["dst"]) for r in relations if r["kind"] == "prerequisite" and r["src"] in topics and r["dst"] in topics}
    related = {
        tuple(sorted((r["src"], r["dst"])))
        for r in relations
        if r["kind"] == "related" and r["src"] in topics and r["dst"] in topics and r["src"] != r["dst"]
    }
    kept = acyclic_prerequisites(prereqs, order)
    TopicRelation.objects.bulk_create(
        [TopicRelation(src_id=s, dst_id=d, kind=TopicRelation.Kind.PREREQUISITE) for s, d in kept]
        + [TopicRelation(src_id=s, dst_id=d, kind=TopicRelation.Kind.RELATED) for s, d in related if (s, d) not in kept and (d, s) not in kept]
    )
    return len(kept), len(related)


def build_graph(classroom_id):
    """After the professor approves the index: knowledge graph, then the first node."""
    from graph.services import create_node_for_topic, root_topic

    classroom = Classroom.objects.get(id=classroom_id)
    book = classroom.book
    try:
        draft = get_llm().build_relations(topics_payload(book))
    except LLMError as exc:
        set_status(classroom, Classroom.Status.REVIEW, f"Knowledge graph failed: {exc}")
        return
    save_relations(book, [r.model_dump() for r in draft.relations])
    broadcast(classroom.id, "job.progress", {"job": "graph", "message": "Knowledge graph ready"})

    with transaction.atomic():
        set_status(classroom, Classroom.Status.GROWING)
        create_node_for_topic(classroom, root_topic(book))


__all__ = ["Book", "build_graph", "ingest_book", "save_index", "save_relations"]
