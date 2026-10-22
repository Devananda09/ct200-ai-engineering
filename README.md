# CardioTrack CT-200 AI Engineering System

A high-fidelity document intelligence, versioning, hierarchy reconstruction, and grounded QA generation platform for CardioTrack CT-200 Blood Pressure Monitor technical manuals (`v1` and `v2`).

---

## 1. Architecture Overview

```text
               CardioTrack CT-200 Manual PDFs
                  v1.pdf           v2.pdf
                    │                │
                    ▼                ▼
            ┌───────────────────────────────────┐
            │       PDF Parser (PyMuPDF)        │
            │  • Block & layout extraction      │
            │  • Structural table extraction    │
            │  • Scanned/image-only detection   │
            └─────────────────┬─────────────────┘
                              │
                              ▼
            ┌───────────────────────────────────┐
            │     Document Understanding &      │
            │     Hierarchy Construction        │
            │  • Regex section heading matcher  │
            │  • Missing parent level fallback  │
            │    (e.g., 2.1.1.1 attaches to 2.1)│
            └─────────────────┬─────────────────┘
                              │
                              ▼
            ┌───────────────────────────────────┐
            │     Structured Document Tree      │
            │  • Versioned DocumentNodes        │
            │  • Deterministic SHA-256 Hashes   │
            │  • Attached specs and tables      │
            └─────────┬─────────────────┬───────┘
                      │                 │
                      ▼                 ▼
          ┌─────────────────────┐   ┌───────────────────────────┐
          │     v1 ↔ v2 Diff    │   │  SQLAlchemy + SQLite DB   │
          │  • Added sections   │   │  • document_versions      │
          │  • Removed sections │   │  • document_nodes         │
          │  • Modified nodes   │   │  • selections (immutable) │
          │  • Unchanged nodes  │   │  • generated_qa           │
          └───────────┬─────────┘   └─────────────┬─────────────┘
                      │                           │
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │      FastAPI Backend      │
                      └─────────────┬─────────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             ▼                      ▼                      ▼
      Browse Endpoints      Keyword Search / RAG    Version-Pinned Selection
     (/tree, /nodes, etc.)   (/query, /search)       (/selections)
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │     LLM Provider Layer      │
                                            │  • Gemini 1.5 Flash (Key)   │
                                            │  • Deterministic Fallback   │
                                            └──────────────┬──────────────┘
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │ Pydantic Validation & Retry │
                                            │  • QAItem (3–5 test ideas)  │
                                            │  • Bounded retry (max 3)    │
                                            └──────────────┬──────────────┘
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │   Persist to generated_qa   │
                                            │   (tied to content_hash)    │
                                            └──────────────┬──────────────┘
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │ Staleness & Impact Analysis │
                                            │ (current, stale, removed)   │
                                            └─────────────────────────────┘
```

---

## 2. Project Structure

```text
ct200-ai-engineering/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py             # REST API routes (browse, diff, selections, QA, impact)
│   ├── config.py                 # Pydantic BaseSettings (.env loading)
│   ├── db.py                     # SQLAlchemy models & SQLite engine
│   ├── main.py                   # FastAPI app with lifespan initialization
│   ├── models/
│   │   ├── __init__.py
│   │   └── domain.py             # Domain models (Overview, Citations, Diffs)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── api_models.py         # Request and response Pydantic models
│   └── services/
│       ├── __init__.py
│       ├── diff_service.py       # Cross-version comparator (v1 vs v2)
│       ├── llm_provider.py       # LLM abstraction (Gemini + Deterministic fallback)
│       ├── parser_service.py     # Document normalization & section extraction
│       └── rag_service.py        # Chunking & keyword retrieval engine
├── data/
│   ├── ct200_manual.pdf          # v1 Technical Manual
│   └── ct200_manual_v2.pdf       # v2 Technical Manual
├── parser/
│   ├── __init__.py
│   ├── chunker.py                # Semantic & token chunking utilities
│   ├── hierarchy.py              # Tree builder with missing parent resolution
│   ├── models.py                 # Core DocumentNode, Section, and Chunk dataclasses
│   └── pdf_parser.py             # PyMuPDF block & table extraction
├── scripts/
│   ├── __init__.py
│   └── ingest_manuals.py         # CLI ingestion pipeline script
├── tests/
│   ├── __init__.py
│   ├── test_api.py               # API endpoints tests
│   ├── test_hierarchy_and_hashing.py # Table extraction, irregular tree & hashing tests
│   ├── test_ingestion_script.py  # CLI ingestion integration tests
│   ├── test_llm_generation.py    # LLM schemas, fallback & bounded retry tests
│   ├── test_parser.py            # PDF parsing & comparator unit tests
│   ├── test_selection_and_db.py  # DB models & duplicate selection policy tests
│   └── test_staleness_and_impact.py # QA lifecycle, staleness & impact tests
├── .env.example                  # Template configuration file
├── .gitignore                    # Version control ignore rules
├── APPROACH.md                   # Architectural methodology & Decision Log
├── Dockerfile                    # Containerization setup
├── docker-compose.yml            # Docker compose configuration
├── requirements.txt              # Production Python dependencies
└── README.md                     # Documentation
```

---

## 3. Setup & Execution

### Local Python Environment
Prerequisites: Python 3.10+ (tested with Python 3.13)

```bash
# 1. Clone repository and navigate to root
cd ct200-ai-engineering

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Run manual ingestion (parses PDFs, builds trees, seeds SQLite database)
python -m scripts.ingest_manuals

# 6. Start the FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive Swagger UI will be available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 4. Docker Execution

The application is containerized with a non-root security profile. To prevent port collisions with other local services on port 8000, map host port **8001** to container port **8000**:

```bash
# Build the Docker image
docker build -t ct200-ai-engineering .

# Run the container mapping host port 8001
docker run --rm -p 8001:8000 ct200-ai-engineering
```

Verify in your browser or curl:
- **Swagger Documentation**: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)
- **Health Check**: `curl http://127.0.0.1:8001/api/v1/health`

---

## 5. Environment & LLM Configuration

The system is configured via environment variables or a `.env` file:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite:///./ct200.db` | SQLAlchemy SQLite database connection string |
| `GEMINI_API_KEY` | *(empty)* | Optional Google Gemini API key |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `DOCS_V1_PATH` | `data/ct200_manual.pdf` | Path to v1 manual PDF |
| `DOCS_V2_PATH` | `data/ct200_manual_v2.pdf`| Path to v2 manual PDF |
| `APP_PORT` | `8000` | Port for FastAPI server |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Deterministic Fallback & Zero-Cost Execution
- **No API key is required.**
- If `GEMINI_API_KEY` is unset or empty, the system automatically uses `DeterministicFallbackProvider`.
- The fallback analyzes numerical thresholds, operational parameters, and error codes in the selected section to deterministically produce 3–5 fully compliant, schema-validated `QAItem` test ideas.
- **Integrity Guarantee**: The response payload explicitly identifies the provider used (`deterministic-fallback` vs `gemini (gemini-1.5-flash)`). The system never claims external AI was used when it was not.

---

## 6. Core Features & Capabilities

### A. PDF Parsing & Hierarchy Construction
- **Table Extraction**: Employs PyMuPDF table finders to extract structured tables (Specifications on Page 2, Error Codes on Page 4).
- **Missing Parent Level Resolution**: Handles non-uniform section numberings gracefully (e.g., Section `2.1.1.1` safely attaches to parent `2.1` when `2.1.1` does not exist).
- **Scanned Document Detection**: Emits clear warnings if an image-only/scanned PDF without extractable text is provided.

### B. Versioning & Deterministic SHA-256 Hashing
- Every node has a cryptographic SHA-256 content hash computed from its normalized body text.
- Re-selecting identical content yields the exact same hash across sessions.
- Node identity (`node_id`) is strictly decoupled from content state (`content_hash`).

### C. Version Diff Analysis
Detects actual changes between `v1` and `v2`:
- **Added**: Section `5.3 Data Export`
- **Modified**:
  - Section `2.1.1.1`: Battery life modified from 300 to 250 cycles.
  - Section `3.2`: Cuff inflation increment modified from 40 mmHg to 30 mmHg.
  - Section `4.2`: Error codes table introduces E6 (Bluetooth sync failure) and changes E3 auto-deflation from 2.0s to 1.5s.
  - Section `4.3`: Low battery threshold modified from 15% to 10%.
- **Unchanged**: Section `1.0 Overview`, Section `2.2 Environmental Specs`, etc.

### D. Version-Pinned Selection & Duplicate Selection Policy
- `POST /api/v1/selections` records the exact content and SHA-256 hash at selection time.
- **Duplicate Policy**: Selecting the same `(version, node_id, content_hash)` multiple times is idempotent and returns the existing selection record without polluting the database with redundant rows. Selecting a modified node creates a distinct record.

### E. LLM QA Generation with Bounded Retries
- Validates all generated outputs against Pydantic schemas:
  - `QAItem`: `title`, `description`, `expected_result`, `source_reference`.
  - `QAResult`: `node_id`, `version`, `content_hash`, `generated_at`, `provider`, `test_ideas` (enforces min 3, max 5).
- If the model produces malformed JSON or incorrect counts, the service executes a bounded retry (up to 3 attempts). If all retries fail, a controlled error is returned without persisting corrupt output.

### F. Staleness & Impact Detection
- `GET /api/v1/manuals/{version}/nodes/{node_id}/impact`:
  - `status = "current"`: Current node hash equals generation hash. Test ideas remain valid.
  - `status = "stale"`: Node was modified between versions. Hash mismatch detected; review/regeneration required.
  - `status = "removed"`: Node does not exist in target version; test ideas impacted.
  - `status = "untracked"`: Node exists in manual but has no generated QA yet.

---

## 7. REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health, environment, and manual load status |
| `GET` | `/api/v1/manuals` | List ingested manuals and overview metrics |
| `GET` | `/api/v1/manuals/{version}` | Detailed manual metadata, sections, parameters, error codes |
| `GET` | `/api/v1/manuals/{version}/sections` | Flat list of extracted sections for a manual |
| `GET` | `/api/v1/manuals/{version}/tree` | Hierarchical document tree with content hashes |
| `GET` | `/api/v1/manuals/{version}/parameters` | Extracted technical specifications |
| `GET` | `/api/v1/manuals/{version}/errors` | Extracted error codes and device behaviors |
| `GET` | `/api/v1/manuals/{version}/nodes/{node_id}` | Node details, body text, content hash, children list |
| `GET` | `/api/v1/manuals/{version}/nodes/{node_id}/children` | Direct children of a specified node |
| `GET` | `/api/v1/manuals/{node_id}/changes` | Node-level cross-version change comparison (v1 vs v2) |
| `GET` | `/api/v1/diff` | Document-level diff (added, removed, modified, unchanged) |
| `GET` | `/api/v1/manuals/{version}/search?q=...` | Keyword search with citations, snippets, and relevance scores |
| `POST` | `/api/v1/query` | RAG query interface returning answers with citations |
| `POST` | `/api/v1/selections` | Version-pinned node selection with duplicate policy |
| `POST` | `/api/v1/generate-qa` | Generate 3–5 grounded test ideas with bounded retry |
| `GET` | `/api/v1/qa` | List all persisted generated QA records with staleness status |
| `GET` | `/api/v1/qa/{node_id}` | Retrieve persisted QA and staleness for a specific node |
| `GET` | `/api/v1/manuals/{version}/nodes/{node_id}/impact` | Check staleness & impact status against target version |

---

## 8. Automated Testing

The repository contains comprehensive unit and integration tests across all modules.

To execute the test suite:
```bash
pytest -q
```

**Results**: 31 passed tests covering:
- PDF layout extraction and PyMuPDF table parsing
- Structural irregularity handling (e.g. 2.1.1.1 without 2.1.1 parent)
- Deterministic SHA-256 node content hashing
- v1 vs v2 version comparison (added 5.3, modified 2.1.1.1, unchanged 1.0)
- Database persistence (versions, nodes, selections, QA)
- Duplicate selection policy enforcement
- Structured Pydantic schema validation (3–5 test ideas)
- Deterministic fallback provider generation
- LLM bounded retry logic on malformed responses or invalid counts
- Staleness and impact detection lifecycle (`current`, `stale`, `removed`)
- CLI ingestion script execution (`python -m scripts.ingest_manuals`)
- All FastAPI endpoints and response formats
