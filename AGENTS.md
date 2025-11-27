# Swoop Intelligence: Agent & Technology Strategy  
**Version v6 – CURRENT PRODUCTION DESIGN**

This document describes how Swoop Intelligence **actually works today** and the rules agents must follow when changing or extending it.

If code, database schema, or environment variables disagree with this document, **the code + schema are the source of truth**. This file is a high-level map, not permission to invent new systems.

---

## I. Core Philosophy

1. **Own the Data**  
   Every API call and AI inference is an investment into a permanent, curated dataset (the `chunks` table). Once cached and verified, cost for that result is effectively $0 forever.

2. **Safety Over Cleverness**  
   Wrong specs are worse than no specs. It is **never allowed** to serve unverified or quarantined chunks to technicians.

3. **Lazy Generation**  
   Data is generated on-demand, then cached and re-used. We do not pre-generate the entire universe.

4. **Cost-Efficient Reasoning**  
   Expensive models are used sparingly and only where necessary. All model usage is abstracted behind our backend; agents must not hard-code specific vendors into frontend code.

---

## II. Current Production Stack

- **Frontend:** Flutter (iOS, Android, Web)
- **Local Cache (Client):** Isar (offline-first)
- **State Management:** Riverpod
- **Backend:** FastAPI (Python)
- **Admin / QA Panel:** Flutter Web
- **Primary DB:** Supabase (PostgreSQL)
  - Canonical table for content: **`chunks`**
- **LLM Access:**  
  - Configurable via environment (e.g. OpenRouter / direct vendor APIs / local models)
  - Models are examples, not hard requirements. Agents must read env/config before assuming a provider.

> Rule: Agents must not introduce new databases or tables without a migration.  
> The only canonical chunk table is **`public.chunks`**.

---

## III. Chunk-Based Architecture (Still The Moat)

We do **not** store one big HTML blob per page.  
We store **atomic, reusable chunks**. One row = one chunk of knowledge.

**Examples (conceptual – actual schema is in the DB):**

| Chunk Type       | Example Key                     | Content (body)                                   |
|------------------|----------------------------------|--------------------------------------------------|
| `fluid_capacity` | `2011_F150_50_engine_oil`       | 7.7 qt, 5W-20, FL-500S filter                    |
| `torque_spec`    | `2011_F150_50_front_calipers`   | 26 ft-lb front, 20 ft-lb rear                    |
| `part_location`  | `2011_F150_50_crank_sensor`     | Behind starter, passenger side                   |
| `known_issues`   | `2011_F150_50_no_start`         | Common failures, TSB refs                        |
| `removal_steps`  | `2011_F150_50_water_pump`       | Numbered list of steps                           |
| `wiring_diagram` | `2011_F150_50_ignition_coil`    | Diagram path + metadata                          |
| `diag_flow`      | `p0301_50_coyote`               | Decision tree / flowchart                        |

All chunks are tagged with:

- vehicle identity (year/make/model/engine / VIN-like key)
- path in the nav tree (e.g. `systems/engine/mechanical/repairs/oil_change`)
- chunk type + keywords

---

## IV. QA & Trust Model (NON-NEGOTIABLE)

This section replaces older “verification_status only” logic.

### 1. Core Fields (in `chunks`)

- `qa_status`  
  - `pending` – not yet fully checked  
  - `pass` – passed QA checks  
  - `fail` – QA found issues  

- `verified_status`  
  - `unverified` – default for new chunks  
  - `candidate` – passed QA at least once  
  - `verified` – passed QA on multiple days; considered trusted  
  - `banned` – repeatedly failed; must not be auto-used  

- `visibility`  
  - `quarantined` – generated but not safe to show yet  
  - `safe` – allowed to be served to UI  
  - `banned` – must never be served  

- Legacy field: `verification_status`  
  - Used only as a compatibility output for older UI code.  
  - It is derived from `qa_status` + `verified_status` and **must not be the source of truth**.

> Agents must use `qa_status`, `verified_status`, and `visibility` when reasoning about trust – never rely solely on `verification_status`.

### 2. Lifecycle

**New chunk (cache miss or on-demand generation)**

- inserted with:  
  - `qa_status = "pending"`  
  - `verified_status = "unverified"`  
  - `visibility = "quarantined"`

**QA Stage 1–2 – Detection + Repair**

- Rule-based checks + optional LLM analysis decide `qa_status` = `pass` or `fail`.
- Failing chunks may be regenerated (up to a capped number of attempts).

**QA Stage 5 – Promotion**

- First successful QA pass: `unverified → candidate`
- Successful QA on a later day: `candidate → verified`
- If a verified chunk ever fails QA: `verified → banned`

**Visibility Rules**

- `visibility = "safe"` ONLY if:
  - `qa_status = "pass"` **and**
  - `verified_status ∈ {"candidate", "verified"}` **and**
  - not banned
- `visibility = "quarantined"` means the chunk must **never** be shown to users.
- `verified_status = "banned"` means the chunk is effectively dead until manual intervention.

### 3. UI Rules (High-Level)

Agents modifying Flutter code MUST obey these:

- Never show data where `visibility != "safe"`.
- Never label anything “Verified” if:
  - `verified_status != "verified"` OR
  - `qa_status != "pass"` OR
  - `verified_status = "banned"` OR `qa_status = "fail"`.
- If a chunk is quarantined or banned:
  - Backend should return a structured “unavailable / verification in progress” payload, **not** incorrect or placeholder content.

This is how we avoid showing F-150 oil changes on Aveos, etc.

---

## V. Data Sources (Target Strategy)

This section describes the **intended** source stack. Agents must check for environment flags and credentials before assuming any of these are live.

1. **NHTSA (Free)**  
   - TSBs, recalls, some safety data  
   - High-trust, but still passes through QA pipeline

2. **CarQuery (Free)**  
   - Vehicle config validation (year/make/model/engine combos)  
   - Prevents hallucinated vehicles

3. **Licensed Data Provider (e.g. VehicleDatabases.com)**  
   - Labor times, repair procedures, part numbers, specs  
   - When integrated, these chunks may be treated as **high-trust**:
     - they still flow through QA, but rules may auto-mark them as pass unless contradictions are found.

4. **Public Manuals, Forums, Brave Search / Web**  
   - Used as a fallback and for additional color  
   - Never the sole authority for safety-critical specs  
   - Safety-critical chunks from these sources remain `pending` until vetted.

> Important:  
> If a provider/API is not configured in the environment, agents must treat it as **not available** and skip any integration logic that assumes its presence.

---

## VI. Model Strategy (Abstract, Not Hard-Coded)

We support a **2-layer model plan**, but individual model names (Grok, DeepSeek, etc.) are examples, not permanent dependencies.

- **Scrape / Summarize / Rewrite Layer**  
  - Fast, cheap model(s) or local LLM.  
  - Used for transforming raw docs into structured chunks.

- **Reasoning / RAG / Navigation Layer**  
  - More capable model(s), used for:
    - Selecting relevant chunks
    - Synthesizing diagnostic flows
    - Interpreting complex queries

Model selection is governed by configuration/env; agents should read a config file (e.g. `model_config.yaml` or environment variables) instead of hard-coding `"grok-4.1-fast"` etc.

Cost targets remain:

- **New chunk generation (cache miss):** sub-penny  
- **Cache hit:** database lookup only, effectively $0

---

## VII. Lazy Chunk Generation & On-Demand Behavior

### Cache Miss Flow

1. UI or backend requests a chunk for a given vehicle + path.
2. Backend looks up `chunks`:
   - If found & `visibility="safe"` → return.
   - If found but quarantined → return “verification in progress / unavailable”.
   - If not found → `generate_on_demand`:
     - Create stub chunk with `qa_status="pending"`, `visibility="quarantined"`.
     - Schedule QA pipeline to process it.
     - Return “verification in progress / unavailable” response.

### Background Pre-Generation

When a vehicle is first viewed, a background PreGenerator may request a **baseline set** of chunks (oil, torque, etc.). These are still quarantined until QA passes, but this makes future requests faster.

---

## VIII. Human Verification (Optional Layer)

When a human verification queue is in use:

- Certain chunk types (torque, brake procedures, airbag, major safety work) can be flagged for manual review.
- A human can:
  - Approve (which may set `verified_status` to `verified` faster)
  - Edit and correct
  - Mark as banned/manual-only

The human layer is an enhancement on top of the automated QA pipeline, not a replacement.

---

## IX. Production Status Notes (Reality Check)

- Canonical table: `public.chunks`
- Legacy tables/views like `service_chunks` and `chunk_verification_summary` have been removed or archived.
- QA pipeline (Stages 1–7) is implemented:
  - Detection, repair, promotion, quarantine, and continuous daily QA are active.
- Frontend is allowed and expected to be in active development;  
  **the old rule “do not start Flutter until X tests pass” is no longer valid and has been retired.**

Agents must:

- Respect the existing QA + trust model
- Avoid re-introducing legacy tables or bypassing the QA pipeline
- Prefer incremental, backwards-compatible changes

---

## X. UI / UX Philosophy (Still Non-Negotiable)

*(This section is mostly aesthetic; it did not cause breakage and is left structurally the same, with minor clarifications.)*

- Dark-mode, high-clarity, “Apple-level calm” interface.
- One primary action per screen.
- Text readable from a distance in a dirty shop.
- Accent color is for interaction / progress only, not static chrome.
- No amateur vibes: no harsh shadows, no gradients, no rainbow UI.

All detailed typography, spacing, and component rules from the prior version still stand. Agents should treat those as **strong guidelines** for Flutter component design, but must not block functional work if design polish is still in progress.

---

## XI. How Agents Should Use This File

1. Treat this as **constraints and invariants**, not a wishlist.  
2. Never invent new tables, enums, or fields based solely on this doc; always cross-check with the live schema.  
3. Never bypass `qa_status / verified_status / visibility` when serving content.  
4. When in doubt, favor:
   - returning “unavailable / verification in progress”  
   - over returning possibly wrong data.

If an agent is about to make a change that conflicts with this document, it must explain why and propose an update to `AGENTS.md` as part of its work.

To run backend : """cd /app && source .venv/bin/activate && uvicorn main:app --reload --port 8000"""

Note: you need to run backend in background or in another terminal

To run frontend : flutter run -d web-server --web-port=9000
