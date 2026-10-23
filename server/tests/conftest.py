import json

import pytest
from django.test import Client

from accounts.models import User
from classes.models import Classroom, Membership
from config.celery import app as celery_app
from demo.course import SAMPLE_PDF


@pytest.fixture(autouse=True)
def offline_llm(settings, tmp_path):
    settings.LLM_PROVIDER = "fake"
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


class Api:
    """Thin JSON client: api.post(url, data) -> (status, body)."""

    def __init__(self, user=None):
        self.client = Client()
        self.headers = {}
        if user is not None:
            from accounts.tokens import issue_tokens

            self.headers["HTTP_AUTHORIZATION"] = f"Bearer {issue_tokens(user)['access']}"

    def _do(self, method, url, data=None, **extra):
        kwargs = {**self.headers, **extra}
        if data is not None and "content_type" not in kwargs:
            kwargs["content_type"] = "application/json"
            data = json.dumps(data)
        response = getattr(self.client, method)(f"/api{url}", data, **kwargs) if data is not None else getattr(self.client, method)(f"/api{url}", **kwargs)
        body = response.json() if response.get("Content-Type", "").startswith("application/json") and response.content else None
        return response.status_code, body

    def get(self, url, **kw):
        return self._do("get", url, **kw)

    def post(self, url, data=None, **kw):
        return self._do("post", url, data if data is not None else {}, **kw)

    def put(self, url, data, **kw):
        return self._do("put", url, data, **kw)

    def patch(self, url, data, **kw):
        return self._do("patch", url, data, **kw)

    def delete(self, url, **kw):
        return self._do("delete", url, **kw)

    def upload(self, url, path):
        with open(path, "rb") as fh:
            response = self.client.post(f"/api{url}", {"file": fh}, **self.headers)
        return response.status_code, response.json()


@pytest.fixture
def make_user(db):
    def make(email, name=""):
        return User.objects.create_user(email=email, password="password123", full_name=name)

    return make


@pytest.fixture
def api():
    return Api


@pytest.fixture
def people(make_user):
    return {
        "prof": make_user("prof@x.test", "Prof"),
        "ta": make_user("ta@x.test", "TA"),
        "s1": make_user("s1@x.test", "Student One"),
        "s2": make_user("s2@x.test", "Student Two"),
        "outsider": make_user("out@x.test", "Outsider"),
    }


def build_class(people, api):
    """Create a class through the API: upload the sample book, approve the index. Returns its id."""
    prof = api(people["prof"])
    status, body = prof.post("/classes", {"name": "Algorithms"})
    assert status == 201, body
    class_id = body["id"]
    status, body = prof.upload(f"/classes/{class_id}/book", SAMPLE_PDF)
    assert status == 200, body
    assert Classroom.objects.get(id=class_id).status == Classroom.Status.REVIEW
    status, body = prof.post(f"/classes/{class_id}/index/approve")
    assert status == 200, body
    classroom = Classroom.objects.get(id=class_id)
    for key, role in (("ta", Membership.Role.ASSISTANT), ("s1", Membership.Role.STUDENT), ("s2", Membership.Role.STUDENT)):
        Membership.objects.create(user=people[key], classroom=classroom, role=role)
    return class_id


@pytest.fixture
def growing_class(people, api, transactional_db):
    return build_class(people, api)
