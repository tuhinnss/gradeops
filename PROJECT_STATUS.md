# GRADEOPS — Project Status & Development Context

**Last updated:** September 2026
**Phase:** 2 — course/exam hierarchy, role-based Professor and TA dashboards, human review lifecycle
**Purpose of this document:** Onboard future developers and AI sessions without losing architectural or behavioral context. User-facing setup and workflows live in `README.md`.

---

## 1. Project overview

**GRADEOPS** grades handwritten exam answer sheets with AI and routes every grade through human review.

- A **Professor** owns courses (roster, TAs), exams (rubric, answer sheets, AI evaluation), escalations, similarity flags, the gradebook and finalisation (approve → lock → publish, reopen).
- A **TA** reviews AI grades only for exams they are assigned to: approve, override (with reason) or escalate, from a keyboard-driven review screen.
- Review lifecycle (per submission): `NOT_EVALUATED → AI_EVALUATED → TA_PENDING → TA_APPROVED | TA_OVERRIDDEN | ESCALATED → PROFESSOR_APPROVED → PUBLISHED`. Nothing is published without a human approval.
- Exam lifecycle: `DRAFT → PROCESSING → TA_REVIEW → APPROVED → LOCKED → PUBLISHED` (reopen returns to `TA_REVIEW`).

The original single-upload workbench (upload rubric + answer sheet → evaluate → annotated PDF) still works at `/workbench` (professors) and, with `AUTH_ENABLED=false`, anonymously at `/`.

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
Next.js 14 (frontend/, :3000)
  /login → GET /auth/me → /professor/* | /ta/*        SessionProvider + RoleGuard + AppShell
  components/{ui,layout,grading,professor,ta,charts,workbench}
  lib/api-schema.ts (generated from OpenAPI) · lib/endpoints.ts · lib/client.ts
        │  Authorization: Bearer <JWT>
        ▼
FastAPI (app/, :8000, prefix /api/v1)
  routes: auth · courses · exams · rubrics · professor · ta · review
          legacy: upload · bulk · evaluate · results · analytics
  deps_auth.py    get_current_user, require_role, RequireProfessor/RequireTA/RequireProfessorOrTA
  permissions.py  require_course/exam/submission_access (404 when inaccessible), SQL scopes
  services:       review_service (all review actions) · review_queue · finalization ·
                  analytics_service · integrity · exam_workflow · batch_queue · pipeline
        │
        ▼
GradeOpsPipeline (unchanged flow)
  PDF → images → question segmentation → OCR (Florence-2 / Nougat / Tesseract)
  → EvaluationEngine (rubric evidence) → similarity check → annotated PDF
        │
        ▼
PostgreSQL via SQLAlchemy 2 async; schema managed by Alembic
```

**Design constraints (do not break without explicit intent):**

- Authorization lives in the backend. Every data route checks role and ownership/assignment; list endpoints filter in SQL. Inaccessible resources return 404, wrong role 403.
- All review decisions go through `review_service.apply_review_action` (row lock + optional `expected_review_status`). Do not add a second implementation.
- Schema changes require an Alembic migration; `alembic check` (and `tests/test_migrations.py`) must report no drift. The API never runs `create_all` unless `DB_AUTO_CREATE=true`.
- Response models are Pydantic (`app/schemas/`). After changing them run `python -m scripts.export_openapi && (cd frontend && npm run gen:api)`; `tests/test_openapi_sync.py` fails otherwise.
- Effort/length heuristics never add marks (see §9).
- Similarity flags are evidence for review, worded neutrally ("Potential match — review required").

---

## 3. Repository layout

```
app/
├── main.py                 # app, CORS, lifespan (security checks, schema-revision check)
├── config.py               # settings (.env)
├── api/
│   ├── deps_auth.py        # authentication + role dependencies
│   ├── permissions.py      # ownership / assignment checks and SQL scopes
│   └── routes/             # auth, courses, exams, rubrics, professor, ta, review,
│                           # upload, bulk, evaluate, results, analytics
├── db/                     # models.py (enums + tables), session.py, crud.py
├── schemas/                # common (ApiModel), academic, review, dashboard, evaluation, …
└── services/
    ├── pipeline.py, pdf_processor.py, layout_segmenter.py, ocr/, rubric_parser.py,
    │   text_utils.py, answer_quality.py, evaluation_engine.py, embeddings.py,
    │   plagiarism_detector.py, pdf_annotator.py            # grading pipeline
    ├── batch_queue.py, evaluate_all_queue.py               # background jobs
    ├── review_service.py, review_queue.py                  # review lifecycle + queues
    ├── exam_workflow.py, finalization.py                   # exam status, gradebook, publish
    └── academic.py, staff.py, analytics_service.py, integrity.py, activity.py
alembic/versions/           # 0001_baseline, 0002_academic_hierarchy
scripts/                    # create_user, seed_dev, claim_legacy_data, export_openapi,
                            # e2e_fixtures, debug_* rubric checks
frontend/src/
├── app/                    # /login, /signup, /professor/*, /ta/*, /workbench, /analytics
├── components/             # ui, layout, grading, professor, ta, charts, workbench
├── lib/                    # client, endpoints, types, api-schema (generated), session, roles
└── test/                   # vitest setup + component tests
frontend/e2e/workflow.cjs   # Playwright browser E2E
tests/                      # pytest against PostgreSQL (see §12)
docs/screenshots/           # README screenshots
```

---

## 4. API contract

Full endpoint list: `README.md` → API, or `http://localhost:8000/docs`. The
machine-readable contract is `frontend/src/lib/openapi.json`.

The legacy workbench routes keep their original request/response shapes. The
per-question evaluation result gained optional fields (`criteria`,
`key_points_partial`, `requires_manual_grading`, `ai_marks_awarded`,
`scoring_method`, `reviewer_comment`); existing fields are unchanged.

```json
{
  "question": "Q1",
  "marks_awarded": 1.5,
  "max_marks": 2.0,
  "justification": "...",
  "confidence": 0.62,
  "is_blank": false,
  "key_points_matched": [],
  "key_points_partial": [],
  "key_points_missed": [],
  "criteria": [{ "criterion": "...", "kind": "key_point", "max_marks": 1, "awarded": 1, "status": "met" }],
  "requires_manual_grading": false,
  "scoring_method": "semantic"
}
```

`max_total` comes from the validated rubric; `total` is the sum of per-question marks.

---

## 5. Database models

See `README.md` → Database for the table list. Key points:

- `users.role`: `PROFESSOR` | `TA` (the old `INSTRUCTOR` value was renamed by migration 0002).
- `courses.professor_id` owns a course; `course_members` (TAs) and `exam_tas` (TA ↔ exam, `active`) drive TA access.
- `student_submissions` carries `course_id`, `exam_id`, `student_record_id`, `assigned_ta_id`, `review_status`, `ai_total_marks` / `ta_total_marks` / `professor_total_marks`, escalation fields, `min_confidence`, `needs_manual_grading`.
- `review_audit` records every decision with actor, role, from/to status, per-question old/new marks and reason; `exam_audit` records exam-level events.
- `integrity_flags` stores one row per (exam, question, submission pair) with evidence and the professor's resolution; re-running evaluation keeps resolved decisions.
- Legacy rows (no course/exam) survive migration; `scripts/claim_legacy_data.py` attaches them to a professor's `LEGACY` course.

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


---

## 9. Grading logic (current)

**Entry:** `EvaluationEngine.evaluate_all()` → one `QuestionResult` per rubric question.

- Each key point is worth `max_marks / n`. A full match (semantic ≥ 0.55; or semantic ≥ 0.40 with keyword overlap ≥ 0.25; or keyword ≥ 0.60 with semantic ≥ 0.30) earns the full share; a partial match (semantic ≥ 0.40, or keyword ≥ 0.35 with semantic ≥ 0.30) earns half. Word overlap without semantic agreement is not credited.
- Partial-credit rules are **floors** (`max(key_point_marks, rule_marks)`), not bonuses.
- Partial-credit rules and negative conditions need a strong match (semantic ≥ 0.55 and keyword ≥ 0.35). Each triggered negative condition deducts 15% of the question, at most 40% in total.
- `answer_quality.effort_based_marks` is computed only as evidence: if it exceeds the awarded marks by ≥ 25% of the maximum, the result gets confidence ≤ 0.45 and `requires_manual_grading`, which surfaces it in review queues. It never changes marks.
- Questions without key points are returned with 0 marks and `requires_manual_grading`.
- Embedding model unavailable → `EMBEDDING_FALLBACK=lexical` grades with keyword overlap only (`scoring_method: lexical`, confidence ≤ 0.5); `error` fails instead.
- Optional LLM (`USE_LLM_REASONING`) may rewrite justifications; marks are unchanged.
- Similarity check (`plagiarism_detector.py`): per question, pairwise cosine (or Jaccard when no model) ≥ `PLAGIARISM_SIMILARITY_THRESHOLD` (0.92). Pairs where both answers are ≥ 0.75 similar to the rubric's key points are skipped. Flags are persisted as `integrity_flags` for professor review.
- `tests/test_evaluation_correctness.py` pins these rules (a long, effortful but irrelevant answer scores 0; matching criteria earn their share; partial rules are floors; no key points → manual grading; lexical fallback is marked and capped; neutral flag wording; answers that both follow the rubric are not flagged).

---

## 10. Frontend

**Stack:** Next.js 14 app router (client pages), React 18, TypeScript, Tailwind with CSS-variable tokens (light/dark, `darkMode: "class"`), Vitest + Testing Library, Playwright for E2E.

- `lib/session.tsx` — `SessionProvider` resolves the user from `GET /auth/me`; `lib/roles.ts` maps role → home and validates `?next=` paths.
- `components/layout/RoleGuard.tsx` — wrong role shows *Access denied* then redirects home (the API enforces the same rule).
- `components/grading/ReviewWorkspace.tsx` — shared review screen (TA and professor), keyboard shortcuts via `lib/shortcuts.ts`, auto-advance to the next pending submission.
- `components/GradeOpsDashboard.tsx` — the original workbench, now composed from `components/workbench/*`.
- Charts are plain HTML/CSS (`components/charts/Charts.tsx`) using `--viz-*` tokens; every chart has a table view.
- Types come from `lib/api-schema.ts` (generated); `lib/types.ts` re-exports friendly aliases.

---

## 11. Backend setup

Python 3.11+, FastAPI, SQLAlchemy 2 async, PostgreSQL, Alembic, PyMuPDF, OpenCV, Tesseract, sentence-transformers / transformers (optional OCR models). All settings: `.env.example` and `README.md` → Configuration reference.

---

## 12. Commands

```bash
# Database
alembic upgrade head
python -m scripts.create_user --email prof@uni.edu --role professor
python -m scripts.seed_dev --with-reviews          # development data only

# Run
uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev

# Backend tests (needs a gradeops_test database; TEST_DATABASE_URL to override)
pytest tests/ -q

# Frontend checks
cd frontend && npm test && npm run typecheck && npm run lint && npm run build

# Browser E2E (API + web running)
python -m scripts.e2e_fixtures /tmp/gradeops-e2e
cd frontend && E2E_FILES=/tmp/gradeops-e2e npm run e2e

# Contract sync after schema changes
python -m scripts.export_openapi && (cd frontend && npm run gen:api)

# Rubric parser checks
python -m scripts.debug_quiz_rubric
```

---

## 13. Known limitations

1. **OCR quality dominates** on handwritten PDFs (`DATA.pdf`); Tesseract is weak on cursive. Segmentation relies on visible question labels / rubric-guided strips.
2. **Semantic grading is approximate** — every AI grade is provisional and must be approved by a human before publishing.
3. **Background jobs are in-process** (`batch_queue.py`). A job interrupted by an API restart is marked failed after 20 minutes without progress (on the next exam/job read) and must be re-run. Legacy `evaluate/all` progress is in memory only.
4. **Single owner per course** — no co-professors or department admins.
5. **Student records are global** (`students.student_id` unique across courses).
6. **Per-exam gradebook only** — no course-wide weighted grade matrix.
7. **No student portal** — "published" means final and exportable.
8. **Annotated PDF** mark placement uses bbox heuristics.
9. **Offline hosts** without the embedding model grade lexically with capped confidence.

---

## 14. Next improvement ideas

1. External job queue (e.g. Redis/RQ or Postgres-backed worker) so evaluation survives API restarts.
2. Course-wide gradebook with exam weights.
3. Co-professor / course admin roles.
4. Per-question OCR crops from detected handwriting boxes.
5. Golden-file tests for OCR + scoring on the sample PDFs.
6. Upgrade Next.js beyond 14.2.x.

---

## 15. Files to read first

| Priority | File | Why |
|----------|------|-----|
| 1 | `app/api/permissions.py`, `app/api/deps_auth.py` | Who can see / do what |
| 2 | `app/services/review_service.py` | Review state machine |
| 3 | `app/services/finalization.py` | Approve / lock / publish / reopen, gradebook |
| 4 | `app/db/models.py`, `alembic/versions/0002_academic_hierarchy.py` | Data model + legacy mapping |
| 5 | `app/services/pipeline.py`, `app/services/evaluation_engine.py` | Grading |
| 6 | `frontend/src/components/grading/ReviewWorkspace.tsx` | Review UI |
| 7 | `frontend/src/lib/session.tsx`, `frontend/src/lib/roles.ts` | Login routing |

---

## 16. Demo checklist

1. `alembic upgrade head` → `python -m scripts.seed_dev --with-reviews`.
2. Start API (`OCR_ENGINE=tesseract` is fine) and web.
3. Sign in as `professor@gradeops.dev` (password printed by the seed script): overview → course → exam command center → analytics → integrity.
4. Sign in as `rahul.ta@gradeops.dev`: review queue → review screen → `A` / `O` / `E` → history.
5. Back as professor: resolve the escalation → Finalize (approve → publish) → final CSV.

---

## 17. Changelog snapshot

| Area | Status |
|------|--------|
| FastAPI + PostgreSQL | Working; schema via Alembic (0001 baseline, 0002 hierarchy) |
| OCR pipeline | Working (engine-dependent quality) |
| Rubric parse (typed PDF / JSON) | Working |
| Evaluation engine | Rubric-evidence scoring; effort never adds marks; lexical fallback |
| Similarity check | Persisted integrity flags with professor resolution; reference-following pairs skipped |
| Auth & roles | JWT; Professor / TA; backend ownership + assignment checks; TA-only self-registration |
| Courses, roster, TAs, exams | Implemented (API + Professor dashboard) |
| TA review workflow | Queue, split-screen review, override/escalate, shortcuts, history |
| Finalisation | Approve / lock / publish / reopen with audit; gradebook + CSV |
| Analytics | Course, exam, question, student, reviewer-agreement |
| Legacy workbench | Preserved (`/workbench`; anonymous with `AUTH_ENABLED=false`) |
| Tests | pytest (API, authorization, lifecycle, migrations, engine), vitest, Playwright E2E |
| Docker compose | API + Postgres + one-shot migrate service |

---

*Update this file when making significant behavioral or architectural changes.*
