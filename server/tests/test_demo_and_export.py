import json
from pathlib import Path

import jsonschema
import pytest
from django.core.management import call_command

from accounts.models import User
from classes.models import Classroom
from graph.egf import export_egf
from graph.models import GraphNode

SCHEMA = json.loads((Path(__file__).parent.parent / "graph" / "egf" / "schema_v1.json").read_text())

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    call_command("seed_demo", stdout=open("/dev/null", "w"))
    return {c.status: c for c in Classroom.objects.filter(is_demo=True)}


def test_seed_is_idempotent(seeded):
    counts = (User.objects.count(), Classroom.objects.count(), GraphNode.objects.count())
    call_command("seed_demo", stdout=open("/dev/null", "w"))
    assert (User.objects.count(), Classroom.objects.count(), GraphNode.objects.count()) == counts
    call_command("seed_demo", "--reset", stdout=open("/dev/null", "w"))
    assert (User.objects.count(), Classroom.objects.count(), GraphNode.objects.count()) == counts


def test_seed_classes_cover_every_stage(seeded):
    assert set(seeded) == {"review", "growing", "frozen"}
    assert seeded["review"].nodes.count() == 0
    assert seeded["growing"].nodes.count() == 12
    assert seeded["frozen"].nodes.count() == 20
    assert seeded["frozen"].test.status == "published"


def test_frozen_demo_metrics_are_populated(seeded, api):
    prof = api(User.objects.get(email="prof@demo.local"))
    frozen = seeded["frozen"]
    status, m = prof.get(f"/classes/{frozen.id}/metrics")
    assert status == 200
    assert m["summary"]["coverage"] == 1.0
    assert m["summary"]["students"] == 6
    assert m["test"]["attempts"] == 6 and m["test"]["avg_score"] is not None
    assert len(m["per_node"]) == 20 and all(n["visits"] for n in m["per_node"])
    assert m["mastery"] and m["growth"] and m["question_outcomes"]

    ana = User.objects.get(email="ana@demo.local")
    status, sm = api(ana).get(f"/classes/{frozen.id}/metrics/students/{ana.id}")
    assert status == 200
    assert sm["summary"]["test_score"] is not None
    assert len(sm["per_node"]) == 20


def test_live_demo_question_grows_the_graph(seeded, api, django_capture_on_commit_callbacks):
    live = seeded["growing"]
    ana = User.objects.get(email="ana@demo.local")
    node = live.nodes.get(topic__title="Stacks and Queues")
    if node.questions.filter(student=ana).exists():
        node = next(n for n in live.nodes.all() if not n.questions.filter(student=ana).exists())
    with django_capture_on_commit_callbacks(execute=True):
        api(ana).post(f"/classes/{live.id}/nodes/{node.id}/question", {"text": "How do hash tables handle collisions?"})
    status, q = api(ana).get(f"/classes/{live.id}/nodes/{node.id}")
    q = q["my_question"]
    assert status == 200 and q["outcome"] == "created_node"
    assert live.nodes.count() == 13
    assert live.nodes.get(topic__title="Hash Tables").ready


def test_egf_export_matches_official_schema(seeded, api):
    frozen = seeded["frozen"]
    egf = export_egf(frozen)
    jsonschema.validate(egf, SCHEMA)
    ids = {n["id"] for n in egf["nodes"]}
    assert egf["info"]["start"] == "sm1"
    assert all(e["from"] in ids and e["to"] in ids for e in egf["edges"])
    assert sum(1 for n in egf["nodes"] if n["type"] == "static-md") == 20

    status, _ = api(User.objects.get(email="ana@demo.local")).get(f"/classes/{frozen.id}/export.egf")
    assert status == 403
    response = api(User.objects.get(email="prof@demo.local")).client.get(
        f"/api/classes/{frozen.id}/export.egf",
        HTTP_AUTHORIZATION=api(User.objects.get(email="prof@demo.local")).headers["HTTP_AUTHORIZATION"],
    )
    assert response.status_code == 200
    assert response["Content-Disposition"].endswith('.egf"')


def test_official_example_validates():
    example = json.loads((Path(__file__).parent / "egf_example_unplugged.egf").read_text())
    jsonschema.validate(example, SCHEMA)
