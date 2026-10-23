from django.db import transaction
from ninja import File, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from classes.models import Classroom, Membership
from classes.permissions import get_membership, require_role, require_status
from graph.realtime import broadcast
from graph.services import topic_states

from .models import Book, TopicRelation
from .services import save_index, set_status
from .tasks import build_graph_task, ingest_book_task

router = Router(tags=["books"])
Status = Classroom.Status

MAX_PDF_BYTES = 200 * 1024 * 1024


class SubtopicIn(Schema):
    title: str
    summary: str = ""
    page_start: int = 1
    page_end: int = 1


class TopicIn(SubtopicIn):
    subtopics: list[SubtopicIn] = []


class IndexIn(Schema):
    topics: list[TopicIn]


@router.post("/{class_id}/book")
def upload_book(request, class_id: int, file: File[UploadedFile]):
    membership = require_role(get_membership(request.auth, class_id), Membership.Role.PROFESSOR)
    classroom = require_status(membership.classroom, Status.DRAFT, Status.REVIEW)
    if not (file.name or "").lower().endswith(".pdf"):
        raise HttpError(400, "Please upload a PDF file")
    if file.size > MAX_PDF_BYTES:
        raise HttpError(400, "The PDF is too large (max 200 MB)")
    with transaction.atomic():
        Book.objects.filter(classroom=classroom).delete()
        Book.objects.create(classroom=classroom, pdf_file=file, title=file.name.rsplit(".", 1)[0][:300])
        set_status(classroom, Status.INDEXING, "Reading the book and extracting its index")
        transaction.on_commit(lambda: ingest_book_task.delay(classroom.id))
    classroom.refresh_from_db()
    return {"status": classroom.status, "detail": classroom.status_detail}


@router.get("/{class_id}/book/pages")
def book_pages(request, class_id: int, start: int, end: int):
    membership = get_membership(request.auth, class_id)
    book = Book.objects.filter(classroom=membership.classroom).first()
    if book is None:
        raise HttpError(404, "This class has no book yet")
    end = min(end, start + 9)
    return {
        "page_count": book.page_count,
        "pages": [{"number": n, "text": book.pages_text[n - 1]} for n in range(max(start, 1), min(end, book.page_count) + 1)],
    }


@router.get("/{class_id}/index")
def get_index(request, class_id: int):
    membership = get_membership(request.auth, class_id)
    classroom = membership.classroom
    book = Book.objects.filter(classroom=classroom).first()
    if book is None:
        return {"book_title": None, "page_count": 0, "topics": [], "relations": []}
    has_graph = classroom.status not in (Status.DRAFT, Status.INDEXING, Status.REVIEW, Status.BUILDING)
    states = topic_states(classroom) if has_graph else {}
    nodes = dict(classroom.nodes.values_list("topic_id", "id"))
    topics = [
        {
            "id": t.id, "parent_id": t.parent_id, "level": t.level, "order": t.order, "title": t.title,
            "summary": t.summary, "page_start": t.page_start, "page_end": t.page_end,
            "state": states.get(t.id), "node_id": nodes.get(t.id),
        }
        for t in book.topics.all()
    ]
    relations = [
        {"src": r.src_id, "dst": r.dst_id, "kind": r.kind}
        for r in TopicRelation.objects.filter(src__book=book)
    ]
    return {"book_title": book.title, "page_count": book.page_count, "topics": topics, "relations": relations}


@router.put("/{class_id}/index")
def replace_index(request, class_id: int, data: IndexIn):
    membership = require_role(get_membership(request.auth, class_id), Membership.Role.PROFESSOR)
    classroom = require_status(membership.classroom, Status.REVIEW)
    if not data.topics:
        raise HttpError(400, "The index needs at least one topic")
    save_index(classroom.book, [t.dict() for t in data.topics])
    broadcast(classroom.id, "index.ready", {"topics": classroom.book.topics.count()})
    return get_index(request, class_id)


@router.post("/{class_id}/index/approve")
def approve_index(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), Membership.Role.PROFESSOR)
    classroom = require_status(membership.classroom, Status.REVIEW)
    if not classroom.book.topics.exists():
        raise HttpError(400, "The index is empty")
    with transaction.atomic():
        set_status(classroom, Status.BUILDING, "Building the knowledge graph and the first node")
        transaction.on_commit(lambda: build_graph_task.delay(classroom.id))
    classroom.refresh_from_db()
    return {"status": classroom.status, "detail": classroom.status_detail}
