# CardioTrack CT-200 AI Engineering Approach & Architecture Document

## 1. Problem Understanding & Objective

The CardioTrack CT-200 Blood Pressure Monitor technical and user manuals are engineering/regulatory documents delivered as PDFs (`v1` and `v2`). Regulatory engineering systems, medical device testing, and QA teams need to:
1. Parse unstructured or semi-structured PDF manuals into high-fidelity, hierarchical document representations (preserving titles, headings, sections, subsections, tables, and device specifications).
2. Maintain rigorous, deterministic document versioning across manual revisions (`v1` and `v2`), identifying added, removed, modified, and unchanged logical nodes.
3. Provide browsable, searchable REST APIs for sections, nodes, children, parameters, error codes, and diff comparisons.
4. Support version-pinned selection where a caller selects an exact version and node ID to retrieve immutable content and cryptographic SHA-256 content hashes.
5. Provide an LLM QA generation pipeline grounded strictly in the selected node content, validated using structured Pydantic schemas (3–5 test ideas), backed by bounded retry on malformed outputs, and persisting to SQLite.
6. Support deterministic offline fallback when no external LLM credentials exist, ensuring the entire system is runnable locally and in Docker without paid services.
7. Implement staleness and impact detection to alert QA teams when manual changes (e.g., v1 battery 300 cycles -> v2 250 cycles, or added/removed sections) invalidate previously generated test ideas.

---

## 2. Conceptual Architecture & Data Flow

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

## 3. PDF Parsing & Document Understanding

### PyMuPDF Extraction & Layout Analysis
- Extraction uses `pymupdf` (`fitz`) to extract structured text blocks (`page.get_text("blocks")`), preserving line positions, bounding box coordinates (`x0, y0, x1, y1`), and sequential page numbers.
- **Table Recognition**: PyMuPDF's built-in table finder (`page.find_tables()`) identifies tabular sections, extracting column headers and structured 2D row data (e.g. Page 2 General Specifications table and Page 4 Error Codes table).
- **Scanned / Image-Only Detection**: If a PDF page contains zero text blocks or empty text length across all pages while containing embedded raster images, the parser flags the document as scanned/image-only and issues a clear diagnostic warning rather than silently producing an empty document.

---

## 4. Hierarchy Construction & Irregularity Handling

### Structural Irregularity Handling
Medical device manuals contain non-uniform numbering schemes. In the CT-200 manual, Section `2.1.1.1` (Battery Specifications) exists without an intermediate `2.1.1` parent section header.
- **Algorithm (`_find_existing_parent`)**:
  Given a section number string with dot-separated parts (e.g., `["2", "1", "1", "1"]`), the algorithm steps backward through successively shorter prefix slices:
  1. Candidate `2.1.1` -> not found in indexed node dict.
  2. Candidate `2.1` -> found!
  3. Parent is assigned to `2.1`, and `2.1.1.1` is appended as a direct child of `2.1`.
- This ensures safe, deterministic tree construction without orphaned nodes or crashed parsers.

---

## 5. Versioning Strategy, Node Identity & Content Hashing

### Stable Logical Identifiers
- Each node maintains a stable logical `node_id` (e.g., `"1"`, `"2.1"`, `"2.1.1.1"`, `"4.2"`, `"5.3"`).
- Node identity (`node_id`) is strictly separated from node content state.

### Deterministic SHA-256 Content Hashing
- Each node computes a cryptographic SHA-256 hash across its normalized body text:
  $$\text{content\_hash} = \text{SHA256}(\text{body\_text.strip().encode('utf-8')})$$
- Determinism guarantees:
  - Identical text across `v1` and `v2` produces the exact same hash (e.g., Section `1` Overview has the identical hash in both versions).
  - Modified text produces distinct hashes (e.g., Section `2.1.1.1` battery cycles 300 in `v1` vs 250 in `v2`).

---

## 6. Document & Version Diff Strategy

The diff service (`DocumentComparator`) operates across the structured trees of `v1` and `v2`:
- **Added Nodes**: Nodes present in `v2` but absent from `v1` (e.g., Section `5.3 Data Export`).
- **Removed Nodes**: Nodes present in `v1` but absent from `v2`.
- **Modified Nodes**: Nodes present in both versions where `content_hash(v1) != content_hash(v2)`.
  - Specific real differences detected:
    - Section `2.1.1.1`: Battery cycles modified from 300 to 250 cycles.
    - Section `3.2`: Cuff inflation increment modified from 40 mmHg to 30 mmHg.
    - Section `4.2`: Error code E6 (Bluetooth synchronization failure) introduced; E3 auto-deflation modified from 2.0 to 1.5 seconds.
    - Section `4.3`: Low battery threshold modified from 15% to 10%.
- **Unchanged Nodes**: Nodes present in both versions where `content_hash(v1) == content_hash(v2)`.

---

## 7. Version-Pinned Selection & Duplicate Selection Policy

When a user selects a node via `POST /api/v1/selections`:
1. Reconstructs exact node content and cryptographic content hash for `(version, node_id)`.
2. **Duplicate Selection Policy**:
   - Selections are treated as immutable point-in-time snapshots.
   - If the same tuple `(version, node_id, content_hash)` is selected multiple times, the system does not create redundant duplicate database rows; it returns the existing selection record.
   - If the same `node_id` is selected under a different version or after a content change resulting in a different `content_hash`, a distinct selection record is persisted.

---

## 8. LLM QA Generation Pipeline & Bounded Retries

### Pipeline Workflow
$$\text{Selection} \longrightarrow \text{Exact Node Content} \longrightarrow \text{Content Hash} \longrightarrow \text{LLM Provider} \longrightarrow \text{Pydantic Validation} \longrightarrow \text{Retry if Malformed} \longrightarrow \text{Persist to SQLite}$$

### Strict Grounding & Schema
Generated test ideas must be strictly grounded in the manual text without hallucinating external medical requirements:
```python
class QAItem(BaseModel):
    title: str
    description: str
    expected_result: str
    source_reference: str

class QAResult(BaseModel):
    node_id: str
    version: str
    content_hash: str
    generated_at: str
    provider: str
    test_ideas: list[QAItem] = Field(..., min_length=3, max_length=5)
```

### Configurable Provider Interface & Deterministic Fallback
- `BaseLLMProvider`: Abstract interface defining `generate_raw(node_id, version, heading, content, retry_count)`.
- `GeminiLLMProvider`: Activated when `GEMINI_API_KEY` is provided in environment variables; calls Google Gemini 1.5 Flash.
- `DeterministicFallbackProvider`: Activated when no API key is present or offline. Uses rule-based extraction across numerical thresholds, tolerances, error codes, and operational steps to generate 3–5 high-quality, valid, grounded `QAItem`s.
- **Bounded Retry Mechanism**:
  - The generation service enforces a retry bound (default: 3 attempts).
  - Catches malformed JSON, missing fields, or invalid list lengths (< 3 or > 5 items).
  - If a real LLM provider repeatedly fails on intermediate attempts, it falls back to the deterministic provider before failing.
  - If all retries fail, an `LLMGenerationError` is raised, HTTP 422/500 returned, and no invalid data is persisted.

---

## 9. Persistence Model (SQLAlchemy + SQLite)

Database models in `app/db.py` persist all required entities:
1. `DocumentVersionRecord`: Tracks `id` (`v1`, `v2`), `title`, `total_pages`, `ingested_at`.
2. `DocumentNodeRecord`: Tracks `version`, `node_id`, `heading`, `level`, `body_text`, `page_number`, `parent_id`, `content_hash`, `tables_json`.
3. `SelectionRecord`: Tracks immutable selections with `version`, `node_id`, `content_hash`, `heading`, `content`, `selected_at`.
4. `GeneratedQARecord`: Tracks persisted QA test ideas, strictly linked to `node_id`, `version`, `generated_from_hash`, `test_ideas_json`, `provider_used`, and `generated_at`.

---

## 10. Staleness & Impact Detection

### Conceptual State Matrix
When inspecting previously generated QA against a target document version:
| Condition | Status | `review_required` | Reason |
| :--- | :--- | :--- | :--- |
| `current_hash == generated_from_hash` | `current` | `False` | Content hash matches source generation content. QA ideas remain valid. |
| `current_hash != generated_from_hash` | `stale` | `True` | Content hash mismatch / changed. Section modified between versions. |
| Node does not exist in target version | `removed` | `True` | Node was removed in target version. Test ideas impacted. |
| No QA generated for existing node | `untracked` | `False` | Node exists in target version but QA has not been generated yet. |

- Available via `GET /api/v1/manuals/{version}/nodes/{node_id}/impact` and `GET /api/v1/qa/{node_id}`.

---

## 11. Decision Log (Required Questions)

### A. What is the most likely silent wrong result and how would you detect it?
**The Silent Wrong Result**:
In pure text-based PDF block extraction, multi-column layouts or tables with irregular column boundaries can have cell text interleaved across adjacent lines in the reading order. For example, if a table has columns `[Code, Meaning, Device Behavior]`, raw text extraction may stream `E1 \n Cuff not connected \n Aborts \n E2...` which might be incorrectly parsed as a single paragraph rather than structured cells.

**Detection Method**:
1. PyMuPDF's `find_tables()` algorithm is used specifically to detect tabular bounding boxes independently of text stream ordering.
2. We verify extracted error codes against known device codes (`E1` through `E5` in `v1`, `E1` through `E6` in `v2`). If table cell counts do not match expected row/column shapes or error code counts drop below expected thresholds, automated warnings are logged.
3. Content hashing captures the exact concatenated representation so any discrepancy in whitespace or missing tokens immediately triggers a hash mismatch in regression test suites.

### B. Where did you choose simplicity over correctness, and why?
**Design Choice**:
We chose a deterministic BM25 / token-overlap keyword scoring search retrieval mechanism over spinning up an external vector database (such as ChromaDB, Pinecone, or Qdrant) with neural embeddings.

**Rationale**:
Medical device manuals like the CT-200 are concise, dense, and highly standardized (under 10 pages). Precision in regulatory engineering requires exact term matching for specific parameters (e.g., `E3`, `30 mmHg`, `300 cycles`, `10°C to 40°C`). Semantic vector models frequently hallucinate or retrieve semantically similar but legally distinct sections. A deterministic keyword-and-token retrieval service is 100% reproducible, requires zero external services or embedding model downloads, has zero latency overhead, runs completely offline inside Docker, and eliminates non-deterministic retrieval bugs.

### C. Name one input/document condition that the implementation does not fully support and explain what happens.
**Condition**:
Scanned, purely raster-image PDFs without an embedded OCR text layer (e.g., a physical manual scanned on an optical office scanner and saved directly as an unsearchable image).

**What Happens**:
When `extract_pdf` is executed on such a file, `page.get_text("blocks")` returns zero text blocks. The implementation explicitly detects this condition:
```python
if is_scanned_or_empty:
    logger.warning("Scanned or image-only PDF detected. No extractable text found.")
```
Instead of silently returning a corrupt or empty document tree, it raises an informative warning, builds an empty section container, and documents the unsupported condition. Heavy Tesseract/OCR engine dependencies were intentionally not bundled to keep the Docker image lightweight, stable, and architecture-agnostic across Apple Silicon and Linux without binary compilation failures.
