# GRADEOPS — Project Status & Development Context

**Last updated:** May 2026  
**Phase:** 1 (ML + backend + web dashboard) — demo-ready, iterative accuracy improvements ongoing  
**Purpose of this document:** Onboard future developers and AI sessions without losing architectural or behavioral context.

---

## 1. Project overview

**GRADEOPS** is an AI-assisted handwritten exam grading system (Human-in-the-Loop style). Instructors/TAs upload:

1. A **marking scheme** (JSON or PDF — often a solutions PDF for typed exams), and  
2. **Student answer sheets** (PDF scans of handwritten work).

The system runs OCR, segments answers by question, scores against the rubric, generates justifications, optionally flags plagiarism, and produces an **annotated PDF** plus JSON results. A **Next.js dashboard** drives the workflow without custom backend changes per UI feature.

**Reference sample files (in repo):**

| File | Role |
|------|------|
| `sample pdfs/Quiz2_MA201-2025-Solutions.pdf` | Typed solutions PDF — ideal rubric source (native text) |
| `sample pdfs/DATA.pdf` | Scanned handwritten answers — no embedded text; OCR-dependent |
| `samples/example_rubric.json` | Generic example rubric |
| `samples/quiz2_ma201_rubric.json` | Hand-crafted rubric for Quiz 2 (Q1–Q6, total 15) — most reliable for demos |

**Expected Mid-Exam rubric (`sample pdfs/sample pdf new/MID-EXAM_28-02-2023_Final-Solutions.pdf`):**

| Section | Questions | Marks each | Subtotal |
|---------|-----------|------------|----------|
| Section I | 7 | 1 | 7 |
| Section II | 3 | 2 | 6 |
| Section III | 2 | 6 | 12 |
| **Total** | **12** | | **25** |

Global labels: `Q1`–`Q12` in document order (section-local numbers reset; no dedupe collision).

**Expected Quiz 2 rubric (ground truth):**

| Question | Max marks |
|----------|-----------|
| Q1 | 2 |
| Q2 | 4 |
| Q3 | 2 |
| Q4 | 3 |
| Q5 | 1 |
| Q6 | 3 |
| **Total** | **15** |

---

## 2. Current architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14, port 3000)                                       │
│  frontend/src/components/GradeOpsDashboard.tsx                          │
│  - Upload rubric / answer PDFs                                          │
│  - Evaluate, view per-question marks, download annotated PDF            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP (NEXT_PUBLIC_API_URL)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI API (port 8000) — app/main.py, prefix /api/v1                  │
│  upload │ evaluate │ results                                            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  GradeOpsPipeline (app/services/pipeline.py)                            │
│  1. PDF → images (PyMuPDF)                                              │
│  2. Layout segmentation (rubric-guided or OCR markers)                  │
│  3. OCR per region (Florence-2 / Nougat / Tesseract fallback)           │
│  4. Merge & dedupe answers (text_utils)                                 │
│  5. EvaluationEngine + answer_quality heuristics                        │
│  6. PDF annotation (PyMuPDF)                                            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL (async SQLAlchemy + asyncpg)                                │
│  rubrics, student_submissions, extracted_answers, evaluation_logs       │
└─────────────────────────────────────────────────────────────────────────┘
```

**Design constraints (do not break without explicit intent):**

- Frontend UI layout and API response shapes are stable for the dashboard.
- Database schema has not been heavily migrated; tables created via `init_db()` on startup.
- Grading is **lightweight**: sentence-transformers embeddings + heuristics; **no required LLM** (`USE_LLM_REASONING=false` by default).

---

## 3. Repository layout

```
gradeops project/
├── app/                          # FastAPI backend
│   ├── main.py                   # App entry, CORS, lifespan, DB init
│   ├── config.py                 # pydantic-settings from .env
│   ├── api/routes/
│   │   ├── upload.py             # POST rubric, answer-sheet
│   │   ├── evaluate.py           # POST run, batch, ocr-only
│   │   └── results.py            # GET results, annotated PDF, report
│   ├── core/                     # logging, exceptions
│   ├── db/                       # models, session, crud
│   ├── schemas/                  # Pydantic API models
│   └── services/
│       ├── pipeline.py           # Orchestrator
│       ├── pdf_processor.py      # PDF → images
│       ├── layout_segmenter.py   # Question regions
│       ├── ocr/                  # Florence-2, Nougat, Tesseract
│       ├── rubric_parser.py      # JSON/PDF → RubricSchema
│       ├── text_utils.py         # OCR cleanup, Q detection, validation
│       ├── answer_quality.py     # Handwritten-answer heuristics
│       ├── evaluation_engine.py  # Scoring + justifications
│       ├── plagiarism_detector.py
│       └── pdf_annotator.py
├── frontend/                     # Next.js 14 + Tailwind
│   └── src/
│       ├── app/                  # layout, page, globals
│       ├── components/GradeOpsDashboard.tsx
│       └── lib/api.ts            # API client
├── samples/                      # Example JSON rubrics
├── sample pdfs/                  # Real test PDFs (user-provided)
├── scripts/
│   ├── debug_quiz_rubric.py      # Verify Quiz2 PDF → 6 Q, 15 marks
│   └── api_examples.ps1 / .sh
├── tests/                        # pytest (text_utils, answer_quality, …)
├── uploads/                      # Stored uploads (gitignored)
├── outputs/                      # evaluation.json, annotated PDFs
├── docker-compose.yml            # Postgres + API
├── requirements.txt
├── .env.example
├── README.md
└── PROJECT_STATUS.md             # This file
```

---

## 4. API contract (stable)

**Base URL:** `http://localhost:8000`  
**Prefix:** `/api/v1`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/upload/rubric` | Form: `file` (.json/.pdf), `name` |
| POST | `/api/v1/upload/answer-sheet` | Form: `file` (.pdf), `student_id`, optional `rubric_id` |
| POST | `/api/v1/evaluate/run` | JSON: `submission_id`, `rubric_id?`, `run_plagiarism_check` |
| POST | `/api/v1/evaluate/batch` | Multiple submission IDs |
| POST | `/api/v1/evaluate/ocr/{submission_id}` | OCR only |
| GET | `/api/v1/results/{submission_id}` | Full result JSON |
| GET | `/api/v1/results/{submission_id}/json` | Typed `EvaluationResponse` |
| GET | `/api/v1/results/{submission_id}/annotated-pdf` | PDF download |
| GET | `/api/v1/results/{submission_id}/generate-report` | OCR + logs + evaluation |

**Evaluation response shape (frontend depends on this):**

```json
{
  "submission_id": "uuid",
  "student_id": "string",
  "results": [
    {
      "question": "Q1",
      "marks_awarded": 1.5,
      "max_marks": 2.0,
      "justification": "...",
      "confidence": 0.62,
      "is_blank": false,
      "key_points_matched": [],
      "key_points_missed": []
    }
  ],
  "total": 8.5,
  "max_total": 15.0,
  "plagiarism_flags": [],
  "annotated_pdf_url": "/api/v1/results/{id}/annotated-pdf"
}
```

**Important:** `max_total` is computed from the **validated rubric** (`rubric_total_marks`), not from summing duplicate OCR regions. `total` is the sum of `marks_awarded` per question (one row per rubric question).

---

## 5. Database models

| Table | Purpose |
|-------|---------|
| `rubrics` | Parsed rubric JSON (`structured_data`), source file metadata |
| `student_submissions` | Answer PDF path, status, `extracted_text`, `evaluation_result`, `annotated_pdf_path` |
| `extracted_answers` | Per-question OCR rows (bbox, text, confidence) |
| `evaluation_logs` | Stage messages (ocr, evaluate, …) |

**Submission status enum:** `uploaded` → `processing` → `ocr_complete` → `evaluated` (or `failed`).

---

## 6. Completed fixes (historical context)

### 6.1 Rubric parsing (major)

**Multi-section exams (Feb 2026):** Parses `Section I (7 questions of 1 Mark each)` headers, applies per-section marks, assigns global `Q1…Q12`, handles `1.` on its own line + multi-line stems. See `find_section_aware_question_blocks()` in `text_utils.py`.

**Problems fixed:**

- Duplicate `Q0` entries and inflated totals (e.g. 66 instead of 15).
- OCR-first parsing on typed solution PDFs missed **Q1** and **Q5** → only 4 questions, total 10.
- `[2+1 Marks]` on Q6 parsed as 1 mark instead of 3.
- Splitting on arbitrary digits created fake questions.

**Solutions implemented (`text_utils.py`, `rubric_parser.py`):**

- **Native PDF text first** via PyMuPDF (`_extract_native_pdf_text`) before OCR for rubric PDFs.
- Line-anchored question headers: `Q1.`, `Question 1`, `1. Find…` (IIT-style verbs).
- Page-footer standalone numbers filtered out.
- Marks parsing: `[n]`, `(n marks)`, `[2+1 Marks]` → sum; ignore `........ 1 MARK` sub-lines.
- `validate_rubric_items()` dedupes by question, rejects Q0, caps per-question marks.
- `repair_missing_questions()` merges blocks if declared total (`Total Marks: 15`) hints missing items.
- `log_rubric_parse_debug()` logs blocks, marks, previews on parse.
- Key points from solutions: `extract_rubric_key_points()` (marking scheme, stems, “gets X Mark” lines).

### 6.2 Answer segmentation

**Problems fixed:** LayoutParser / text-band heuristics invented many fake `Q1…Qn` regions.

**Solutions (`layout_segmenter.py`, `pipeline.py`):**

- When rubric question list is known → **even vertical split** per page (most stable).
- Skip LayoutParser when rubric is attached.
- Dedupe regions by question label; drop tiny/noise regions without rubric.

### 6.3 Evaluation / all-zero handwritten scores

**Problems fixed:** Strict embedding similarity (~0.55) → 0 marks for all questions; confidence ~27%.

**Solutions (`answer_quality.py`, `evaluation_engine.py`):**

- Relaxed semantic thresholds (`FULL_MATCH` 0.38, `PARTIAL_MATCH` 0.22).
- **Dual scoring:** `max(rubric_marks, effort_marks × blend)` with effort cap at 85% of max.
- Heuristics: math symbols, equation lines, digits, steps, STEM tokens, keyword overlap.
- `realistic_confidence()` targets ~40–85% for readable handwritten work.
- Professional justification templates (partial credit, OCR limits).
- Re-evaluate if OCR flagged `is_blank` but text length > 20.

### 6.4 Frontend + backend integration

- Next.js dashboard: upload, evaluate, question breakdown, annotated PDF link.
- CORS for `localhost:3000`.
- `localStorage` persists rubric/submission IDs across refresh.

---

## 7. OCR pipeline (detailed)

**Entry:** `OCRService` (`app/services/ocr/ocr_service.py`)

**Preprocessing (lightweight, low RAM):**

- RGB convert, optional downscale if max side > 2000px.
- Contrast + sharpness enhancement (no heavy filters).

**Engine chain (config `OCR_ENGINE`):**

1. Primary: `florence2` | `nougat` | `tesseract` (from `.env`)
2. Fallback order if primary fails: florence2 → nougat → tesseract

**Post-processing:**

- `clean_ocr_text()` — whitespace, drop noise lines.
- `adjust_ocr_confidence()` — text-quality heuristics.
- `is_blank()` — alnum count + `is_noise_fragment()`.

**Per submission (`pipeline.process_submission_ocr`):**

1. `PDFProcessor.pdf_to_images()` — PyMuPDF @ `PDF_DPI` (default 200).
2. Full-page OCR for context text.
3. `LayoutSegmenter.segment_page()` with `expected_questions` from rubric.
4. Per-region OCR on crops.
5. `merge_answers_by_question()` — longest text wins per Q; align to rubric set.

**Docker default:** `OCR_ENGINE=tesseract` in `docker-compose.yml` for faster/low-RAM startup.

**Handwritten scans (`DATA.pdf`):** Native text is empty; quality depends entirely on OCR + segmentation. Typed rubrics should use solutions PDF or JSON.

---

## 8. Rubric parsing (detailed)

**Entry:** `RubricParser.parse_file()` / `parse_pdf()` / `parse_text()`

**JSON:** Direct mapping to `RubricItem` list → `validate_rubric_items()`.

**PDF:**

1. Extract native text (PyMuPDF) if ≥ ~400 chars.
2. Else OCR all pages.
3. `find_question_blocks()` → per-question body + marks from header window.
4. Build `RubricItem` with `extract_rubric_key_points()`.
5. `repair_missing_questions()` + `validate_rubric_items()`.
6. Debug log summary.

**Debug script:**

```powershell
cd "d:\gradeops project"
$env:PYTHONPATH="."
python -m scripts.debug_quiz_rubric
```

Expected: 6 questions, total 15.0 for `Quiz2_MA201-2025-Solutions.pdf`.

---

## 9. Grading logic (detailed)

**Entry:** `EvaluationEngine.evaluate_all()` → one `QuestionResult` per rubric question.

### 9.1 Answer quality (`answer_quality.py`)

`analyze_answer()` computes:

- Length, words, digits, math symbols, equation-like lines, step hints, STEM tokens.
- `keyword_best` vs rubric key points.
- `content_score` (0–1), `is_handwritten_math`, `is_truly_blank`.

`effort_based_marks(max_marks, quality)` — tiered partial credit (20–72% of max by content score), floor ~25% of max if math signals present.

### 9.2 Rubric alignment (`evaluation_engine.py`)

For each key point:

- Embedding cosine similarity (sentence-transformers `all-MiniLM-L6-v2`).
- Keyword overlap (lightweight, no extra models).
- `combined = 0.55×sem + 0.45×kw`.

Marks from matched (full) + partial (55% weight per point) key points, plus optional partial rules / negative conditions (penalties require higher bar to avoid OCR false positives).

### 9.3 Final marks per question

```text
rubric_marks  = from key points + rules − penalties
effort_marks  = from answer_quality heuristics
marks_awarded = blend(max(rubric, effort×0.75), effort if rubric very low)
              → round to 0.5, cap at max_marks, effort-alone cap 85% of max
```

Blanks: `content_score < 0.15` and OCR blank → 0 marks, high confidence.

### 9.4 Confidence

`realistic_confidence()` — typically 0.40–0.85 for non-blank handwritten answers; ~0.90 for confirmed blanks.

### 9.5 Optional LLM

If `USE_LLM_REASONING=true` and `OPENAI_API_KEY` set, justifications can be rewritten (marks unchanged). **Off by default** for demos and RAM.

### 9.6 Plagiarism

`PlagiarismDetector` — cross-student embedding similarity per question above `PLAGIARISM_SIMILARITY_THRESHOLD` (0.92).

---

## 10. Frontend setup

**Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS.

**Key files:**

- `frontend/src/components/GradeOpsDashboard.tsx` — full UI (do not redesign without user request).
- `frontend/src/lib/api.ts` — fetch wrappers matching API above.
- `frontend/.env.local` — `NEXT_PUBLIC_API_URL=http://localhost:8000`

**Flow:**

1. Upload rubric → stores `rubricId` in state + localStorage.
2. Upload answer sheet(s) with `student_id`.
3. **Evaluate** → POST `/evaluate/run`.
4. Expand **Question breakdown**; download **Annotated PDF**.

**Note:** After backend rubric parser fixes, users must **re-upload rubric** (or clear session) — old DB rubrics may still hold the 4-question / 10-mark parse.

---

## 11. Backend setup

**Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, PostgreSQL, PyMuPDF, OpenCV, sentence-transformers, transformers (optional OCR models).

**Config:** `.env` from `.env.example`

| Variable | Typical value | Notes |
|----------|---------------|--------|
| `DATABASE_URL` | `postgresql+asyncpg://gradeops:gradeops@localhost:5432/gradeops` | |
| `OCR_ENGINE` | `tesseract` (dev) / `florence2` (GPU) | |
| `OCR_DEVICE` | `cpu` | |
| `EMBEDDING_MODEL_ID` | `sentence-transformers/all-MiniLM-L6-v2` | Loaded once, cached |
| `SIMILARITY_THRESHOLD` | `0.55` (config); engine uses lower internal thresholds | |
| `BLANK_ANSWER_MIN_CHARS` | `3` | |
| `MAX_UPLOAD_MB` | `50` | |

---

## 12. Commands to run

### 12.1 PostgreSQL (local)

Create DB/user if needed:

```sql
CREATE USER gradeops WITH PASSWORD 'gradeops';
CREATE DATABASE gradeops OWNER gradeops;
```

### 12.2 Backend

```powershell
cd "d:\gradeops project"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Install Tesseract for OCR fallback: https://github.com/UB-Mannheim/tesseract/wiki
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs  
- Health: http://localhost:8000/health  

### 12.3 Frontend

```powershell
cd "d:\gradeops project\frontend"
copy .env.local.example .env.local
npm install
npm run dev
```

- UI: http://localhost:3000  

### 12.4 Docker (backend + Postgres only)

```powershell
cd "d:\gradeops project"
copy .env.example .env
docker compose up --build
```

Run frontend separately on host.

### 12.5 Tests

```powershell
cd "d:\gradeops project"
$env:PYTHONPATH="."
python -m pytest tests/test_text_utils.py tests/test_answer_quality.py -v
```

Full suite may require all deps (`PyMuPDF`, `PIL`, `sentence-transformers`, etc.).

### 12.6 Debug rubric parse

```powershell
$env:PYTHONPATH="."
python -m scripts.debug_quiz_rubric
```

---

## 13. Known limitations

1. **Handwritten answer PDFs** (`DATA.pdf`): No embedded text; OCR quality dominates. Segmentation uses rubric-guided strips — misalignment on multi-page layouts can assign wrong text to a question.

2. **Semantic grading is approximate:** Embeddings compare noisy OCR to typed rubric/solution phrases. Heuristic partial credit improves demos but is **not** a substitute for expert marking.

3. **Rubric from solutions PDF:** Key points are inferred from stems/marking notes, not a formal instructor rubric. JSON rubrics (`samples/quiz2_ma201_rubric.json`) are more predictable.

4. **RAM / CPU:** Florence-2 and sentence-transformers are heavy; use `OCR_ENGINE=tesseract` on low-RAM laptops. First evaluation loads embedding model (slow once).

5. **LayoutParser:** Optional; disabled on rubric-guided path. Detectron2 not required for default flow.

6. **No auth / multi-tenant:** Single-user demo; no role-based access despite original spec mentioning instructors/TAs.

7. **Annotated PDF:** Marks placed using bbox heuristics; may not align perfectly with handwritten regions.

8. **Re-upload required:** Cached rubrics in PostgreSQL are not auto-migrated when parser logic changes.

9. **Python 3.14:** Some environments may have partial package compatibility; **3.11** is the tested target per README.

10. **Plagiarism:** Only meaningful with multiple students evaluated together in batch with flag enabled.

---

## 14. Next improvement ideas (prioritized)

### High impact

1. **Per-question OCR crops from layout** — detect handwritten boxes on `DATA.pdf` instead of only equal vertical splits (OpenCV contour + rubric anchors).

2. **Ship canonical JSON rubrics** per exam in `samples/` and recommend JSON upload in UI helper text.

3. **Golden-file tests** — store expected parse of `Quiz2_MA201-2025-Solutions.pdf` and expected score ranges for `DATA.pdf` snippets in CI.

4. **Cache embedding model** in `models_cache/` with explicit warm-up endpoint `POST /evaluate/warmup` for demos.

### Medium impact

5. **Question–answer alignment** using detected “Q1”, “Q2” marks in handwritten margins (OCR on left margin).

6. **Tune effort/rubric blend** per question mark weight (small questions vs 4-mark questions).

7. **Alembic migrations** instead of `create_all` only.

8. **List submissions API** — `GET /api/v1/submissions` for dashboard refresh without localStorage.

9. **Progress WebSocket** for long OCR/evaluate jobs.

### Lower priority / future phases

10. Instructor vs TA roles, review queue, keyboard shortcuts (original product spec).

11. Optional LLM justification (`USE_LLM_REASONING`) with budget caps.

12. Fine-tuned OCR for math (Nougat/TrOCR) when GPU available.

13. Next.js production deploy + API URL env per environment.

14. Upgrade Next.js past 14.2.18 (security advisory in npm audit).

---

## 15. Files to read first (for AI continuation)

| Priority | File | Why |
|----------|------|-----|
| 1 | `app/services/pipeline.py` | End-to-end flow |
| 2 | `app/services/evaluation_engine.py` | Scoring behavior |
| 3 | `app/services/answer_quality.py` | Handwritten heuristics |
| 4 | `app/services/text_utils.py` | Rubric parse + OCR cleanup |
| 5 | `app/services/rubric_parser.py` | PDF/JSON rubric ingest |
| 6 | `app/services/ocr/ocr_service.py` | OCR chain |
| 7 | `frontend/src/components/GradeOpsDashboard.tsx` | UI contract |
| 8 | `app/api/routes/*.py` | HTTP surface |

---

## 16. Demo checklist

1. Start Postgres → backend → frontend.  
2. Upload **`samples/quiz2_ma201_rubric.json`** OR **`sample pdfs/Quiz2_MA201-2025-Solutions.pdf`** (verify 6 questions, 15 marks in logs).  
3. Upload **`sample pdfs/DATA.pdf`** with a student ID.  
4. **Evaluate** — expect non-zero partial marks if OCR extracted content per question.  
5. Download annotated PDF; expand question breakdown for justifications.  
6. If totals wrong: **Clear list**, re-upload rubric, re-evaluate.

---

## 17. Changelog snapshot (conversation-derived)

| Area | Status |
|------|--------|
| FastAPI + PostgreSQL | Working |
| OCR pipeline | Working (engine-dependent quality) |
| Rubric parse (typed PDF) | Working — 6×15 for Quiz 2 |
| Rubric parse (OCR-only) | Fragile |
| Handwritten evaluation | Improved via heuristics; not perfect |
| Frontend dashboard | Working |
| Docker compose | Working (API + DB) |
| Auth / HITL review UI | Not implemented |
| Phase 2 features | Not started |

---

*End of PROJECT_STATUS.md — update this file when making significant behavioral or architectural changes.*
