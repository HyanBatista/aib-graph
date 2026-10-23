from ninja.errors import HttpError

from .models import Classroom, Membership

STAFF = (Membership.Role.PROFESSOR, Membership.Role.ASSISTANT)


def get_membership(user, class_id):
    """The user's membership in the class; 404 if the class doesn't exist or the user isn't in it."""
    membership = (
        Membership.objects.select_related("classroom").filter(user=user, classroom_id=class_id).first()
    )
    if membership is None:
        raise HttpError(404, "Class not found")
    return membership


def require_role(membership, *roles):
    if membership.role not in roles:
        raise HttpError(403, "You don't have permission to do this in this class")
    return membership


def require_status(classroom, *statuses):
    if classroom.status not in statuses:
        raise HttpError(409, f"Not allowed while the class is '{classroom.status}'")
    return classroom


__all__ = ["Classroom", "Membership", "STAFF", "get_membership", "require_role", "require_status"]
