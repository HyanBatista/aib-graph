from django.contrib.auth import get_user_model
from ninja import Router
from ninja.errors import HttpError

from classes.models import Membership
from classes.permissions import STAFF, get_membership, require_role

from .services import class_metrics, student_metrics

router = Router(tags=["metrics"])


@router.get("/{class_id}/metrics")
def class_dashboard(request, class_id: int):
    membership = require_role(get_membership(request.auth, class_id), *STAFF)
    return class_metrics(membership.classroom)


@router.get("/{class_id}/metrics/students/{user_id}")
def student_dashboard(request, class_id: int, user_id: int):
    membership = get_membership(request.auth, class_id)
    if membership.role not in STAFF and user_id != request.auth.id:
        raise HttpError(403, "You can only see your own dashboard")
    if not Membership.objects.filter(classroom_id=class_id, user_id=user_id, role=Membership.Role.STUDENT).exists():
        raise HttpError(404, "Student not found in this class")
    return student_metrics(membership.classroom, get_user_model().objects.get(id=user_id))
