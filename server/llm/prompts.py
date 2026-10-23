"""Prompt templates. Every prompt asks for JSON matching a schema in `llm.schemas`."""

import json

INDEX = """You are building the study index of the attached book.
Return its topics in reading order, each with its subtopics (at most two levels).
Aim for {min_topics}-{max_topics} topics and 2-5 subtopics per topic, skipping front/back matter
(preface, acknowledgements, bibliography, index).
For each entry give a one or two sentence summary and the PDF page range (1-based, physical page numbers
of the PDF file, not the printed page numbers).
Write titles and summaries in the book's own language."""

RELATIONS = """Below is the index of a book, as a JSON list of topics with ids.
Build its knowledge graph: list the relations between topics.
- "prerequisite": src must be understood before dst can be learned.
- "related": the topics are strongly connected but neither depends on the other.
Only use ids from the list. Do not create cycles of prerequisites. Prefer a sparse graph:
each topic should have at most 3 prerequisites.

Index:
{index_json}"""

NODE = """You are writing one lesson of a course generated from a book. Language: {language}.
Topic: "{title}"
Topic summary: {summary}
Topics the student has probably seen already: {seen}

Write:
1. `lesson_md`: a self-contained lesson in Markdown (400-900 words) explaining the topic, faithful to the
   book excerpt below. Use headings, lists and LaTeX ($...$) where useful. End with a short "Key ideas" list.
2. `quiz`: 3 to 5 multiple-choice questions on the lesson, 4 options each, exactly one correct
   (`answer_index`, 0-based), with a one-sentence `feedback` explaining the right answer.

Book excerpt (pages {page_start}-{page_end}):
{excerpt}"""

ROUTE = """A student studying the topic "{current}" of a course built from a book asked:
"{question}"

1. Answer the question in Markdown (`answer_md`), briefly and faithfully to the book. Language: {language}.
2. Decide which topic of the book index the question is really about (`target_topic_id`).
   Prefer topics marked "available" (not taught yet, prerequisites met), then "locked" ones (not taught yet),
   and pick a "covered" topic only if the question is clearly about something already taught.
   Use null when the question is unrelated to the book.

Index topics:
{topics_json}

Book excerpt for the current topic:
{excerpt}"""

TEST = """Write the final test of a course. Language: {language}.
The course is made of the lessons listed below (id, title, summary, key ideas).
Write at least one item per lesson, using every lesson id at least once, {per_node} items per lesson in total.
Mix item kinds: roughly two thirds "mcq" (4 options, `answer_index` 0-based) and one third "open"
(a short written answer, with a `rubric` that states what a full-credit answer must contain).
Questions must be answerable from the lessons.

Lessons:
{lessons_json}"""

GRADE = """Grade a student's answer to an open test question. Language: {language}.
Question: {prompt}
Rubric (what a full-credit answer must contain): {rubric}
Student answer: {answer}

Give `score` from 0 to 1 (partial credit allowed) and one or two sentences of `feedback` addressed to the student."""


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=1)
