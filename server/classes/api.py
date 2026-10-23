from django.db import transaction
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from graph.realtime import broadcast
from graph.services import freeze

from .models import Classroom, Membership
from .permissions import STAFF, get_membership, require_role, require_status

router = Router(tags=["classes"])
Role = Membership.Role


class ClassOut(Schema):
    id: int
    name: str
    status: str
    status_detail: str
    language: str
    role: str
    invite_code: str | None
    professor: str
    book_title: str | None
    topics_total: int
    topics_covered: int
    members: int
    frozen_at: str | None


def class_out(membership):
    c = membership.classroom
    book = getattr(c, "book", None)
    return {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "status_detail": c.status_detail,
        "language": c.language,
        "role": membership.role,
        "invite_code": c.invite_code if membership.role in STAFF else None,
        "professor": c.professor.full_name or c.professor.email,
        "book_title": book.title if book else None,
        "topics_total": book.topics.count() if book else 0,
        "topics_covered": c.nodes.count(),
        "members": c.memberships.count(),
        "frozen_at": c.frozen_at.isoformat() if c.frozen_at else None,
    }


class ClassIn(Schema):
    name: str
    language: str = "en"


class JoinIn(Schema):
    invite_code: str


class MemberOut(Schema):
    user_id: int
    email: str
    full_name: str
    role: str


class RoleIn(Schema):
    role: str


@router.get("", response=list[ClassOut])
def list_classes(request):
    memberships = (
        Membership.objects.filter(user=request.auth)
        .select_related("classroom__professor", "classroom__book")
        .order_by("-classroom__created_at")
    )
    return [class_out(m) for m in memberships]


@router.post("", response={201: ClassOut})
def create_class(request, data: ClassIn):
    name = data.name.strip()
    if not name:
        raise HttpError(400, "Name is required")
    with transaction.atomic():
        classroom = Classroom.objects.create(name=name, professor=request.auth, language=data.language or "en")
        membership = Membership.objects.create(user=request.auth, classroom=classroom, role=Role.PROFESSOR)
    return Status(201, class_out(membership))


@router.post("/join", response=ClassOut)
def join_class(request, data: JoinIn):
    classroom = Classroom.objects.filter(invite_code=data.invite_code.strip().upper()).first()
    if classroom is None:
        raise HttpError(404, "No class with this invite code")
    membership, created = Membership.objects.get_or_create(
        user=request.auth, classroom=classroom, defaults={"role": Role.STUDENT}
    )
    if created:
        broadcast(classroom.id, "members.changed", {})
    return class_out(membership)


@router.get("/{class_id}", response=ClassOut)
def get_class(request, class_id: int):
    return class_out(get_membership(request.auth, class_id))


@router.get("/{class_id}/members", response=list[MemberOut])
def list_members(request, class_id: int):
    require_role(get_membership(request.auth, class_id), *STAFF)
    members = Membership.objects.filter(classroom_id=class_id).select_related("user").order_by("role", "user__full_name")
    return [{"user_id": m.user_id, "email": m.user.email, "full_name": m.user.full_name, "role": m.role} for m in members]


@router.patch("/{class_id}/members/{user_id}", response=MemberOut)
def set_member_role(request, class_id: int, user_id: int, data: RoleIn):
    require_role(get_membership(request.auth, class_id), Role.PROFESSOR)
    if data.role not in (Role.ASSISTANT, Role.STUDENT):
        raise HttpError(400, "Role must be 'assistant' or 'student'")
    member = Membership.objects.select_related("user").filter(classroom_id=class_id, user_id=user_id).first()
    if member is None:
        raise HttpError(404, "Member not found")
    if member.role == Role.PROFESSOR:
        raise HttpError(400, "The professor's role can't be changed")
    member.role = data.role
    member.save(update_fields=["role"])
    broadcast(class_id, "members.changed", {})
    return {"user_id": member.user_id, "email": member.user.email, "full_name": member.user.full_name, "role": member.role}


@router.delete("/{class_id}/members/{user_id}", response={204: None})
def remove_member(request, class_id: int, user_id: int):
    require_role(get_membership(request.auth, class_id), Role.PROFESSOR)
    deleted, _ = Membership.objects.filter(classroom_id=class_id, user_id=user_id).exclude(role=Role.PROFESSOR).delete()
    if not deleted:
        raise HttpError(404, "Member not found")
    broadcast(class_id, "members.changed", {})
    return Status(204, None)


@router.post("/{class_id}/freeze", response=ClassOut)
def freeze_class(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), Role.PROFESSOR)
    require_status(membership.classroom, Classroom.Status.GROWING, Classroom.Status.COMPLETE)
    if not freeze(membership.classroom):
        raise HttpError(409, f"Not allowed while the class is '{membership.classroom.status}'")
    return class_out(membership)
