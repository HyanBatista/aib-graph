"""Export a class graph as an Edukors Graph Format (EGF v1) course.

Each graph node becomes a static Markdown node (`smN`) followed by its quiz (`qN`).
EGF players follow one path, so nodes are chained in the order students discovered
them (breadth-first from the first node); the real class graph is kept in
`info.extras["aib-graph"]` so nothing is lost.
"""

import re
import string
import uuid
from collections import deque

from django.utils import timezone

SCHEMA_URL = "https://edukors.org/graph/schema/v1/"
NAMESPACE = uuid.UUID("2b0e5d0a-6f0f-4a59-9c3e-5d7d0a1f6a11")


def text(lang, value):
    return [{"lang": lang, "text": value}]


def discovery_order(nodes, edges):
    children = {}
    for e in edges:
        children.setdefault(e.src_id, []).append(e.dst_id)
    by_id = {n.id: n for n in nodes}
    order, seen = [], set()
    for start in nodes:  # nodes are already sorted by creation time
        if start.id in seen:
            continue
        queue = deque([start.id])
        seen.add(start.id)
        while queue:
            nid = queue.popleft()
            order.append(by_id[nid])
            for child in sorted(children.get(nid, []), key=lambda c: (by_id[c].created_at, c)):
                if child not in seen:
                    seen.add(child)
                    queue.append(child)
    return order


def export_egf(classroom):
    lang = classroom.language if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", classroom.language or "") else "en"
    nodes = list(classroom.nodes.select_related("topic__parent").filter(ready=True).order_by("created_at", "id"))
    edges = list(classroom.edges.filter(src__ready=True, dst__ready=True))
    ordered = discovery_order(nodes, edges)

    top_topics = list(classroom.book.topics.filter(level=0).order_by("order"))
    section_of = {t.id: i + 1 for i, t in enumerate(top_topics)}

    egf_nodes, egf_edges, ids = [], [], {}
    previous = None
    for k, node in enumerate(ordered, start=1):
        topic = node.topic
        section = section_of.get(topic.parent_id or topic.id, 1)
        sm_id, q_id = f"sm{k}", f"q{k}"
        ids[node.id] = sm_id
        egf_nodes.append({
            "id": sm_id,
            "type": "static-md",
            "section": section,
            "position": {"x": 40, "y": (k - 1) * 260},
            "title": text(lang, topic.title),
            "content": {"item": text(lang, node.lesson_md or topic.summary or topic.title)},
        })
        if previous:
            egf_edges.append({"from": previous, "to": sm_id})
        previous = sm_id
        quiz_items = [quiz_item(q, lang) for q in node.quiz if len(q.get("options", [])) >= 2]
        if quiz_items:
            egf_nodes.append({
                "id": q_id,
                "type": "quiz",
                "section": section,
                "position": {"x": 40, "y": (k - 1) * 260 + 130},
                "title": text(lang, f"{topic.title} — quiz"),
                "content": {"items": quiz_items},
            })
            egf_edges.append({"from": sm_id, "to": q_id})
            previous = q_id

    info = {
        "course-id": str(uuid.uuid5(NAMESPACE, f"class-{classroom.id}")),
        "source-language": lang,
        "other-languages": [],
        "title": text(lang, classroom.name),
        "author": classroom.professor.full_name or classroom.professor.email,
        "version": "1.0.0",
        "date": timezone.localdate().isoformat(),
        "start": "sm1",
        "sections": [{"number": i + 1, "title": text(lang, t.title)} for i, t in enumerate(top_topics)],
        "extras": {
            "aib-graph": {
                "class_id": classroom.id,
                "book": classroom.book.title,
                "edges": [[ids[e.src_id], ids[e.dst_id]] for e in edges if e.src_id in ids and e.dst_id in ids],
            }
        },
    }
    if not info["sections"]:
        del info["sections"]
    return {"$schema": SCHEMA_URL, "info": info, "nodes": egf_nodes, "edges": egf_edges}


def quiz_item(q, lang):
    item = {
        "question": text(lang, q["prompt"]),
        "options": [
            {"value": string.ascii_lowercase[i], "label": text(lang, opt), "correct": i == q["answer_index"]}
            for i, opt in enumerate(q["options"][:26])
        ],
    }
    if q.get("feedback"):
        item["feedback"] = text(lang, q["feedback"])
    return item
