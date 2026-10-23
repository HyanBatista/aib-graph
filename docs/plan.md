# AIB Graph — auto-generated, collaborative learning graphs (Electron + Django)

## Context
Edukors (edukors.org/graph) defines EGF: a course is a *learning graph* whose nodes are activities (display / collection / decision) and whose edges are paths. Their editor is hand-authored. We want the same idea, but **the graph builds itself**:

1. Professor uploads a book PDF → the system extracts an **index (topics → subtopics)** and a **knowledge graph** (topics + prerequisite relations).
2. The system generates the **first node**. Each node = one topic/subtopic of the index.
3. Students work on a node and **each must ask one question**. The question is mapped onto the knowledge graph; if it points at a topic that has no node yet, a **new node is created**, linked from the current one, and immediately visible to every student in the class.
4. Growth stops when **every index topic has a node**.
5. Professor can **freeze** the graph and **generate a test** covering all generated nodes.
6. A **dashboard** shows metrics per student and per class.

One class graph is shared by 1 professor, N assistants and N students. Repo is empty (only README.md) — greenfield.

## Decisions (confirmed)
- Desktop: **Electron + TypeScript** (electron-vite, React, @xyflow/react for the graph, Recharts for dashboards).
- Backend: **Django + Django Ninja + Postgres + WebSockets** (Django Channels, Redis channel layer). Long LLM jobs in **Celery** (reuses Redis).
- LLM: **Gemini** via the Python `google-genai` SDK, server-side only (key never ships in the app). PDF sent through the Gemini File API; structured JSON output (`response_schema`) for every call. Model name is a setting (`GEMINI_MODEL`, a "pro" model for index/KG/test, a "flash" model for question routing/grading).
- Internal model is **EGF-like**, with **Export `.egf`** for a frozen graph.

## Repo layout
```
desktop/            Electron app (electron-vite, React, TS)
  src/main/         window, secure token storage (safeStorage), .egf file save dialog
  src/preload/      contextBridge: token get/set, saveFile
  src/renderer/     React app: api client, ws client, pages, components
server/             Django project
  config/           settings, asgi.py (Channels router), celery.py
  accounts/         User, JWT auth (django-ninja-jwt)
  classes/          Classroom, Membership(role), invite codes
  books/            Book (PDF), IndexTopic, TopicRelation (knowledge graph)
  graph/            GraphNode, GraphEdge, NodeProgress, StudentQuestion, consumers.py
  assessment/       Test, TestItem, TestAttempt, ItemAnswer
  metrics/          aggregation queries + endpoints
  llm/              gemini client, prompts, pydantic schemas for structured output
docker-compose.yml  postgres, redis, server (daphne), worker (celery)
```

## Data model (server)
- `Classroom(name, professor, invite_code, status: draft|indexing|review|growing|complete|frozen)`; `Membership(user, classroom, role: professor|assistant|student)`.
- `Book(classroom, pdf_file, gemini_file_uri, page_count)`.
- `IndexTopic(book, parent, order, title, summary, page_start, page_end, level)` — the index; leaves and inner topics are both "coverable".
- `TopicRelation(src, dst, kind: prerequisite|related)` — the knowledge graph.
- `GraphNode(classroom, topic UNIQUE per classroom, lesson_md, quiz_json, created_by_question NULL, created_at)` — unique constraint `(classroom, topic)` prevents duplicate nodes when two students' questions hit the same topic at once.
- `GraphEdge(classroom, src_node, dst_node, origin_question NULL)`.
- `NodeProgress(student, node, opened_at, quiz_score, quiz_answers, question_done, completed_at)`.
- `StudentQuestion(student, node, text, answer_md, resolved_topic NULL, outcome: created_node|linked_existing|answered_only, created_node NULL)`.
- `Test(classroom, status: draft|published|closed)`, `TestItem(test, node, kind: mcq|open, prompt, options, answer_key, rubric)`, `TestAttempt`, `ItemAnswer(score, feedback, graded_by: ai|assistant|professor)`.

## Pipelines (Celery tasks in `llm/` + app modules)
1. **Ingest & index** — upload PDF → `pypdf` page count + per-page text (kept for grounding/citations) → upload to Gemini File API → prompt returns hierarchical index `{title, summary, page_start, page_end, children[]}`. Classroom → `review`.
2. **Professor review** — desktop shows the index as an editable tree (rename, merge, delete, reorder). On approve → task builds the **knowledge graph**: Gemini returns `prerequisite`/`related` relations between topic ids (validated: ids exist, prerequisite graph is acyclic; cycles dropped).
3. **First node** — root = first topic with no prerequisites (in index order). Generate node content grounded on its page range: `lesson_md` (Markdown + LaTeX) and a short quiz (3–5 MCQ with feedback). Classroom → `growing`. Broadcast `node.created`.
4. **Student on a node** — read lesson → take quiz (auto-scored) → **ask one question (required to complete the node)**. Question task (flash model), given the current node, its KG neighbours, the uncovered "frontier" topics (prerequisites already covered) and the covered topics:
   - returns `{answer_md, target_topic_id|null}` grounded in the book pages;
   - target uncovered → create `GraphNode` (inside `transaction.atomic`, `get_or_create` on the unique key), generate its content, add edge current→new, outcome `created_node`;
   - target already covered → add edge if missing, outcome `linked_existing`;
   - null/off-book → `answered_only`.
   - Broadcast `node.created` / `edge.created` / `question.answered`.
5. **Completion** — after each node creation, if every `IndexTopic` has a node → classroom `complete`, broadcast `graph.completed`. Fallback so growth can't stall: professor/assistant can "expand topic" manually from the uncovered list.
6. **Freeze & test** — professor freezes (no new questions/nodes; state `frozen`) → test task generates items so **every node gets ≥1 item** (mix of MCQ and open, with rubric) → professor/assistants edit → publish → students take it → MCQ auto-graded, open answers graded by Gemini against the rubric; assistants/professor can override grades.
7. **EGF export** — each `GraphNode` → `sm_<id>` (Markdown display) + `quiz_<id>` (collection) nodes; `GraphEdge` → EGF edges; download as `.egf` via main-process save dialog. Exact field names to be taken from Edukors' published EGF spec/examples (download one example `.egf` at implementation time and mirror it).

## Realtime
Channels consumer `ws/classes/<id>/` (JWT in query string, membership checked). Group per classroom. Events: `index.ready`, `job.progress`, `node.created`, `edge.created`, `question.answered` (only to the asker), `graph.completed`, `graph.frozen`, `test.published`. Celery tasks publish via `async_to_sync(channel_layer.group_send)`. The renderer keeps a zustand store patched by these events, so new nodes appear live in the graph view.

## API (Django Ninja, `/api`)
Auth (`/auth/register|login|refresh`), classes (create, join by invite code, members, set role), books (upload, index get/patch, approve), graph (get full graph, node detail, progress, submit quiz, ask question, expand topic, freeze, export egf), tests (generate, edit items, publish, attempt, grade override), metrics (`/metrics/class/<id>`, `/metrics/class/<id>/student/<uid>`). Role checks via a small `require_role(...)` helper used by every router.

## Desktop screens (renderer)
- Login / register; class list; create class (professor) / join with code.
- **Index review** (professor): editable tree + "Approve & build graph".
- **Graph view**: React Flow + ELK/dagre layout; nodes coloured by state (not visited / in progress / completed for the student; heat by avg score for staff); side panel with lesson, quiz, question box and answer; coverage bar "X / Y topics".
- **Test**: builder (staff) and taking/grading screens.
- **Dashboard**:
  - Student: nodes completed, quiz score per node, questions asked, nodes created by their questions, test score, per-topic mastery.
  - Class: index coverage %, graph growth over time, avg/median quiz per node (hardest topics), participation distribution, test score distribution, topic × student mastery heatmap; staff can drill into any student.
- Electron security: `contextIsolation: true`, `nodeIntegration: false`, CSP allowing only the configured server origin; JWT stored with `safeStorage`.

## Demo seed data
Management command `python manage.py seed_demo [--reset]` (idempotent; `--reset` wipes demo rows first), also run automatically by `docker compose` when `SEED_DEMO=1`. It needs **no Gemini key**: all content comes from a fixture file `server/demo/fixtures/demo_course.json` (hand-written index, KG, lessons, quizzes, questions, test items).

- **Users** (password `demo1234` for all, printed at the end of the command):
  - `prof@demo.local` — professor
  - `ta1@demo.local`, `ta2@demo.local` — assistants
  - `ana@`, `bruno@`, `carla@`, `diego@`, `elisa@`, `felipe@demo.local` — students
- **Classrooms** (one per lifecycle stage, so every screen has something to show):
  1. *"Intro to Algorithms — Review"* — status `review`: index (≈5 topics, ≈15 subtopics) waiting for professor approval; no nodes.
  2. *"Intro to Algorithms — Live"* — status `growing`: approved index + KG, ~60% of topics already have nodes, edges with `origin_question`, `NodeProgress` with varied quiz scores, `StudentQuestion` rows of all three outcomes, timestamps spread over the last 14 days (so the growth-over-time chart has a curve). Some frontier topics left uncovered so a live demo question creates a new node.
  3. *"Intro to Algorithms — Frozen"* — status `frozen`: all topics covered, published test with items for every node, attempts from all students (MCQ + open answers, some graded by AI, one overridden by an assistant) → dashboards fully populated.
- A small bundled sample PDF (`server/demo/fixtures/sample_book.pdf`, short public-domain/self-written text matching the fixture index) attached as each class's `Book`, so the "view source pages" panel works.
- **Fake LLM mode** `LLM_PROVIDER=fake`: the `llm/` client returns canned fixture responses (question routing picks the first uncovered frontier topic mentioned by keyword, else `answered_only`), so the full demo — including live node creation — runs offline without a Gemini key. Default is `gemini` when `GEMINI_API_KEY` is set.
- Desktop login screen shows a "Demo accounts" dropdown in development builds (`import.meta.env.DEV`) to log in as any seeded user in one click.

## Milestones
1. Scaffolding: docker-compose, Django project + Ninja + Channels + Celery, electron-vite app, auth, classes/roles, WS connection, **seed users + `seed_demo` skeleton**. Every later milestone extends the fixture/seed for the data it adds.
2. PDF ingest → index → professor review → knowledge graph.
3. First node + graph view + lesson/quiz.
4. Question routing → node creation → live broadcast → completion.
5. Freeze, test generation, taking, grading.
6. Metrics endpoints + dashboards.
7. EGF export, packaging (electron-builder for macOS/Windows/Linux).

## Verification
- Server: `pytest` (pytest-django) with Gemini client mocked by fixtures returning recorded structured outputs; tests for: index parsing, KG cycle removal, concurrent question → single node (two threads, unique constraint), completion detection, freeze blocks questions, test covers every node, role permissions, metrics aggregates.
- Channels: `channels.testing.WebsocketCommunicator` test that a question creating a node broadcasts `node.created` to another member.
- Desktop: `vitest` for store/event reducers; Playwright `_electron` smoke test: log in → open class → graph renders.
- Seed: test that `seed_demo` runs twice without errors/duplicates, and that the frozen class's metrics endpoints return non-empty data.
- Demo smoke: `SEED_DEMO=1 LLM_PROVIDER=fake docker compose up`, log in as `prof@demo.local` and `ana@demo.local` in two Electron windows, open the *Live* class, ask a question as Ana → new node appears in the professor's window; open dashboards of the *Frozen* class.
- End-to-end manual: `docker compose up`, run 3 Electron instances (professor, 2 students), upload a short public-domain PDF, approve index, ask questions from both students and watch nodes appear on both screens, continue until "complete", freeze, generate/take test, check both dashboards, export `.egf` and open it in the Edukors Graph Editor.
