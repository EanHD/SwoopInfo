# Swoop Intelligence API - The Brain

The production-ready FastAPI backend for Swoop Intelligence's chunk-based automotive service platform.

## Quick Start

```bash
# 1. Install dependencies (creates venv + installs everything)
uv sync

# 2. Activate venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 3. Set up environment
cp .env.example .env
# Edit .env with your Supabase + OpenRouter keys

# 4. Run the server
uvicorn main:app --reload

# 5. Test it
python test_endpoint.py
```

## Architecture

**Chunk-Based System:**
- Every piece of information is an atomic, reusable chunk
- Chunks are lazy-generated on first request
- Cached forever in Supabase
- Combined intelligently based on concern

**2-Model Pipeline (via OpenRouter):**
1. **Grok-4.1-Fast:** Scrape/extract + rewrite (FREE TIER!)
2. **DeepSeek-R1:** RAG navigation + embeddings (~$0.0003/chunk)

**Cost:** <$0.0005 per new chunk (often $0.00 on free tier), $0.00 forever after

## API Endpoints

### GET /
Health check

### POST /api/generate-chunks
Generate and compile chunks for a specific vehicle concern.

**Request:**
```json
{
  "year": "2011",
  "make": "Ford",
  "model": "F-150",
  "engine": "5.0L",
  "concern": "cranks no start, died while driving",
  "dtc_codes": ["P0230"]
}
```

**Response:**
```json
{
  "vehicle_key": "2011_ford_f150_50",
  "concern": "cranks no start, died while driving",
  "chunks_found": 2,
  "chunks_generated": 3,
  "chunks": [...],
  "compiled_html": "<!DOCTYPE html>...",
  "total_cost": 0.00028,
  "generation_time_seconds": 5.2
}
```

## Development

**Install with dev dependencies:**
```bash
uv sync --extra dev
```

**Run linter:**
```bash
ruff check .
ruff format .
```

## Project Structure

```
app/
├── pyproject.toml       # Modern Python project config
├── main.py              # FastAPI app entry point
├── config.py            # Environment variables
├── api/
│   └── generate.py      # Core /generate-chunks endpoint
├── models/
│   ├── chunk.py         # ServiceChunk, ChunkType
│   ├── vehicle.py       # Vehicle, VehicleConcern
│   └── generation.py    # Request/Response models
└── services/
    ├── openrouter.py        # 2-model pipeline client
    ├── chunk_generator.py   # Generate new chunks
    ├── supabase_client.py   # DB operations
    └── document_assembler.py # Compile HTML docs
```

## Database Setup

1. Create Supabase project at https://supabase.com
2. Run SQL from `db_schema.sql` in SQL Editor
3. Copy URL + anon key to `.env`

## Environment Variables

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Next Steps

1. ✅ Test chunk generation with different vehicles
2. ✅ Verify caching (run same request twice)
3. ✅ Check Supabase to see chunks accumulating
4. 📱 Build Flutter app (tree navigation + "Ask Swoop")
5. 🔧 Add admin panel for chunk verification
6. 🔗 Webhook integration for job bookings
