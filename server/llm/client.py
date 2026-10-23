"""LLM access. `get_llm()` returns the Gemini client or the offline fake, per `settings.LLM_PROVIDER`.

Both implement the same methods and take/return plain data, so the rest of the server
never touches the SDK.
"""

import logging
import re
import time
from functools import lru_cache

from django.conf import settings

from . import prompts
from .schemas import (
    GradeDraft,
    IndexDraft,
    NodeContentDraft,
    QuestionRouting,
    QuizQuestionDraft,
    RelationDraft,
    RelationsDraft,
    SubtopicDraft,
    TestDraft,
    TestItemDraft,
    TopicDraft,
)

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class GeminiLLM:
    def __init__(self, api_key, model_pro, model_flash):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model_pro = model_pro
        self.model_flash = model_flash

    def _generate(self, model, contents, schema):
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.3,
        )
        try:
            response = self._client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # network, quota, safety...
            raise LLMError(str(exc)) from exc
        if response.parsed is None:
            try:
                return schema.model_validate_json(response.text or "")
            except Exception as exc:
                raise LLMError(f"Unparseable response: {(response.text or '')[:300]}") from exc
        return response.parsed

    def upload_pdf(self, path, timeout=120):
        try:
            uploaded = self._client.files.upload(file=path, config={"mime_type": "application/pdf"})
            # Large PDFs are processed asynchronously; they can't be referenced until ACTIVE.
            deadline = time.monotonic() + timeout
            while getattr(uploaded.state, "name", uploaded.state) == "PROCESSING":
                if time.monotonic() > deadline:
                    raise LLMError("Timed out waiting for Gemini to process the PDF")
                time.sleep(2)
                uploaded = self._client.files.get(name=uploaded.name)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        if getattr(uploaded.state, "name", uploaded.state) == "FAILED":
            raise LLMError("Gemini could not process the PDF")
        return uploaded.uri

    def extract_index(self, pdf_path, pages_text, file_uri=None):
        from google.genai import types

        page_count = len(pages_text)
        prompt = prompts.INDEX.format(
            min_topics=max(3, min(8, page_count // 20)),
            max_topics=max(6, min(20, page_count // 8)),
        )
        if file_uri is None:
            file_uri = self.upload_pdf(pdf_path)
        pdf = types.Part.from_uri(file_uri=file_uri, mime_type="application/pdf")
        return self._generate(self.model_pro, [pdf, prompt], IndexDraft)

    def build_relations(self, topics):
        prompt = prompts.RELATIONS.format(index_json=prompts.dumps(topics))
        return self._generate(self.model_pro, prompt, RelationsDraft)

    def generate_node(self, topic, excerpt, seen, language):
        prompt = prompts.NODE.format(
            language=language,
            title=topic["title"],
            summary=topic["summary"],
            seen=", ".join(seen) or "none",
            page_start=topic["page_start"],
            page_end=topic["page_end"],
            excerpt=excerpt,
        )
        return self._generate(self.model_pro, prompt, NodeContentDraft)

    def route_question(self, question, current, topics, excerpt, language):
        prompt = prompts.ROUTE.format(
            current=current["title"],
            question=question,
            language=language,
            topics_json=prompts.dumps(topics),
            excerpt=excerpt,
        )
        return self._generate(self.model_flash, prompt, QuestionRouting)

    def generate_test(self, lessons, language, per_node):
        prompt = prompts.TEST.format(language=language, per_node=per_node, lessons_json=prompts.dumps(lessons))
        return self._generate(self.model_pro, prompt, TestDraft)

    def grade_open(self, prompt, rubric, answer, language):
        text = prompts.GRADE.format(language=language, prompt=prompt, rubric=rubric, answer=answer)
        return self._generate(self.model_flash, text, GradeDraft)


_WORD = re.compile(r"[\wÀ-ÿ]{4,}", re.UNICODE)
_STOP = {"what", "when", "where", "which", "about", "does", "this", "that", "with", "from", "have", "there",
         "como", "qual", "quais", "sobre", "para", "isso", "esse", "essa", "entre", "quando", "onde"}


def keywords(text):
    return {w.lower() for w in _WORD.findall(text or "")} - _STOP


class FakeLLM:
    """Deterministic stand-in used by the demo and the tests. No network calls."""

    def upload_pdf(self, path):
        return ""

    def extract_index(self, pdf_path, pages_text, file_uri=None):
        outline = _pdf_outline(pdf_path)
        if outline:
            return IndexDraft(book_title=outline[0], language="en", topics=outline[1])
        # No outline: one topic per chunk of pages, titled by the first line of its first page.
        topics = []
        chunk = max(1, len(pages_text) // 6)
        for start in range(0, len(pages_text), chunk):
            end = min(start + chunk, len(pages_text))
            first_line = next((ln.strip() for ln in pages_text[start].splitlines() if ln.strip()), "")
            title = first_line[:80] or f"Pages {start + 1}-{end}"
            subtopics = [
                SubtopicDraft(title=f"{title} — part {i + 1}", summary="", page_start=p + 1, page_end=p + 1)
                for i, p in enumerate(range(start, end))
            ] if end - start > 1 else []
            topics.append(TopicDraft(title=title, summary=pages_text[start][:200], page_start=start + 1,
                                     page_end=end, subtopics=subtopics))
        return IndexDraft(book_title="Untitled book", language="en", topics=topics)

    def build_relations(self, topics):
        relations = []
        roots = [t for t in topics if t["parent_id"] is None]
        for a, b in zip(roots, roots[1:]):
            relations.append(RelationDraft(src=a["id"], dst=b["id"], kind="prerequisite"))
        for t in topics:
            if t["parent_id"] is not None:
                relations.append(RelationDraft(src=t["parent_id"], dst=t["id"], kind="prerequisite"))
        return RelationsDraft(relations=relations)

    def generate_node(self, topic, excerpt, seen, language):
        body = re.sub(r"\[page \d+\]\n", "", excerpt).strip()[:1500] or topic["summary"]
        lesson = f"# {topic['title']}\n\n{topic['summary']}\n\n## From the book\n\n{body}\n\n## Key ideas\n\n- {topic['title']}\n"
        others = [s for s in seen if s != topic["title"]][:3]
        while len(others) < 3:
            others.append(f"None of the above ({len(others) + 1})")
        quiz = [
            QuizQuestionDraft(
                prompt="Which topic does this lesson cover?",
                options=[topic["title"], *others],
                answer_index=0,
                feedback=f"This lesson is about {topic['title']}.",
            ),
            QuizQuestionDraft(
                prompt=f"Is the following statement about the lesson true? \"{(topic['summary'] or topic['title'])[:140]}\"",
                options=["True", "False"],
                answer_index=0,
                feedback="The statement is the summary of the lesson.",
            ),
        ]
        return NodeContentDraft(lesson_md=lesson, quiz=quiz)

    def route_question(self, question, current, topics, excerpt, language):
        words = keywords(question)

        def overlap(t):
            return len(words & keywords(t["title"] + " " + t["summary"]))

        target = None
        for status in ("available", "locked", "covered"):
            scored = sorted(((overlap(t), t) for t in topics if t["status"] == status), key=lambda x: -x[0])
            if scored and scored[0][0] > 0:
                target = scored[0][1]
                break
        if target is None:
            return QuestionRouting(answer_md="That question goes beyond this book, so I can't place it in the course.",
                                   target_topic_id=None)
        answer = f"Your question relates to **{target['title']}**. {target['summary']}"
        return QuestionRouting(answer_md=answer, target_topic_id=target["id"])

    def generate_test(self, lessons, language, per_node):
        items = []
        for i, lesson in enumerate(lessons):
            for q in lesson.get("quiz", [])[:1]:
                items.append(TestItemDraft(node_id=lesson["id"], kind="mcq", prompt=f"[{lesson['title']}] {q['prompt']}",
                                           options=q["options"], answer_index=q["answer_index"]))
            if i % 2 == 0 or not lesson.get("quiz"):
                items.append(TestItemDraft(
                    node_id=lesson["id"], kind="open",
                    prompt=f"In your own words, explain the main idea of \"{lesson['title']}\".",
                    rubric=f"Mentions: {lesson['summary'] or lesson['title']}",
                ))
        return TestDraft(items=items)

    def grade_open(self, prompt, rubric, answer, language):
        expected = keywords(rubric)
        hit = len(expected & keywords(answer))
        score = round(min(1.0, hit / max(1, min(len(expected), 5))), 2)
        feedback = "Good answer." if score >= 0.7 else "Your answer misses some key ideas from the rubric."
        return GradeDraft(score=score, feedback=feedback)


def _pdf_outline(path):
    """Two-level index from the PDF bookmarks, if the file has them."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        outline = reader.outline
    except Exception:
        return None
    if not outline:
        return None

    def page_of(item):
        try:
            return reader.get_destination_page_number(item) + 1
        except Exception:
            return 1

    flat = []  # (level, title, page)
    for item in outline:
        if isinstance(item, list):
            for sub in item:
                if not isinstance(sub, list):
                    flat.append((1, sub.title, page_of(sub)))
        else:
            flat.append((0, item.title, page_of(item)))
    if not flat:
        return None
    last_page = len(reader.pages)
    ends = [flat[i + 1][2] - 1 if i + 1 < len(flat) else last_page for i in range(len(flat))]
    topics = []
    for (level, title, page), end in zip(flat, ends):
        end = max(end, page)
        if level == 0 or not topics:
            topics.append(TopicDraft(title=title, summary="", page_start=page, page_end=end))
        else:
            topics[-1].subtopics.append(SubtopicDraft(title=title, summary="", page_start=page, page_end=end))
    for t in topics:
        if t.subtopics:
            t.page_end = max(t.page_end, t.subtopics[-1].page_end)
    title = (reader.metadata or {}).get("/Title") or "Untitled book"
    return title, topics


@lru_cache(maxsize=1)
def _gemini():
    return GeminiLLM(settings.GEMINI_API_KEY, settings.GEMINI_MODEL_PRO, settings.GEMINI_MODEL_FLASH)


def get_llm():
    if settings.LLM_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY:
            raise LLMError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        return _gemini()
    return FakeLLM()
