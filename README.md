# AIB Graph

Self-growing learning graphs for a class, inspired by [Edukors Graph](https://edukors.org/graph/).

1. The professor uploads a book (PDF). Gemini extracts an **index** (topics → subtopics), the professor reviews it, and the server builds a **knowledge graph** (prerequisites between topics) and the **first node**.
2. Every node is one topic: a lesson plus a quiz. On each node, every student **asks one question**. The question is routed onto the knowledge graph:
   - about a topic with no node yet → a **new node** is created and linked (if its prerequisites are missing, the closest prerequisite is opened first);
   - about a topic that is already covered → the nodes are linked;
   - off-book → the question is just answered.
   New nodes appear live for the whole class (WebSockets).
3. The graph is **complete** when every index topic has a node. The professor **freezes** it and **generates a test** that covers every node; MCQs are auto-graded and open answers are graded by the AI (assistants can override).
4. **Dashboards** show metrics per student and per class. A frozen graph can be **exported as `.egf`** ([EGF v1](https://edukors.org/graph/schema/v1/)) and opened in the Edukors editor.

Roles per class: one professor, any number of assistants and students (join by invite code).

```
desktop/   Electron + React + TypeScript app (see desktop/README.md)
server/    Django + Django Ninja + Channels + Celery, Postgres, Redis, Gemini
```

## Quick start (offline demo, no API key)

With `make` (run `make` alone to list every command):

```bash
make install      # server and desktop dependencies
make seed         # migrate + demo users and classes (make reset-demo to rebuild)
make dev          # server on http://127.0.0.1:8000 and the desktop app
```

The desktop app can also be run from a production build, or packaged:

```bash
make desktop-start                 # build and run without the dev server
make desktop-start PROFILE=ana     # a second window with its own login, to try two users at once
make desktop-start SERVER_URL=http://10.0.0.5:8000   # talk to another server
make desktop-dist                  # installer for this OS in desktop/dist/ (also desktop-dist-mac/-win/-linux)
```

Or step by step:

```bash
cd server
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo          # --reset to rebuild
uv run daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

With no env vars the server uses SQLite, an in-memory channel layer, runs Celery tasks inline and uses the **fake LLM** (deterministic answers from the book text), so everything works offline.

Then start the desktop app:

```bash
cd desktop
npm install
npm run dev
```

### Demo data

Every account uses the password `demo1234`. In dev builds, the login screen has a one-click "Demo accounts" picker.

| Account | Role |
|---|---|
| `prof@demo.local` | professor |
| `ta1@demo.local`, `ta2@demo.local` | assistants |
| `ana@`, `bruno@`, `carla@`, `diego@`, `elisa@`, `felipe@demo.local` | students |

The demo has three classes built from the bundled sample book (`server/demo/fixtures/sample_book.pdf`, 20 topics):

- **Intro to Algorithms — Review**: the index is waiting for the professor's approval.
- **Intro to Algorithms — Live**: 12 of 20 topics covered, two weeks of activity. Log in as a student, open *Stacks and Queues* and ask *"How do hash tables handle collisions?"*. A *Hash Tables* node appears on every open screen.
- **Intro to Algorithms — Frozen**: every topic is covered, and a published test has been taken by every student. The dashboards are fully populated here.

You can also create a new class and upload `sample_book.pdf` to walk through the whole pipeline.

## Running with Docker (Postgres, Redis, Celery worker)

```bash
cp .env.example .env        # set DJANGO_SECRET_KEY, and GEMINI_API_KEY to use Gemini
docker compose up --build
DJANGO_DEBUG=1 SEED_DEMO=1 LLM_PROVIDER=fake docker compose up --build   # local offline demo
```

Without `DJANGO_DEBUG=1` the server refuses to start unless `DJANGO_SECRET_KEY` is set (32+ characters). Uploaded PDFs are never served directly; clients read pages through the authenticated API.

## Configuration (server env vars)

| Variable | Default | |
|---|---|---|
| `GEMINI_API_KEY` | – | enables Gemini |
| `LLM_PROVIDER` | `gemini` if a key is set, else `fake` | |
| `GEMINI_MODEL_PRO` / `GEMINI_MODEL_FLASH` | `gemini-2.5-pro` / `gemini-2.5-flash` | pro: index, knowledge graph, lessons, test; flash: question routing, grading |
| `DATABASE_URL` | SQLite | e.g. `postgres://user:pass@host/db` |
| `REDIS_URL` | – | enables the Redis channel layer and a real Celery worker |
| `DJANGO_SECRET_KEY` | dev key when `DJANGO_DEBUG=1`, else required | signs JWTs; 32+ characters |
| `DJANGO_DEBUG` | `1` (`0` in docker compose) | |

## Tests

```bash
cd server && uv run pytest                     # SQLite
DATABASE_URL=postgres://... uv run pytest      # also runs the concurrent-node-creation test
cd desktop && npm test && npm run e2e
```

## How it works (server)

- `books/services.py`: PDF → page text → Gemini File API → index (`IndexTopic`) → knowledge graph (`TopicRelation`, prerequisite cycles removed) → first node.
- `graph/services.py`: topic states (covered / available / locked), question routing, node creation (one node per topic, guarded by a DB unique constraint), completion and freeze.
- `assessment/services.py`: test generation (any node the model skips gets a fallback item), grading.
- `metrics/services.py`: class and student dashboards.
- `graph/egf.py`: EGF export, validated against the official schema in tests.
- `llm/client.py`: `GeminiLLM` (structured JSON output via `response_schema`) and `FakeLLM`.
- Realtime: `ws://<server>/ws/classes/<id>/?token=<jwt>` pushes `node.created`, `node.ready`, `edge.created`, `question.answered`, `class.status`, `graph.completed`, `graph.frozen`, `test.*` and `metrics.changed`.
