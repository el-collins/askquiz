# AskQuiz Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend that proxies text and image questions to Groq, enforces a per-device daily rate limit via Postgres, and never exposes the Groq API key to clients.

**Architecture:** A single `POST /ask` endpoint accepts a multipart form (`type`, `content` or `image`) plus an `X-Device-Id` header, checks/increments a Postgres-backed rate-limit counter, then calls Groq's text or vision model with a fixed terse system prompt and returns `{"answer": str}`. Two Docker Compose services (`api`, `db`) make up the whole deployable unit.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, the `groq` SDK, pytest/pytest-asyncio, Docker Compose, Postgres 16.

**Spec:** `docs/superpowers/specs/2026-09-24-askquiz-mvp-design.md`

## Global Constraints

- Backend language/framework: FastAPI (Python) — per spec section 4.2.
- Single Postgres table only: `usage(device_id, date, request_count)` — no users table, no Q&A table (spec section 4.3).
- No question/answer content is persisted anywhere — only rate-limit counters (spec section 4.2).
- Groq API key lives only in a server-side environment variable, never returned to or stored by the client (spec sections 4.2, 8).
- System prompt enforces terse output (≤30–50 words), low temperature, same prompt for text and image paths (spec section 4.4, original notes).
- No OCR fallback — if the vision model can't parse an image, its own response is returned as-is (spec sections 4.4, 6).
- No response streaming (SSE/chunked) — synchronous request/response only (spec section 5).
- No Redis — Postgres-only rate limiting (spec section 9, explicitly deferred).
- No user accounts, login, or cross-device history (spec section 2).
- Exactly two Docker Compose services: `api` and `db` (spec sections 3, 8).
- Groq calls use a 15s request-level timeout (spec section 6).
- Rate limit is a per-device daily cap keyed by `(device_id, date)`, returns `429` when exceeded (spec sections 4.3, 6).

## Review Focus

- Oversized image upload — the spec sets no limit; without one, a large image risks unbounded Groq cost/latency and memory use. Expect a request-level cap that rejects oversized images before calling Groq. → tested in Task 4.
- Non-image content-type sent for `type=image` — expect a clean `400` rather than forwarding arbitrary bytes to Groq as an "image". → tested in Task 4.
- Concurrent requests from the same device near its cap — expect the increment to be atomic so a race can't let a device exceed its daily cap. → tested in Task 2.
- Empty/whitespace-only text content for `type=text` — expect a `400` before spending a Groq call on nothing. → tested in Task 4.
- Groq returning an empty/blank completion — expect this to surface as a failure (`502`), not a blank `answer` shown to the user. → tested in Task 3.

---

### Task 1: Project scaffolding & health check

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/.gitignore`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/Dockerfile`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: FastAPI app instance importable as `app.main:app`; `GET /health -> {"status": "ok"}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Create supporting files and run the test to verify it fails**

```text
# backend/requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pytest>=8.3.0
pytest-asyncio>=0.24.0
httpx>=0.27.0
```

```ini
# backend/pytest.ini
[pytest]
asyncio_mode = auto
```

```text
# backend/.gitignore
__pycache__/
*.pyc
.pytest_cache/
.env
```

Create empty `backend/app/__init__.py` and `backend/tests/__init__.py`.

Run (from `backend/`): `pip install -r requirements.txt && pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/main.py
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}
```

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/pytest.ini backend/.gitignore backend/app backend/tests backend/Dockerfile
git commit -m "feat(backend): scaffold FastAPI app with health check"
```

---

### Task 2: Database layer & rate limiting (Postgres)

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/tests/test_db.py`
- Create: `backend/docker-compose.yml`
- Create: `backend/.env.example`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: nothing new
- Produces (in `app/db.py`): `async def create_pool(database_url: str) -> asyncpg.Pool` (creates the connection pool and ensures the `usage` table exists); `async def check_and_increment(pool: asyncpg.Pool, device_id: str, cap: int, today: date) -> bool` (atomically increments today's count for the device and returns whether the request is allowed)

- [ ] **Step 1: Add Docker Compose and env files, start Postgres**

```yaml
# backend/docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://askquiz:askquiz@db:5432/askquiz
      GROQ_API_KEY: ${GROQ_API_KEY}
      DAILY_REQUEST_CAP: ${DAILY_REQUEST_CAP:-50}
    depends_on:
      - db
  db:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: askquiz
      POSTGRES_PASSWORD: askquiz
      POSTGRES_DB: askquiz
    volumes:
      - db_data:/var/lib/postgresql/data
volumes:
  db_data:
```

```text
# backend/.env.example
GROQ_API_KEY=your_groq_api_key_here
DAILY_REQUEST_CAP=50
```

Run: `docker compose up -d db` (from `backend/`)
Expected: the `db` container starts and stays healthy — check with `docker compose ps`

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_db.py
import asyncio
import os
from datetime import date

import pytest

from app.db import create_pool, check_and_increment

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://askquiz:askquiz@localhost:5432/askquiz"
)


@pytest.fixture
async def pool():
    db_pool = await create_pool(TEST_DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM usage")
    yield db_pool
    await db_pool.close()


async def test_allows_requests_up_to_cap(pool):
    device_id = "device-a"
    today = date(2026, 9, 24)
    for _ in range(3):
        allowed = await check_and_increment(pool, device_id, cap=3, today=today)
        assert allowed is True


async def test_rejects_requests_over_cap(pool):
    device_id = "device-b"
    today = date(2026, 9, 24)
    for _ in range(3):
        await check_and_increment(pool, device_id, cap=3, today=today)
    allowed = await check_and_increment(pool, device_id, cap=3, today=today)
    assert allowed is False


async def test_cap_resets_on_a_new_date(pool):
    device_id = "device-c"
    for _ in range(3):
        await check_and_increment(pool, device_id, cap=3, today=date(2026, 9, 24))
    allowed_next_day = await check_and_increment(
        pool, device_id, cap=3, today=date(2026, 9, 25)
    )
    assert allowed_next_day is True


async def test_concurrent_requests_never_exceed_cap(pool):
    device_id = "device-d"
    today = date(2026, 9, 24)
    results = await asyncio.gather(
        *[check_and_increment(pool, device_id, cap=3, today=today) for _ in range(10)]
    )
    assert sum(results) == 3
```

- [ ] **Step 3: Run the tests to verify they fail**

```text
# add to backend/requirements.txt
asyncpg>=0.29.0
```

Run: `pip install -r requirements.txt && pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 4: Write the minimal implementation**

```python
# backend/app/db.py
from datetime import date

import asyncpg

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS usage (
    device_id TEXT NOT NULL,
    date DATE NOT NULL,
    request_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, date)
);
"""


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url)
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)
    return pool


async def check_and_increment(
    pool: asyncpg.Pool, device_id: str, cap: int, today: date
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO usage (device_id, date, request_count)
            VALUES ($1, $2, 1)
            ON CONFLICT (device_id, date)
            DO UPDATE SET request_count = usage.request_count + 1
            RETURNING request_count
            """,
            device_id,
            today,
        )
    return row["request_count"] <= cap
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/tests/test_db.py backend/docker-compose.yml backend/.env.example backend/requirements.txt
git commit -m "feat(backend): add Postgres-backed rate limiting"
```

---

### Task 3: Groq client wrapper

**Files:**
- Create: `backend/app/groq_client.py`
- Create: `backend/tests/test_groq_client.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: nothing new (takes a Groq SDK client object as a parameter, so it stays testable without network calls)
- Produces (in `app/groq_client.py`): `def ask_text(client, content: str) -> str`; `def ask_image(client, image_bytes: bytes, mime_type: str) -> str`; `class GroqAnswerError(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_groq_client.py
from types import SimpleNamespace

import pytest

from app.groq_client import ask_text, ask_image, GroqAnswerError


class FakeGroqClient:
    def __init__(self, content, raise_exc=None):
        self._content = content
        self._raise_exc = raise_exc
        self.last_call = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_call = kwargs
        if self._raise_exc:
            raise self._raise_exc
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_ask_text_returns_stripped_answer():
    client = FakeGroqClient(content="  B. Queue  ")
    answer = ask_text(client, "Which data structure uses FIFO?")
    assert answer == "B. Queue"
    assert client.last_call["messages"][1]["content"] == "Which data structure uses FIFO?"


def test_ask_text_raises_on_empty_answer():
    client = FakeGroqClient(content="   ")
    with pytest.raises(GroqAnswerError):
        ask_text(client, "What is polymorphism?")


def test_ask_text_wraps_sdk_errors():
    client = FakeGroqClient(content=None, raise_exc=ConnectionError("boom"))
    with pytest.raises(GroqAnswerError):
        ask_text(client, "What is polymorphism?")


def test_ask_image_sends_data_url_and_returns_answer():
    client = FakeGroqClient(content="B. Paris")
    answer = ask_image(client, b"fake-bytes", "image/jpeg")
    assert answer == "B. Paris"
    image_part = client.last_call["messages"][1]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_ask_image_raises_on_empty_answer():
    client = FakeGroqClient(content="")
    with pytest.raises(GroqAnswerError):
        ask_image(client, b"fake-bytes", "image/jpeg")
```

- [ ] **Step 2: Run the tests to verify they fail**

```text
# add to backend/requirements.txt
groq>=0.11.0
```

Run: `pip install -r requirements.txt && pytest tests/test_groq_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.groq_client'`

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/groq_client.py
import base64

SYSTEM_PROMPT = (
    "Answer the user's question directly. Be extremely concise. "
    "Give only the answer and, when necessary, one short explanation "
    "(max 30-50 words total). Do not provide introductions, "
    "conclusions, or unnecessary details."
)

TEXT_MODEL = "llama-3.1-8b-instant"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class GroqAnswerError(Exception):
    """Raised when Groq fails to return a usable answer."""


def ask_text(client, content: str) -> str:
    try:
        response = client.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )
    except Exception as exc:
        raise GroqAnswerError(f"Groq request failed: {exc}") from exc
    return _extract_answer(response)


def ask_image(client, image_bytes: bytes, mime_type: str) -> str:
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64_image}"
    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Answer the question shown in this image."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
    except Exception as exc:
        raise GroqAnswerError(f"Groq request failed: {exc}") from exc
    return _extract_answer(response)


def _extract_answer(response) -> str:
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise GroqAnswerError("Groq returned an empty answer")
    return answer.strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_groq_client.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/groq_client.py backend/tests/test_groq_client.py backend/requirements.txt
git commit -m "feat(backend): add Groq text/vision client wrapper"
```

---

### Task 4: `/ask` endpoint — validation, wiring, error handling

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_ask_endpoint.py`
- Modify: `backend/app/main.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: `create_pool`, `check_and_increment` from `app/db.py` (Task 2); `ask_text`, `ask_image`, `GroqAnswerError` from `app/groq_client.py` (Task 3)
- Produces: `POST /ask` — multipart form fields `type: "text"|"image"`, `content: str` (for text), `image: file` (for image), header `X-Device-Id: str` → `200 {"answer": str}` or `400`/`413`/`429`/`502`; `load_settings() -> Settings` in `app/config.py`

- [ ] **Step 1: Add config module and test env defaults**

```python
# backend/app/config.py
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    database_url: str
    daily_request_cap: int


def load_settings() -> Settings:
    groq_api_key = os.environ.get("GROQ_API_KEY")
    database_url = os.environ.get("DATABASE_URL")
    if not groq_api_key:
        raise RuntimeError("Missing required environment variable: GROQ_API_KEY")
    if not database_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
    daily_request_cap = int(os.environ.get("DAILY_REQUEST_CAP", "50"))
    return Settings(
        groq_api_key=groq_api_key,
        database_url=database_url,
        daily_request_cap=daily_request_cap,
    )
```

```python
# backend/tests/conftest.py
import os

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://askquiz:askquiz@localhost:5432/askquiz"
)
os.environ.setdefault("DAILY_REQUEST_CAP", "3")
```

This must exist before Step 2's tests import `app.main`, since `conftest.py` is loaded by pytest before test module collection — it guarantees `load_settings()` never fails for lack of env vars during tests.

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_ask_endpoint.py
import io

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture
def client(monkeypatch):
    async def fake_create_pool(database_url):
        return object()

    monkeypatch.setattr(main_module, "create_pool", fake_create_pool)
    monkeypatch.setattr(main_module, "Groq", lambda **kwargs: object())

    async def default_check_and_increment(pool, device_id, cap, today):
        return True

    monkeypatch.setattr(main_module, "check_and_increment", default_check_and_increment)

    with TestClient(main_module.app) as c:
        yield c


def test_text_question_returns_answer(client, monkeypatch):
    monkeypatch.setattr(main_module, "ask_text", lambda groq_client, content: "B. Queue")

    response = client.post(
        "/ask",
        data={"type": "text", "content": "Which data structure uses FIFO?"},
        headers={"X-Device-Id": "device-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "B. Queue"}


def test_text_missing_content_returns_400(client):
    response = client.post(
        "/ask", data={"type": "text"}, headers={"X-Device-Id": "device-1"}
    )
    assert response.status_code == 400


def test_text_blank_content_returns_400(client):
    response = client.post(
        "/ask",
        data={"type": "text", "content": "   "},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 400


def test_image_missing_file_returns_400(client):
    response = client.post(
        "/ask", data={"type": "image"}, headers={"X-Device-Id": "device-1"}
    )
    assert response.status_code == 400


def test_image_wrong_content_type_returns_400(client):
    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 400


def test_image_too_large_returns_413(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_IMAGE_BYTES", 10)
    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(b"x" * 100), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 413


def test_missing_device_id_header_returns_400(client):
    response = client.post("/ask", data={"type": "text", "content": "hi"})
    assert response.status_code == 400


def test_rate_limit_exceeded_returns_429(client, monkeypatch):
    async def deny(pool, device_id, cap, today):
        return False

    monkeypatch.setattr(main_module, "check_and_increment", deny)

    response = client.post(
        "/ask",
        data={"type": "text", "content": "hi"},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 429


def test_groq_failure_returns_502(client, monkeypatch):
    from app.groq_client import GroqAnswerError

    def failing_ask_text(groq_client, content):
        raise GroqAnswerError("boom")

    monkeypatch.setattr(main_module, "ask_text", failing_ask_text)

    response = client.post(
        "/ask",
        data={"type": "text", "content": "hi"},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 502
```

- [ ] **Step 3: Run the tests to verify they fail**

```text
# add to backend/requirements.txt
python-multipart>=0.0.9
```

Run: `pip install -r requirements.txt && pytest tests/test_ask_endpoint.py -v`
Expected: FAIL — `/ask` doesn't exist yet (404s / AttributeError on `create_pool` not present in `app.main`)

- [ ] **Step 4: Write the minimal implementation**

```python
# backend/app/main.py
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from groq import Groq

from app.config import load_settings
from app.db import create_pool, check_and_increment
from app.groq_client import ask_text, ask_image, GroqAnswerError

settings = load_settings()
app = FastAPI()

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


@app.on_event("startup")
async def startup() -> None:
    app.state.db_pool = await create_pool(settings.database_url)
    app.state.groq_client = Groq(api_key=settings.groq_api_key, timeout=15.0)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask")
async def ask(
    request: Request,
    type: Literal["text", "image"] = Form(...),
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    x_device_id: str = Header(..., alias="X-Device-Id"),
):
    if not x_device_id.strip():
        raise HTTPException(status_code=400, detail="X-Device-Id header must not be empty")

    if type == "text":
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="content is required for type=text")
    else:
        if image is None:
            raise HTTPException(status_code=400, detail="image file is required for type=image")
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400, detail=f"unsupported image type: {image.content_type}"
            )

    allowed = await check_and_increment(
        request.app.state.db_pool, x_device_id, settings.daily_request_cap, date.today()
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="daily request limit reached")

    client = request.app.state.groq_client
    try:
        if type == "text":
            answer = ask_text(client, content.strip())
        else:
            image_bytes = await image.read()
            if len(image_bytes) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="image too large")
            answer = ask_image(client, image_bytes, image.content_type)
    except GroqAnswerError:
        raise HTTPException(status_code=502, detail="failed to get an answer")

    return {"answer": answer}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/ -v`
Expected: PASS (all tests across all files, including Tasks 1–3's tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/conftest.py backend/tests/test_ask_endpoint.py backend/requirements.txt
git commit -m "feat(backend): wire up /ask endpoint with validation and error handling"
```

---

### Task 5: Full-stack Docker verification (manual)

**Files:** none (verification only)

**Interfaces:**
- Consumes: the full `api` + `db` Docker Compose stack from Tasks 1–4
- Produces: a confirmed working deployment; no new code interfaces

This task is manual verification, not TDD — it needs a real Groq API key and a real photographed question, which automated tests can't exercise. Per spec section 7 ("Pre-ship manual smoke test").

- [ ] **Step 1: Configure real secrets**

Copy `backend/.env.example` to `backend/.env` and set a real `GROQ_API_KEY`.

- [ ] **Step 2: Build and start the stack**

Run (from `backend/`): `docker compose up --build -d`
Expected: `docker compose ps` shows both `api` and `db` as running/healthy

- [ ] **Step 3: Verify the health endpoint**

Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`

- [ ] **Step 4: Verify a real text question**

Run:
```bash
curl -X POST http://localhost:8000/ask \
  -H "X-Device-Id: smoke-test" \
  -F "type=text" \
  -F "content=Which data structure uses FIFO? A. Stack B. Queue C. Tree D. Graph"
```
Expected: a JSON response like `{"answer": "B. Queue"}` — short, direct, no long explanation

- [ ] **Step 5: Verify a real image question**

Using a photo of a multiple-choice question (e.g. `question.jpg` on disk):
```bash
curl -X POST http://localhost:8000/ask \
  -H "X-Device-Id: smoke-test" \
  -F "type=image" \
  -F "image=@question.jpg;type=image/jpeg"
```
Expected: a short, direct JSON answer

- [ ] **Step 6: Verify rate limiting**

Set `DAILY_REQUEST_CAP=1` in `backend/.env`, `docker compose up -d --build`, then send the Step 4 request twice with the same `X-Device-Id`.
Expected: first request `200`, second request `429`

- [ ] **Step 7: Tear down and restore defaults**

```bash
docker compose down
```
Reset `DAILY_REQUEST_CAP` in `.env` back to a real-world value (e.g. `50`).

- [ ] **Step 8: Commit any final config tweaks**

```bash
git add backend/.env.example
git commit -m "chore(backend): finalize env defaults after smoke test"
```
(Skip this step if nothing changed.)
