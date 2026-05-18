# GRADEOPS — Human-in-the-Loop AI Exam Grading

AI-powered handwritten exam evaluation: OCR, rubric matching, partial marking, justifications, plagiarism flags, annotated PDFs, bulk processing, optional auth, and instructor review workflows.

> **Backward compatible:** With `AUTH_ENABLED=false` (default), the original single-upload dashboard and API behave as before.

## Architecture

```
PDF Upload → Page Images → Question Segmentation → OCR → Rubric Match → Scoring → Annotated PDF
                                    ↓
                              PostgreSQL (submissions, rubrics, logs)
```

## Project structure

| Path | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, CORS, lifespan (DB init), routes mount |
| `app/config.py` | Pydantic settings from `.env` |
| `app/core/logging.py` | Structured stdout logging |
| `app/core/exceptions.py` | Domain errors → HTTP exceptions |
| `app/db/models.py` | SQLAlchemy models: Rubric, StudentSubmission, ExtractedAnswer, EvaluationLog |
| `app/db/session.py` | Async engine, sessions, `init_db()` |
| `app/db/crud.py` | Create/read/update helpers |
| `app/schemas/` | Pydantic request/response models |
| `app/services/pdf_processor.py` | PDF → PIL images via PyMuPDF |
| `app/services/layout_segmenter.py` | Question regions (OpenCV + optional LayoutParser) |
| `app/services/ocr/` | Florence-2, Nougat, Tesseract with fallback chain |
| `app/services/rubric_parser.py` | JSON/PDF → structured rubric |
| `app/services/evaluation_engine.py` | Sentence-transformers + cosine similarity scoring |
| `app/services/plagiarism_detector.py` | Cross-student similarity flags |
| `app/services/pdf_annotator.py` | Marks & comments on PDF (PyMuPDF) |
| `app/services/pipeline.py` | End-to-end orchestration |
| `app/api/routes/upload.py` | Upload answer sheet & rubric |
| `app/api/routes/evaluate.py` | Run OCR + evaluation |
| `app/api/routes/results.py` | JSON results, annotated PDF, report |
| `samples/example_rubric.json` | Sample marking scheme |
| `docker-compose.yml` | PostgreSQL + API |
| `frontend/` | Next.js 14 + Tailwind UI (uploads, results, annotated PDF) |
| `scripts/api_examples.*` | curl / PowerShell examples |

## Quick start (local)

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ (or Docker)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) on PATH (fallback engine)
- Optional: CUDA GPU for Florence-2 / Nougat

### 2. Setup

```bash
cd "d:\gradeops project"
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
```

Start PostgreSQL, then:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/docs** for interactive API docs.

## Frontend (Next.js)

The web UI lives in `frontend/`: upload marking scheme (JSON/PDF), upload student answer PDFs, run evaluation, open **question breakdown** (marks + AI remarks per question), and download **annotated PDFs**.

```bash
cd frontend
copy .env.local.example .env.local
npm install
npm run dev
```

Then open **http://localhost:3000**. Set `NEXT_PUBLIC_API_URL` in `.env.local` to your FastAPI base (default `http://localhost:8000`). The backend `CORS_ORIGINS` already includes `http://localhost:3000`.

## Docker (backend)

```bash
copy .env.example .env
docker compose up --build
```

Docker defaults to `OCR_ENGINE=tesseract` for faster startup. For Florence-2, set `OCR_ENGINE=florence2` and mount GPU if available.

## API workflow

### 1. Upload rubric

```bash
curl -X POST "http://localhost:8000/api/v1/upload/rubric" \
  -F "file=@samples/example_rubric.json" \
  -F "name=Midterm"
```

### 2. Upload answer sheet

```bash
curl -X POST "http://localhost:8000/api/v1/upload/answer-sheet" \
  -F "file=@student_answers.pdf" \
  -F "student_id=STU001" \
  -F "rubric_id=<RUBRIC_UUID>"
```

### 3. Evaluate

```bash
curl -X POST "http://localhost:8000/api/v1/evaluate/run" \
  -H "Content-Type: application/json" \
  -d "{\"submission_id\": \"<SUBMISSION_UUID>\", \"rubric_id\": \"<RUBRIC_UUID>\"}"
```

### 4. Results & annotated PDF

- `GET /api/v1/results/{submission_id}` — full JSON
- `GET /api/v1/results/{submission_id}/annotated-pdf` — download PDF
- `GET /api/v1/results/{submission_id}/generate-report` — OCR + logs + evaluation

## Output example

```json
{
  "student_id": "STU001",
  "results": [
    {
      "question": "Q1",
      "marks_awarded": 4.0,
      "max_marks": 5.0,
      "justification": "Awarded 4.0/5.0 marks for Q1. Matched key points: ...",
      "confidence": 0.89,
      "is_blank": false
    }
  ],
  "total": 42.0,
  "max_total": 50.0
}
```

## Rubric JSON format

```json
{
  "title": "Exam",
  "items": [
    {
      "question_number": "Q1",
      "max_marks": 5,
      "key_points": ["Point 1", "Point 2"],
      "negative_conditions": ["Wrong formula"],
      "partial_credit_rules": [
        { "condition": "Partial explanation", "marks": 2 }
      ]
    }
  ]
}
```

## OCR engines

| Engine | Config `OCR_ENGINE` | Notes |
|--------|---------------------|-------|
| Florence-2 | `florence2` | Default; best for handwriting (GPU recommended) |
| Nougat | `nougat` | Academic documents |
| Tesseract | `tesseract` | Fast CPU fallback |

Fallback chain: primary → Florence → Nougat → Tesseract.

## Environment variables

See `.env.example` for all options. Key settings:

- `DATABASE_URL` — async PostgreSQL URL
- `OCR_ENGINE` / `OCR_DEVICE` — model selection
- `SIMILARITY_THRESHOLD` — key point match threshold (0–1)
- `OPENAI_API_KEY` + `USE_LLM_REASONING=true` — optional LLM justifications

## Tests

```bash
pytest tests/ -v
```

Unit tests cover rubric parsing, evaluation logic, and health endpoint (DB mocked).

## Phase 2 features

| Feature | Endpoints | Notes |
|---------|-----------|-------|
| Bulk upload | `POST /api/v1/bulk/answer-sheets`, `/bulk/answer-sheets/zip` | Multi-PDF or ZIP; auto student IDs from filenames |
| Batch queue | `POST /api/v1/bulk/jobs`, `GET /api/v1/bulk/jobs/{id}` | Async evaluation with progress |
| Auth (optional) | `/api/v1/auth/register`, `/login`, `/me` | Set `AUTH_ENABLED=true` |
| Review (HITL) | `GET/POST /api/v1/review/{submission_id}` | Approve, reject, override marks |
| Analytics | `GET /api/v1/analytics/rubric/{id}` | Averages, toppers, pass/fail |
| Plagiarism report | `GET /api/v1/analytics/rubric/{id}/plagiarism` | Cohort flags |
| Optional AI | `AI_BACKEND=openai\|gemini\|huggingface` | Heuristic grading remains default |
| S3 storage | `STORAGE_BACKEND=s3` | Local disk fallback |

### Frontend pages

- `/` — Dashboard (single + bulk upload, review panel)
- `/analytics` — Charts (Recharts)
- `/login`, `/signup` — When auth is enabled

### Migrations

```bash
alembic upgrade head
```

Tables are also created on startup via `init_db()` for local dev.

### Deployment

- **API:** Docker Compose, [Render](https://render.com), or [Railway](https://railway.app) — use `DATABASE_URL` + `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Frontend:** [Vercel](https://vercel.com) — root `frontend/`, env `NEXT_PUBLIC_API_URL`

## Next steps

Upload a **sample handwritten answer PDF** and **marking scheme** to validate end-to-end accuracy. Use `samples/quiz2_ma201_rubric.json` for reliable typed-rubric demos.
