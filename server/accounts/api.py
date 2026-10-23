from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from ninja import Router, Schema, Status
from ninja.errors import HttpError
from ninja.security import HttpBearer

from .tokens import issue_tokens, user_from_token

User = get_user_model()


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        user = user_from_token(token)
        if user:
            request.user = user
        return user


router = Router(tags=["auth"])


class UserOut(Schema):
    id: int
    email: str
    full_name: str


class TokensOut(Schema):
    access: str
    refresh: str
    user: UserOut


class RegisterIn(Schema):
    email: str
    password: str
    full_name: str = ""


class LoginIn(Schema):
    email: str
    password: str


class RefreshIn(Schema):
    refresh: str


@router.post("/register", response={201: TokensOut})
def register(request, data: RegisterIn):
    email = data.email.strip().lower()
    if User.objects.filter(email=email).exists():
        raise HttpError(409, "An account with this email already exists")
    try:
        validate_password(data.password)
    except ValidationError as exc:
        raise HttpError(400, " ".join(exc.messages))
    user = User.objects.create_user(email=email, password=data.password, full_name=data.full_name.strip())
    return Status(201, {**issue_tokens(user), "user": user})


@router.post("/login", response=TokensOut)
def login(request, data: LoginIn):
    user = authenticate(request, email=data.email.strip().lower(), password=data.password)
    if user is None:
        raise HttpError(401, "Invalid email or password")
    return {**issue_tokens(user), "user": user}


@router.post("/refresh", response=TokensOut)
def refresh(request, data: RefreshIn):
    user = user_from_token(data.refresh, kind="refresh")
    if user is None:
        raise HttpError(401, "Invalid or expired refresh token")
    return {**issue_tokens(user), "user": user}


@router.get("/me", response=UserOut, auth=JWTAuth())
def me(request):
    return request.auth
