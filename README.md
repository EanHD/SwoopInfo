# SwoopInfo — Automotive Data Hub

> **The brain behind Swoop Service Auto**

SwoopInfo is the central data platform that powers the entire Swoop ecosystem. It collects, verifies, and serves automotive intelligence: vehicles, services, parts, labor times, torque specs, TSBs, and more.

**Vision:** Build the most accurate automotive API by continuously curating data throughout our journey.

---

## Core Philosophy

1. **Own the Data** — Every API call becomes permanent, verified data. Once cached, cost is $0 forever.
2. **Safety Over Cleverness** — Wrong specs are dangerous. Never serve unverified data.
3. **Lazy Generation** — Generate on-demand, cache forever.
4. **Cost-Efficient** — Expensive models only where necessary.

---

## Current Features

- **Chunk-Based Architecture** — Atomic, reusable data (torque specs, fluid capacities, procedures)
- **QA Pipeline** — Multi-stage verification before data is served
- **Vehicle Validation** — CarQuery integration prevents hallucinated Y/M/M/E combos
- **TSB/Recall Data** — NHTSA integration for safety bulletins
- **Offline-First** — Isar local cache with Supabase sync
- **Real-Time Generation** — On-demand content with cost tracking

---

## Architecture

```text
SwoopInfo/
├── app/                  ← FastAPI backend (Python)
│   ├── api/              ← REST endpoints (chunks, generate, qa, chat)
│   ├── models/           ← Pydantic models (chunk, vehicle, generation)
│   ├── services/         ← Business logic
│   │   ├── supabase_client.py    ← Database operations
│   │   ├── chunk_generator.py    ← Content generation
│   │   ├── qa_agent.py           ← Verification pipeline
│   │   ├── nhtsa.py              ← TSB/recall data
│   │   ├── carquery.py           ← Vehicle validation
│   │   └── openrouter.py         ← LLM abstraction
│   └── tests/            ← Backend tests
├── lib/                  ← Flutter frontend (Dart)
│   ├── screens/          ← UI screens
│   ├── providers/        ← Riverpod state
│   └── widgets/          ← Reusable components
├── assets/data/          ← nav_tree.json, service_templates.json
├── backend/diagrams/     ← Diagram generation (coming soon)
└── scripts/              ← Utility scripts
```

---

## Quick Start

**Backend (required for all Swoop apps):**

```bash
cd app && source .venv/bin/activate && uvicorn main:app --reload --port 8000
```

**Frontend (optional admin UI):**

```bash
flutter run -d web-server --web-port=9000
```

---

## Data Sources

| Source | Status | Data |
|--------|--------|------|
| NHTSA | ✅ Active | TSBs, recalls, complaints |
| CarQuery | ✅ Active | Vehicle Y/M/M/E validation |
| OpenRouter | ✅ Active | LLM content generation |
| O'Reilly API | ⏳ Pending | Parts catalog (awaiting approval) |
| VehicleDatabases | 📋 Planned | Labor times, procedures |

---

## Deployment

SwoopInfo is designed to be deployed as separate frontend and backend services.

### Backend (API) → Vercel

The FastAPI backend is Vercel-ready:

```bash
cd app
vercel deploy
```

**Environment Variables (set in Vercel dashboard):**
- `SUPABASE_URL` — Your Supabase project URL
- `SUPABASE_ANON_KEY` — Supabase anonymous key
- `OPENROUTER_API_KEY` — OpenRouter API key for LLM
- `TAVILY_API_KEY` — Tavily search API (optional)

### Frontend (Admin UI) → Flutter Web

Can be deployed anywhere that serves static files:

```bash
flutter build web --release
# Deploy build/web/ to Vercel, Cloudflare Pages, etc.
```

### Recommended Production Setup

| Service | Platform | Domain |
|---------|----------|--------|
| API | Vercel | api.swoopinfo.com |
| Admin UI | Vercel | swoopinfo.com |
| Database | Supabase | (managed) |

---

## Coming Soon

- **Parts Integration** — O'Reilly API for automatic parts lookup
- **Belt Routing Diagrams** — Visual serpentine layouts
- **Wiring Diagrams** — Component-level schematics
- **Diagnostic Flowcharts** — Interactive decision trees

---

## Tech Stack

- **Backend:** FastAPI (Python) + Supabase (PostgreSQL)
- **Frontend:** Flutter (iOS, Android, Web)
- **State:** Riverpod
- **Cache:** Isar (offline-first)
- **LLM:** OpenRouter (configurable)

---

## Documentation

- **[AGENTS.md](./AGENTS.md)** — Agent guidelines and QA rules
- **[../ARCHITECTURE.md](../ARCHITECTURE.md)** — Full system architecture

---

*Built for professional technicians who demand accuracy.*
