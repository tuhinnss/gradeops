# GRADEOPS — Human-in-the-Loop AI Exam Grading

AI-powered handwritten exam evaluation: OCR, rubric matching, partial marking, justifications, plagiarism flags, annotated PDFs, bulk processing, optional authentication, analytics, and instructor review workflows.

> **Backward compatible:** With `AUTH_ENABLED=false` (default), the original single-upload dashboard and API behave as before.

---

# Architecture

```text
PDF Upload → Page Images → Question Segmentation → OCR → Rubric Match → Scoring → Annotated PDF
                                    ↓
                              PostgreSQL (submissions, rubrics, logs)
```

---

# Tech Stack

| Layer          | Technology                         |
| -------------- | ---------------------------------- |
| Backend        | FastAPI                            |
| Frontend       | Next.js 14 + Tailwind              |
| OCR            | Florence-2 / Nougat / Tesseract    |
| Database       | PostgreSQL                         |
| ORM            | SQLAlchemy                         |
| ML Models      | Sentence Transformers              |
| Authentication | JWT                                |
| Deployment     | Docker / Render / Railway / Vercel |

---

# Project Structure

| Path                                  | Purpose                                             |
| ------------------------------------- | --------------------------------------------------- |
| `app/main.py`                         | FastAPI app, CORS, lifespan (DB init), routes mount |
| `app/config.py`                       | Pydantic settings from `.env`                       |
| `app/core/logging.py`                 | Structured stdout logging                           |
| `app/core/exceptions.py`              | Domain errors → HTTP exceptions                     |
| `app/db/models.py`                    | SQLAlchemy models                                   |
| `app/db/session.py`                   | Async engine, sessions, `init_db()`                 |
| `app/db/crud.py`                      | Database helpers                                    |
| `app/schemas/`                        | Pydantic request/response models                    |
| `app/services/pdf_processor.py`       | PDF → PIL images                                    |
| `app/services/layout_segmenter.py`    | Question segmentation                               |
| `app/services/ocr/`                   | OCR engines + fallback chain                        |
| `app/services/rubric_parser.py`       | Rubric parsing                                      |
| `app/services/evaluation_engine.py`   | Similarity scoring                                  |
| `app/services/plagiarism_detector.py` | Plagiarism detection                                |
| `app/services/pdf_annotator.py`       | Annotated PDF generation                            |
| `app/services/pipeline.py`            | End-to-end orchestration                            |
| `frontend/`                           | Next.js frontend                                    |
| `tests/`                              | Unit/integration tests                              |
| `samples/`                            | Sample rubric files                                 |
| `sample_pdfs/`                        | Sample answer sheets                                |
| `docker-compose.yml`                  | PostgreSQL + API setup                              |

---

# Features

* AI-powered handwritten exam grading
* OCR extraction pipeline
* Rubric-based evaluation
* Partial marking support
* Confidence scoring
* Plagiarism detection
* Annotated PDF generation
* Bulk answer-sheet processing
* Analytics dashboard
* Human-in-the-loop review system
* Optional authentication system
* Docker support
* Multiple OCR engine fallback

---

# Quick Start (Local)

## 1. Clone the Repository

Open PowerShell / Terminal:

```bash
git clone https://github.com/PIYUSH-bit1818/gradeops-cc.git
cd gradeops-cc
```

You can clone the project anywhere on your system.

Examples:

* `D:\Projects\gradeops-cc`
* `C:\Users\YourName\Desktop\gradeops-cc`

---

# 2. Install Python

Install:

* Python 3.11+

Download:

* https://www.python.org/downloads/

During installation:

✅ Enable:

```text
Add Python to PATH
```

Verify installation:

```bash
python --version
```

---

# 3. Install PostgreSQL + pgAdmin

Download PostgreSQL:

* https://www.postgresql.org/download/windows/

During installation:

| Setting  | Recommended Value        |
| -------- | ------------------------ |
| Port     | `5432`                   |
| Username | `postgres`               |
| Password | Create your own password |

⚠️ Remember the password you create during installation.

pgAdmin 4 will automatically install with PostgreSQL.

---

# 4. Create Database in pgAdmin

Open:

```text
pgAdmin 4
```

Then:

1. Expand:

```text
Servers → PostgreSQL
```

2. Right click:

```text
Databases → Create → Database
```

3. Database name:

```text
gradeops
```

4. Click Save

---

# 5. Create Virtual Environment

Inside project folder:

```bash
python -m venv .venv
```

Activate virtual environment:

### Windows

```bash
.\.venv\Scripts\activate
```

### Linux / Mac

```bash
source .venv/bin/activate
```

---

# 6. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

---

# 7. Configure Environment Variables

Copy environment file:

### Windows

```bash
copy .env.example .env
```

### Linux / Mac

```bash
cp .env.example .env
```

Open `.env`

Update this line:

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/gradeops
```

Replace:

```text
YOUR_PASSWORD
```

with your PostgreSQL password.

Example:

```env
DATABASE_URL=postgresql+asyncpg://postgres:mypassword123@localhost:5432/gradeops
```

---

# 8. Start Backend Server

Run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If successful, you should see:

```text
Application startup complete
```

Backend URL:

```text
http://localhost:8000
```

Swagger API Docs:

```text
http://localhost:8000/docs
```

---

# 9. Frontend Setup

Open a NEW terminal.

Go to frontend folder:

```bash
cd frontend
```

Install frontend dependencies:

```bash
npm install
```

Start frontend:

```bash
npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

---

# 10. Running the Full Project

Keep BOTH terminals running simultaneously.

## Terminal 1 — Backend

```bash
uvicorn app.main:app --reload --port 8000
```

## Terminal 2 — Frontend

```bash
npm run dev
```

---

# 11. OCR Requirements

GRADEOPS uses OCR for handwritten answer extraction.

Recommended OCR:

* Tesseract OCR

Download:

* https://github.com/tesseract-ocr/tesseract

After installation, ensure Tesseract is added to PATH.

Verify installation:

```bash
tesseract --version
```

---

# Frontend (Next.js)

The frontend dashboard supports:

* Rubric upload
* Answer-sheet upload
* Bulk evaluation
* Result visualization
* Annotated PDF preview/download
* Analytics dashboard
* Human review workflows

Frontend path:

```text
frontend/
```

---

# API Workflow

## 1. Upload Rubric

```bash
curl -X POST "http://localhost:8000/api/v1/upload/rubric" \
  -F "file=@samples/example_rubric.json" \
  -F "name=Midterm"
```

---

## 2. Upload Answer Sheet

```bash
curl -X POST "http://localhost:8000/api/v1/upload/answer-sheet" \
  -F "file=@student_answers.pdf" \
  -F "student_id=STU001" \
  -F "rubric_id=<RUBRIC_UUID>"
```

---

## 3. Run Evaluation

```bash
curl -X POST "http://localhost:8000/api/v1/evaluate/run" \
  -H "Content-Type: application/json" \
  -d "{\"submission_id\": \"<SUBMISSION_UUID>\", \"rubric_id\": \"<RUBRIC_UUID>\"}"
```

---

## 4. Download Results

Endpoints:

* `GET /api/v1/results/{submission_id}`
* `GET /api/v1/results/{submission_id}/annotated-pdf`
* `GET /api/v1/results/{submission_id}/generate-report`

---

# Example Output

```json
{
  "student_id": "STU001",
  "results": [
    {
      "question": "Q1",
      "marks_awarded": 4.0,
      "max_marks": 5.0,
      "justification": "Awarded 4.0/5.0 marks for Q1.",
      "confidence": 0.89,
      "is_blank": false
    }
  ],
  "total": 42.0,
  "max_total": 50.0
}
```

---

# Rubric JSON Format

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
        {
          "condition": "Partial explanation",
          "marks": 2
        }
      ]
    }
  ]
}
```

---

# OCR Engines

| Engine     | Config      | Notes                |
| ---------- | ----------- | -------------------- |
| Florence-2 | `florence2` | Best handwriting OCR |
| Nougat     | `nougat`    | Academic documents   |
| Tesseract  | `tesseract` | Fast CPU fallback    |

Fallback chain:

```text
Primary → Florence → Nougat → Tesseract
```

---

# Environment Variables

See `.env.example` for all available settings.

Important variables:

| Variable               | Purpose               |
| ---------------------- | --------------------- |
| `DATABASE_URL`         | PostgreSQL connection |
| `OCR_ENGINE`           | OCR model selection   |
| `OCR_DEVICE`           | CPU/GPU               |
| `SIMILARITY_THRESHOLD` | Matching threshold    |
| `AI_BACKEND`           | Optional LLM backend  |
| `AUTH_ENABLED`         | Enable authentication |

---

# Docker Setup

Copy environment file:

```bash
copy .env.example .env
```

Start Docker:

```bash
docker compose up --build
```

---

# Database Migrations

```bash
alembic upgrade head
```

Tables are also automatically created during startup via:

```python
init_db()
```

---

# Running Tests

```bash
pytest tests/ -v
```

Tests include:

* rubric parsing
* evaluation logic
* API health checks
* OCR pipeline tests

---

# Common Errors & Fixes

## PostgreSQL Authentication Error

Error:

```text
password authentication failed for user "postgres"
```

Fix:

* Verify PostgreSQL password
* Update `.env`
* Restart backend

---

## Port Already in Use

Frontend:

```bash
npm run dev -- -p 3001
```

Backend:

```bash
uvicorn app.main:app --reload --port 8001
```

---

## Missing Python Packages

Run again:

```bash
pip install -r requirements.txt
```

inside activated virtual environment.

---

## Node Modules Error

Delete:

```text
node_modules/
```

Then reinstall:

```bash
npm install
```

---

# Verify Setup

## Backend API

Open:

```text
http://localhost:8000/docs
```

## Frontend

Open:

```text
http://localhost:3000
```

## Full Workflow Test

1. Upload rubric
2. Upload handwritten PDF
3. Run evaluation
4. Download annotated PDF

If all work successfully, setup is complete.

---

# Deployment

## Backend

Supported platforms:

* Docker Compose
* Render
* Railway

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## Frontend

Recommended:

* Vercel

Root directory:

```text
frontend/
```

Environment variable:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

# Future Improvements

* Better handwriting OCR
* GPU acceleration
* Cloud deployment
* Real-time evaluation queue
* Advanced analytics
* Teacher dashboard enhancements
* LLM-powered reasoning

---

# Next Steps

Upload:

* sample handwritten answer PDFs
* rubric JSON/PDF

to validate end-to-end evaluation accuracy.

Recommended sample:

```text
samples/quiz2_ma201_rubric.json
```
