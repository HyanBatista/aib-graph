"""The demo course: fixture loading and the page layout shared by the PDF builder and the seed."""

import json
from functools import lru_cache
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
COURSE_JSON = FIXTURES / "demo_course.json"
SAMPLE_PDF = FIXTURES / "sample_book.pdf"


@lru_cache(maxsize=1)
def load_course():
    return json.loads(COURSE_JSON.read_text())


def layout():
    """Page plan of the sample book: a title page, then one page per chapter intro and per section.

    Returns a list of topics in reading order:
    {"title", "summary", "text", "level", "parent", "page", ...fixture fields}
    """
    course = load_course()
    page = 2  # page 1 is the title page
    topics = []
    for chapter in course["chapters"]:
        topics.append({**chapter, "level": 0, "parent": None, "page": page})
        page += 1
        for section in chapter["sections"]:
            topics.append({**section, "level": 1, "parent": chapter["title"], "page": page})
            page += 1
    return topics


def index_payload():
    """The index in the shape `books.services.save_index` expects."""
    result = []
    for chapter in load_course()["chapters"]:
        pages = [t["page"] for t in layout() if t["title"] == chapter["title"] or t.get("parent") == chapter["title"]]
        result.append({
            "title": chapter["title"],
            "summary": chapter["summary"],
            "page_start": min(pages),
            "page_end": max(pages),
            "subtopics": [
                {"title": t["title"], "summary": t["summary"], "page_start": t["page"], "page_end": t["page"]}
                for t in layout()
                if t.get("parent") == chapter["title"]
            ],
        })
    return result


def prerequisites():
    """(src title, dst title) pairs: listed `requires`, parent chapter → section, chapter → next chapter."""
    pairs = []
    chapters = load_course()["chapters"]
    for prev, nxt in zip(chapters, chapters[1:]):
        pairs.append((prev["title"], nxt["title"]))
    for t in layout():
        if t["parent"]:
            pairs.append((t["parent"], t["title"]))
        for req in t.get("requires", []):
            if (req, t["title"]) not in pairs:
                pairs.append((req, t["title"]))
    return pairs


def lesson_md(topic):
    ideas = "\n".join(f"- {k}" for k in topic.get("key_ideas", []))
    body = f"# {topic['title']}\n\n{topic['text']}\n"
    if ideas:
        body += f"\n## Key ideas\n\n{ideas}\n"
    return body


def chapter_quiz(chapter):
    """Chapters have no hand-written quiz: reuse the first question of each of their sections."""
    return [s["quiz"][0] for s in chapter["sections"]]
