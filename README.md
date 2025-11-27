# Swoop Intelligence

**Launch Date: November 28, 2025**

Professional automotive diagnostic intelligence platform. Every service document looks like it came from a factory service manual.

## Current Features

- **Verified Service Data** — Multi-source consensus with QA pipeline
- **Factory Manual Styling** — Professional navy blue aesthetic with proper step boxes, warnings, and specifications
- **Vehicle Coverage** — Validated year/make/model/engine combinations
- **Offline-First** — Isar local cache with Supabase sync
- **Real-Time Generation** — On-demand chunk creation with cost tracking

## Architecture

```
swoopinfo/
├── app/                  ← FastAPI backend (Python)
│   ├── api/              ← REST endpoints
│   ├── models/           ← Pydantic models
│   ├── services/         ← Business logic
│   └── tests/            ← Backend tests
├── lib/                  ← Flutter frontend (Dart)
│   ├── screens/          ← UI screens
│   ├── providers/        ← Riverpod state
│   ├── services/         ← API clients
│   └── widgets/          ← Reusable components
├── backend/diagrams/     ← Diagram generation (disabled, coming next update)
├── assets/data/          ← nav_tree.json, service_templates.json
└── scripts/              ← Utility scripts
```

## Quick Start

**Backend:**
```bash
cd app && source .venv/bin/activate && uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
flutter run -d web-server --web-port=9000
```

## Coming Next Update

- **Belt Routing Diagrams** — Visual serpentine belt layouts with pulley positions
- **Wiring Diagrams** — Component-level electrical schematics
- **Diagnostic Flowcharts** — Interactive decision trees

## Tech Stack

- **Frontend:** Flutter (iOS, Android, Web)
- **Backend:** FastAPI + Supabase
- **State:** Riverpod
- **Cache:** Isar
- **LLM:** Configurable (OpenRouter/local)

---

*Built for professional technicians who demand accuracy.*
