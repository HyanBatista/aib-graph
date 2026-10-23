"""Structured outputs requested from the LLM. Gemini receives these as `response_schema`."""

from typing import Literal

from pydantic import BaseModel, Field


class SubtopicDraft(BaseModel):
    title: str
    summary: str
    page_start: int
    page_end: int


class TopicDraft(BaseModel):
    title: str
    summary: str
    page_start: int
    page_end: int
    subtopics: list[SubtopicDraft] = Field(default_factory=list)


class IndexDraft(BaseModel):
    book_title: str
    language: str = Field(description="ISO 639-1 code of the book's language, e.g. 'en' or 'pt'")
    topics: list[TopicDraft]


class RelationDraft(BaseModel):
    src: int = Field(description="id of the source topic")
    dst: int = Field(description="id of the destination topic")
    kind: Literal["prerequisite", "related"]


class RelationsDraft(BaseModel):
    relations: list[RelationDraft]


class QuizQuestionDraft(BaseModel):
    prompt: str
    options: list[str]
    answer_index: int
    feedback: str


class NodeContentDraft(BaseModel):
    lesson_md: str
    quiz: list[QuizQuestionDraft]


class QuestionRouting(BaseModel):
    answer_md: str = Field(description="Answer to the student's question, in Markdown, grounded in the book")
    target_topic_id: int | None = Field(
        default=None,
        description="id of the index topic the question is really about, or null if it is off-book",
    )


class TestItemDraft(BaseModel):
    node_id: int
    kind: Literal["mcq", "open"]
    prompt: str
    options: list[str] = Field(default_factory=list)
    answer_index: int | None = None
    rubric: str = ""


class TestDraft(BaseModel):
    items: list[TestItemDraft]


class GradeDraft(BaseModel):
    score: float = Field(description="0 (wrong) to 1 (fully correct)")
    feedback: str
