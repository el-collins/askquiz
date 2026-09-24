# AskQuiz MVP — Design Spec

Date: 2026-09-24

## 1. Purpose & Success Criteria

AskQuiz lets a student submit a question — typed or photographed — and get back a short, direct answer (e.g. "B — Encapsulation" plus at most one short explanatory line), not a long ChatGPT-style essay. The product's differentiator is speed and terseness, aimed at exam/homework prep.

Success for the MVP:
- A student can type a question or photograph a multiple-choice/short question and get a correct, terse answer back in a few seconds.
- The app can be used with zero signup friction (no login).
- The whole system runs on infrastructure the user already controls (Coolify + Docker Compose) at negligible cost, sized for dozens to low hundreds of users.

## 2. Scope

**In scope for MVP:**
- Text question input
- Image question input (photo of a question, e.g. multiple choice)
- Anonymous, device-based identity (no accounts)
- Per-device daily rate limiting
- Android build (Expo/React Native)
- FastAPI backend, Postgres for rate-limit state, deployed via Docker Compose on Coolify

**Explicitly out of scope for MVP (deferred):**
- Voice input / speech-to-text
- User accounts / login / OAuth
- Question/answer history (app is stateless — nothing is persisted beyond rate-limit counters)
- OCR fallback pipeline for images the vision model can't parse (the vision model's own "can't read this" response is surfaced as-is instead)
- Token/response streaming (SSE or chunked) — full response returned at once
- Monetization / paid tier
- iOS build (same codebase, but not built/published yet)
- Redis or any dedicated rate-limiting service (Postgres counters are sufficient at this scale)

## 3. Architecture

```
┌─────────────────────┐
│  Expo / React Native │  (Android build)
│  - Text input        │
│  - Camera/image pick  │
└──────────┬───────────┘
           │ HTTPS, X-Device-Id header
           ▼
┌─────────────────────────────┐
│   FastAPI backend (Docker)   │
│   POST /ask                  │
│   - validates request        │
│   - checks/increments        │
│     rate limit (Postgres)    │
│   - routes by type           │
└──────────┬───────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  text          image
     │           │
     ▼           ▼
┌─────────┐  ┌──────────────┐
│ Groq LLM │  │ Groq Vision  │
│ (text)   │  │ model        │
└─────────┘  └──────────────┘
           │
           ▼
   Short JSON answer
           │
           ▼
     Back to app
```

Deployed as two services in one Docker Compose stack on Coolify: `api` (FastAPI) and `db` (Postgres, with a persistent volume managed by Coolify).

## 4. Components

### 4.1 Mobile app (Expo / React Native, Android)

- Single chat-style screen: text input, camera/gallery picker button, answer display area
- On first launch, generates a UUID (e.g. via `expo-crypto`), persists it in `AsyncStorage`, and sends it as an `X-Device-Id` header on every backend request
- No login flow, no locally persisted Q&A history — the screen only shows the current/most recent exchange
- Talks only to the backend's `/ask` endpoint; never calls Groq directly, and never holds a Groq API key

### 4.2 Backend (FastAPI)

- Single `POST /ask` endpoint
  - Request: `{type: "text" | "image", content: ...}` — for `text`, `content` is the question string; for `image`, the request is multipart with the image file
  - Response: `{answer: string}`
- Request flow:
  1. Pydantic validates the request shape (rejects malformed/empty input with `400` before any Groq call)
  2. Reads `X-Device-Id` header, checks/increments today's usage count for that device in Postgres; rejects with `429` if over the daily cap
  3. Routes to `ask_text(content)` or `ask_image(image_bytes)`, both of which call Groq with a fixed system prompt enforcing low temperature and terse output (≤30–50 words, direct answer, no preamble)
  4. Returns the answer as JSON
- Holds the Groq API key as a server-side environment variable only
- No question/answer content is persisted anywhere — only rate-limit counters are written to Postgres

### 4.3 Database (Postgres)

Single table for rate limiting, no users table, no Q&A table:

```sql
CREATE TABLE usage (
  device_id   TEXT NOT NULL,
  date        DATE NOT NULL,
  request_count INT NOT NULL DEFAULT 0,
  PRIMARY KEY (device_id, date)
);
```

Checked/incremented atomically per request; a device's cap resets naturally each day since counters are keyed by `(device_id, date)`.

### 4.4 AI (Groq)

- **Text:** a fast Groq-hosted text model, called with the terse/low-temperature system prompt
- **Image:** a Groq vision-capable model, sent the image directly (no OCR step) with the same terse system prompt; if the model can't parse the image, its own response (e.g. "I can't read this") is returned as-is — no OCR fallback in MVP
- **Voice:** not implemented in MVP

## 5. Data Flow

**Text question:**
```
app → POST /ask {type: text, content} + X-Device-Id
    → backend checks/increments rate limit
    → Groq text model
    → {answer}
    → app renders it
```

**Image question:**
```
app → POST /ask (multipart image) + X-Device-Id
    → backend checks/increments rate limit
    → Groq vision model
    → {answer}
    → app renders it
```

Both paths are synchronous request/response. No streaming, no background jobs, no queues.

## 6. Error Handling

| Condition | Backend response | App behavior |
|---|---|---|
| Rate limit exceeded | `429` | "You've hit today's limit." |
| Groq call errors or times out (15s request-level timeout) | `502` / `504` | Generic "Couldn't get an answer, try again" with a retry button; no server-side auto-retry |
| Malformed/empty request | `400` (Pydantic validation, before any Groq call) | Input validation feedback in the UI |
| Vision model can't parse the image | `200` with the model's own "can't understand" answer | Answer area shows that response as-is |

## 7. Testing

- **Backend:** unit tests for the rate-limit logic (increment / cap / daily reset via the `(device_id, date)` key) and for request validation; integration test for `/ask` with the Groq client mocked out
- **Mobile:** manual testing on a real Android device/emulator for the text and camera/image flows — no automated mobile test framework at this stage
- **Pre-ship manual smoke test:** run a handful of real exam-style text and photographed multiple-choice questions through the deployed backend and confirm answer correctness, format, and perceived latency

## 8. Deployment

- Docker Compose stack with two services (`api`, `db`), deployed on Coolify
- Coolify manages the Postgres persistent volume
- Groq API key and other secrets supplied via Coolify environment variables, never committed to the repo

## 9. Explicitly Deferred (Fast-Follow Candidates)

These were discussed but intentionally excluded from MVP scope; each can be added later without restructuring `/ask`:
- Voice input (record → Groq Whisper STT → text flow → same answer path)
- Response streaming (SSE/chunked) if perceived latency becomes a concern
- OCR fallback pipeline for images the vision model can't read
- User accounts, cross-device history
- Redis-backed rate limiting if scale grows past what Postgres counters comfortably handle
- iOS build and publish
- Monetization / paid tier
