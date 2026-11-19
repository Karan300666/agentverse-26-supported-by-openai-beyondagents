# agentverse-26-supported-by-openai-beyondagents
Hackathon team repository for BeyondAgents - [hackindia-team:agentverse-26-supported-by-openai:beyondagents]


# Clinora: AI voice receptionist for hospitals

Patients log in with their phone number and talk to an AI receptionist that finds doctors, checks availability, and books, reschedules or cancels appointments, in English or Hinglish.

**[Live demo](<vercel-url>)** · **[Demo video](<video-url>)**

> Hackathon project. One fictional hospital, fictional doctors and synthetic patient data. OTP and payment are simulated.

## Results

| Metric | Result |
|---|---|
| Voice response time | **p50 0.65 s · p95 1.04 s** over 120 turns |
| Previous design | ~15 s per turn (multi-step LangGraph pipeline) |
| Eval suite | **233 / 246 runs passed (95%)**: 123 scenarios × 2 runs |
| Automated tests | **All 56 tests pass** |

**How these were measured**
- **Response time:** in the browser, from the end of the patient's speech (`input_audio_buffer.speech_stopped`) to the start of the reply audio (`output_audio_buffer.started`). Percentiles use the nearest-rank method. The previous design's ~15 s is a single measurement of backend processing only, so the real gap was larger.
- **Evals:** the production Realtime model in text mode, with the same instructions and tools, running real tools against the database inside a rolled-back transaction. Graded by code checks (tool calls, database state, data leaks) plus an LLM judge for language and tone.

## How it works

```mermaid
flowchart LR
  B["Browser<br/>mic · speaker · UI"] <-- "WebRTC: audio + events" --> R["OpenAI Realtime model"]
  B -- "HTTPS: session, tool calls" --> A["FastAPI backend"]
  A -- "short-lived key" --> R
  A --> D[("PostgreSQL")]
```

1. The backend checks the patient and creates a **short-lived key**. The real OpenAI key never leaves the server.
2. The browser streams audio to the Realtime model over **WebRTC**. Ordinary conversation never touches the backend.
3. When the model needs data or wants to act, it calls a **tool**. The browser forwards the call to the backend, which validates and runs it, and the model speaks the result.

**Why this design:** the first version sent every turn through a LangGraph pipeline (guardrails, classifier, branch), which meant several sequential LLM calls and about 15 s per turn. Moving to direct tool calling, with all security enforced in the backend, cut response time to 0.65 s (p50).

## Security

The model is never trusted. Every tool call is checked by the backend:

- **Patient-scoped:** the patient comes from the verified session, never from the model. Arguments that try to name a patient are rejected.
- **Strict validation:** every tool has a typed argument schema, and unknown fields are refused.
- **Two-step consent:** booking, cancelling and rescheduling first return a preview and a one-time code. Only a second call with that code, the same session, the same patient and identical arguments changes data. Codes expire after 5 minutes and work once.
- **Business rules:** 20-minute slots, a 7-day booking window, 24-hour notice to change, and no double booking (also enforced in the database).
- **Limits:** 30 tool calls per minute and 200 per call, one active call per patient, and 30-minute sessions.

## Eval suite

123 scenarios across tool use, booking accuracy (20), adversarial attacks (50: prompt injection, fake admin messages, requests for other patients' data, consent bypass, injection hidden in database content), medical safety (16), and English and Hinglish conversations, including mid-call language switching.

```bash
cd backend
uv run python -m evals.run --repeat 2              # full suite
uv run python -m evals.run --category adversarial  # one category
```

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL (Neon), Logfire
**Voice:** OpenAI Realtime API over WebRTC
**Frontend:** Next.js, TypeScript, Tailwind CSS

## Run locally

**Requirements:** Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js, a PostgreSQL database, and an OpenAI API key with Realtime access.

**1. Environment:** create `.env` in the repo root:
```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
OPENAI_API_KEY=...
REALTIME_MODEL=...
CORS_ORIGINS=["http://localhost:3000"]
LOGFIRE_TOKEN=...            # optional
EVAL_JUDGE_MODEL=...         # only for evals
```

**2. Backend**
```bash
cd backend
uv sync
uv run alembic upgrade head
# load demo data: run backend/seed.sql in your database
uv run uvicorn app.main:app --reload
```

**3. Frontend:** create `frontend/.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`, then:
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, choose **Existing patient**, use phone `9876500001` and any 6-digit code.

**Tests:** `cd backend && uv run pytest`. Tests run inside rolled-back transactions, so no data is changed.

## Limitations

- **Demo authentication:** the OTP is simulated and the API identifies patients by phone number. Production would need real OTP and session tokens.
- **Simulated payment,** gated in the browser.
- **In-memory sessions:** voice sessions, confirmation codes and rate limits live in one process, so it runs as a single instance.
- **Evals use text mode and synthetic data,** not live audio from real patients.