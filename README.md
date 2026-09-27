# GradeOps — Human-in-the-Loop AI Exam Grading

GradeOps grades handwritten exam answer sheets with AI (OCR → question
segmentation → rubric evidence matching → partial credit) and routes every
grade through human review before it is published. A **Professor** owns courses,
exams, rubrics and final grades. **Teaching Assistants** review the AI's grades
only for the exams they are assigned to.

No AI grade reaches a student without a human decision:

```text
AI_EVALUATED → TA_PENDING → TA_APPROVED / TA_OVERRIDDEN / ESCALATED → PROFESSOR_APPROVED → PUBLISHED
```

| Professor | TA |
| --- | --- |
| ![Professor overview](docs/screenshots/professor-overview.png) | ![TA review screen](docs/screenshots/ta-review-screen.png) |

---

## Contents

1. [Architecture](#architecture)
2. [Professor workflow](#professor-workflow)
3. [TA workflow](#ta-workflow)
4. [Role permissions](#role-permissions)
5. [Database](#database)
6. [API](#api)
7. [Local setup](#local-setup)
8. [Migrations](#migrations)
9. [Development seed data](#development-seed-data)
10. [Example login flow](#example-login-flow)
11. [Testing](#testing)
12. [Screenshots](#screenshots)
13. [Grading engine notes](#grading-engine-notes)
14. [Configuration reference](#configuration-reference)
15. [Known limitations](#known-limitations)

---

## Architecture

```text
                    ┌──────────────────────── Next.js 14 (frontend/) ─────────────────────────┐
                    │ /login → GET /auth/me → /professor/*  or  /ta/*   (RoleGuard + sidebar) │
                    └───────────────────────────────┬──────────────────────────────────────────┘
                                                    │ JWT (Authorization: Bearer)
┌───────────────────────────────────── FastAPI (app/) ───────────────────────────────────────────┐
│ routes/        auth · courses · exams · rubrics · professor · ta · review · (legacy) upload,   │
│                bulk, evaluate, results, analytics                                               │
│ deps_auth.py   CurrentUser · RequireProfessor · RequireTA · RequireProfessorOrTA                │
│ permissions.py require_course_access · require_exam_access · require_submission_access ·        │
│                SQL scope filters (course_scope / exam_scope / submission_scope)                 │
│ services/      review_service (single review-action implementation) · review_queue ·           │
│                finalization (approve/lock/publish/reopen, gradebook) · analytics_service ·     │
│                integrity · batch_queue · pipeline                                               │
└───────────────────────────────┬─────────────────────────────────────────┬──────────────────────┘
                                │ SQLAlchemy 2 (async) + Alembic          │
                          PostgreSQL                          Grading pipeline (unchanged flow):
                                                              PDF → page images → question
                                                              segmentation → OCR → rubric evidence
                                                              scoring → similarity check → annotated PDF
```

Key design points:

- **Authorization is enforced on the backend.** Every route resolves the caller
  from the JWT, checks the role, then checks ownership (professor) or assignment
  (TA). Resources the caller cannot access return **404** (their existence is not
  revealed); a wrong role returns **403**. List endpoints filter in SQL, so a TA
  never receives rows outside their assigned exams. Knowing a UUID is never
  enough.
- **One review-action implementation** (`app/services/review_service.py`) is used
  by the TA and professor dashboards and by the legacy `/review/{id}/action`
  route. Actions lock the submission row (`SELECT … FOR UPDATE`) and accept an
  optional `expected_review_status` so two reviewers cannot silently overwrite
  each other.
- **Typed contracts.** Pydantic response models → OpenAPI
  (`frontend/src/lib/openapi.json`) → generated TypeScript
  (`frontend/src/lib/api-schema.ts`). A backend test fails if the committed
  schema drifts from the API.
- **Schema managed by Alembic.** The API does not create tables on startup
  (unless `DB_AUTO_CREATE=true` for throwaway experiments).

Project layout:

| Path | Purpose |
| --- | --- |
| `app/api/routes/` | REST routes (role dashboards + legacy workbench routes) |
| `app/api/deps_auth.py`, `app/api/permissions.py` | Authentication, role guards, ownership/assignment checks |
| `app/db/models.py` | SQLAlchemy models and lifecycle enums |
| `app/schemas/` | Pydantic request/response models (source of the frontend types) |
| `app/services/` | Grading pipeline, review, finalisation, analytics, integrity |
| `alembic/versions/` | `0001_baseline` (original schema) and `0002_academic_hierarchy` |
| `scripts/` | `create_user`, `seed_dev`, `claim_legacy_data`, `export_openapi`, `e2e_fixtures` |
| `frontend/src/app/professor/`, `frontend/src/app/ta/` | Role dashboards |
| `frontend/src/components/{ui,layout,grading,professor,ta,charts,workbench}` | Shared components |
| `frontend/src/lib/` | API client, generated types, session, role routing, shortcuts |
| `tests/` | Backend tests (pytest, real PostgreSQL) |
| `frontend/src/**/*.test.ts(x)`, `frontend/e2e/` | Frontend unit tests and browser E2E |

---

## Professor workflow

1. **Create a course** (`/professor/courses`) — code, name, semester, year, section.
2. **Add students** — individually or by CSV import (columns `student_id,name,email`).
3. **Add TAs** to the course — an existing TA account by email, or create the account by also giving an initial password.
4. **Create an exam** (`/professor/exams/new`) — a 4-step flow: details → rubric (upload JSON/PDF, or reuse one of your rubrics) → upload answer sheets (student IDs are inferred from filenames and validated against the roster before upload) → assign TAs.
5. **Run AI evaluation** from the exam page. Progress is polled from the batch job; failures are listed per file and can be re-run. The similarity check runs as part of the job.
6. **Distribute** submissions among the assigned TAs (round-robin; optional rebalance) or leave them in a shared queue.
7. **Monitor review** on the exam command center (`/professor/exams/[examId]`): pipeline stage, per-TA progress, submissions, audit log.
8. **Resolve escalations** (`/professor/reviews/escalated`): approve, override (reason required) or return to the TA with a note.
9. **Review similarity flags** (`/professor/integrity`): side-by-side excerpts; dismiss or confirm with notes. Flags are evidence for review, never an automatic finding.
10. **Finalize**: the confirmation dialog shows a summary (submissions, overrides, open escalations, open flags, manual-grading items). *Approve* (bulk-approves TA-reviewed submissions) → optional *Lock* → *Publish* (open similarity flags must be explicitly acknowledged). *Reopen* requires a reason and is audited.
11. **Gradebook** (`/professor/exams/[examId]/gradebook`): AI / TA / professor / final score per student, including roster students with no submission; CSV export (provisional before approval, final after).
12. **Analytics** at course, exam, question and student level: score distribution, question difficulty, full/partial/zero credit, most-missed rubric criteria, AI-vs-reviewer disagreement and override rates, TA workload.

## TA workflow

1. Sign in → `/ta` shows assigned exams, pending reviews, recent activity.
2. **Review queue** (`/ta/reviews`): only submissions from assigned exams (and, when distributed, only those assigned to you). Filter by exam, course, status, confidence range, similarity flag, manual-grading, student and question; sort by confidence or date. Filters are kept in the URL.
3. **Review screen** (`/ta/reviews/[submissionId]`): cropped answer image (or full page) beside the extracted text, the AI's marks, per-criterion evidence, confidence, similarity flags and the audit timeline.
   - **Approve** → `TA_APPROVED`
   - **Override** → marks validated `0 ≤ marks ≤ max`, a reason is required, notes optional → `TA_OVERRIDDEN`; the original AI marks are kept in the audit trail
   - **Escalate** with a reason (`ambiguous_answer`, `ocr_unreliable`, `rubric_unclear`, `integrity_concern`, `ai_grading_incorrect`, or `other` with notes) → `ESCALATED`
   - After an action the next pending submission opens automatically.
4. **Keyboard shortcuts** (disabled while typing in a text field; press `?` for help): `A` approve · `O` override · `E` escalate · `←`/`→` previous/next · `Space` show/hide review details · `Esc` close dialog.
5. **History** (`/ta/history`): every decision you made, from the review audit log.
6. **Escalations** (`/ta/escalations`): status of what you escalated (read-only).

A TA can revise a TA decision (`TA_APPROVED`/`TA_OVERRIDDEN`) on a submission in their scope until the professor approves the exam; escalated and professor-approved submissions are the professor's.

## Role permissions

Enforced in `app/api/deps_auth.py`, `app/api/permissions.py` and `app/services/review_service.py`; covered by `tests/test_authorization.py`.

| Capability | Professor | TA |
| --- | :---: | :---: |
| Create / edit / archive courses | own courses | — |
| Manage roster (add, CSV import, drop) | own courses | — |
| Add / remove TAs, assign TAs to exams | own courses | — |
| Create exams, upload / edit / link rubrics | own courses | — |
| Upload / delete answer sheets | own exams (delete only before review) | — |
| Run AI evaluation, distribute submissions | own exams | — |
| View exams & submissions | own courses | assigned exams only (and own distributed submissions) |
| Approve / override | any evaluated submission until the exam is locked or published | `AI_EVALUATED`, `TA_PENDING`, `TA_APPROVED`, `TA_OVERRIDDEN` in scope; not after exam approval |
| Escalate | — (resolves instead) | yes |
| Resolve escalation / return to TA | yes | — |
| Approve / lock / publish / reopen exam | own exams | — |
| Gradebook & CSV export | own exams | — |
| Exam analytics | full, with per-student data | cohort level only, assigned exams |
| Resolve similarity flags | own exams | view on assigned submissions |
| Review history | exam & submission audit logs | own decisions |

Accounts: `POST /auth/register` only ever creates **TA** accounts (and can be
disabled with `ALLOW_SELF_REGISTRATION=false`); a self-registered TA has no
access until a professor adds them to a course and assigns them to an exam.
Professors are provisioned with `python -m scripts.create_user --role professor`.

## Database

Managed by Alembic (`alembic/versions/`). Main tables:

| Table | Purpose |
| --- | --- |
| `users` | Accounts; `role` = `PROFESSOR` or `TA` |
| `courses` | Course offering; `professor_id` = owner; (`professor_id`, `course_code`, `semester`, `academic_year`) unique; `status` ACTIVE/ARCHIVED |
| `course_members` | TA membership of a course (`active`) |
| `students` | Student records (`student_id` unique) |
| `enrollments` | Student ↔ course (`ENROLLED` / `DROPPED`) |
| `rubrics` | Structured rubric JSON, `owner_id` |
| `exams` | Belongs to a course; `status` DRAFT → PROCESSING → TA_REVIEW → APPROVED → LOCKED → PUBLISHED; `rubric_id`; approval/lock/publish timestamps |
| `exam_tas` | TA assignment to an exam (`active`) |
| `exam_audit` | Exam-level audit log (created, rubric uploaded/linked, submissions uploaded/deleted, TA assignment, distribution, processing, approve/lock/publish/reopen, gradebook export) |
| `student_submissions` | One answer sheet; pipeline `status`, `review_status`, `course_id`, `exam_id`, `student_record_id`, `assigned_ta_id`, AI/TA/professor totals, escalation fields, `min_confidence`, `needs_manual_grading` |
| `extracted_answers`, `evaluation_logs` | Per-question OCR text/regions and per-question scoring |
| `review_audit` | Every review decision: actor, role, from/to status, question, old/new marks, reason, notes |
| `integrity_flags` | Similarity flags per question pair with evidence and professor resolution |
| `batch_jobs`, `plagiarism_reports` | Batch evaluation jobs and legacy per-rubric similarity reports |

Legacy data: the original schema had no courses or exams. Migration
`0002_academic_hierarchy` keeps every row, renames the `INSTRUCTOR` role to
`PROFESSOR`, maps old review states (`PENDING` → `AI_EVALUATED`/`NOT_EVALUATED`,
`REVIEWED` → `TA_PENDING`, `APPROVED` → `TA_APPROVED`, `OVERRIDDEN` →
`TA_OVERRIDDEN`, `REJECTED` → `ESCALATED`) and backfills AI/TA totals from the
stored evaluation results and override history. Legacy submissions have no
course; attach them to a professor with `scripts/claim_legacy_data.py` (see
[Migrations](#migrations)).

## API

All routes are under `/api/v1`. Interactive docs: `http://localhost:8000/docs`.

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/login`, `GET /auth/me`, `POST /auth/register` (TA only), `POST /auth/change-password`, `GET /auth/status` |
| Courses | `GET/POST /courses`, `GET/PATCH/DELETE /courses/{id}`, `GET/POST /courses/{id}/students`, `POST /courses/{id}/students/import-csv`, `DELETE /courses/{id}/students/{studentRecordId}`, `GET/POST /courses/{id}/tas`, `DELETE /courses/{id}/tas/{userId}`, `GET /courses/{id}/analytics`, `GET /courses/{id}/activity` |
| Exams | `GET/POST /exams`, `GET/PATCH /exams/{id}`, `GET/POST/PUT /exams/{id}/rubric`, `POST /exams/{id}/tas`, `DELETE /exams/{id}/tas/{taId}`, `POST /exams/{id}/distribute`, `GET/POST /exams/{id}/submissions`, `POST /exams/{id}/submissions/validate`, `DELETE /exams/{id}/submissions/{submissionId}`, `POST /exams/{id}/evaluate`, `GET /exams/{id}/publish-summary`, `POST /exams/{id}/approve`, `/lock`, `/publish`, `/reopen`, `GET /exams/{id}/gradebook`, `GET /exams/{id}/gradebook.csv?final=`, `GET /exams/{id}/analytics`, `GET /exams/{id}/integrity` |
| Rubrics | `GET /rubrics`, `GET/PUT /rubrics/{id}` |
| Professor | `GET /professor/dashboard`, `GET /professor/escalations`, `GET /professor/integrity`, `PATCH /professor/integrity/{flagId}`, `GET /professor/submissions` |
| TA | `GET /ta/dashboard`, `GET /ta/exams`, `GET /ta/reviews`, `GET /ta/reviews/{submissionId}`, `GET /ta/history` |
| Review | `GET /review/{id}`, `GET /review/{id}/detail`, `POST /review/{id}/action`, `GET /review/{id}/answer-image?question=`, `GET /review/{id}/pages/{i}`, `GET /review/{id}/source-pdf` |
| Batch jobs | `GET /bulk/jobs/{jobId}` |
| Legacy workbench | `POST /upload/rubric`, `POST /upload/answer-sheet`, `POST /bulk/answer-sheets`, `POST /bulk/answer-sheets/zip`, `POST /bulk/jobs`, `POST /evaluate/run`, `/evaluate/batch`, `/evaluate/all`, `/evaluate/ocr/{id}`, `GET /results/{id}`, `/results/{id}/annotated-pdf`, `/results/{id}/generate-report`, `GET /analytics/…` |

Review action body (`POST /review/{id}/action`):

```json
{
  "action": "override",
  "reason": "Key step present but OCR missed it",
  "notes": "Checked against page 2",
  "overrides": [{ "question": "Q2", "marks_awarded": 4 }],
  "expected_review_status": "ai_evaluated"
}
```

`action` is `approve | override | escalate | resolve | return_to_ta` (`reject`
is accepted as a legacy alias of `escalate`). Invalid transitions return `409`;
marks outside `0…max`, unknown questions or a missing reason return `400`/`422`.

### Backward compatibility

The original single-upload workbench (`/upload/*`, `/evaluate/*`, `/results/*`)
still works:

- With `AUTH_ENABLED=true` (default) these routes require login (uploading and
  evaluating require a professor) and are scoped like the new API: a professor
  sees their own uploads and courses, a TA only assigned submissions. The
  workbench UI is at `/workbench` (professors).
- With `AUTH_ENABLED=false` they are open, as in the original MVP, and `/`
  shows the workbench to anonymous visitors. This mode is for local demos only;
  the `/professor` and `/ta` dashboards always require login, and
  `ENVIRONMENT=production` refuses to start with auth disabled.

## Local setup

Requirements: Python 3.11+, Node.js 18+, PostgreSQL 14+, Tesseract OCR
(`tesseract --version`). The Florence-2/Nougat OCR engines and the
sentence-embedding model are downloaded from Hugging Face on first use.

```bash
git clone https://github.com/tuhinnss/gradeops.git
cd gradeops

# Backend
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
# edit .env: DATABASE_URL, and JWT_SECRET_KEY (openssl rand -hex 32)

createdb gradeops                  # or create it in pgAdmin
alembic upgrade head
python -m scripts.create_user --email you@uni.edu --name "Your Name" --role professor
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                        # http://localhost:3000
```

### Docker

```bash
cp .env.example .env               # set JWT_SECRET_KEY
docker compose up --build
```

`docker compose` starts PostgreSQL, runs `alembic upgrade head` in a one-shot
`migrate` service, then starts the API on port 8000 (Tesseract OCR). Create the
first professor inside the API container:

```bash
docker compose run --rm api python -m scripts.create_user --email you@uni.edu --role professor
```

The frontend is not containerised; run it with `npm run dev` or deploy
`frontend/` (e.g. Vercel) with `NEXT_PUBLIC_API_URL` set.

## Migrations

```bash
alembic upgrade head          # create or upgrade the schema
alembic current               # show the applied revision
alembic check                 # fail if models and migrations have drifted
alembic downgrade 0001_baseline   # lossy: drops courses/exams and maps states back
```

- **Fresh database:** `alembic upgrade head` creates everything.
- **Existing database created by the old `create_all` startup** (no
  `alembic_version` table): `0001_baseline` detects the existing tables and
  skips creation, then `0002_academic_hierarchy` upgrades them in place without
  deleting data. Back up first (`pg_dump`), then run `alembic upgrade head`.
- **Adopting legacy submissions** into the course/exam model:

  ```bash
  python -m scripts.claim_legacy_data --professor prof@uni.edu           # dry run
  python -m scripts.claim_legacy_data --professor prof@uni.edu --apply
  ```

  This creates a `LEGACY` course owned by the professor with one exam per
  legacy rubric, links the submissions and enrols their students. Grades are
  not changed, and every grade still needs human review before publishing.

On startup the API logs a warning if the database is not at the latest revision.

## Development seed data

`scripts/seed_dev.py` creates clearly labelled **development-only** data. It
refuses to run when `ENVIRONMENT=production` or when seed data already exists.

```bash
python -m scripts.seed_dev                  # course, roster, exam, answer sheets, AI grading
python -m scripts.seed_dev --with-reviews   # plus a few sample TA decisions
python -m scripts.seed_dev --no-evaluate    # leave the sheets for "Run AI evaluation" in the UI
```

It creates one professor and two TAs (all `@gradeops.dev`, password
`gradeops-dev-2026`), course `CS3001 Data Structures` with 10 students, a
mid-semester exam using `samples/ds_midsem_rubric.json`, and one generated
typed answer sheet per student. The sheets are graded by the real pipeline
(OCR → segmentation → evaluation → similarity check) through the same batch job
the dashboard uses — no scores are written directly. Nothing in the product
itself uses mock data; empty states are shown when there is no data.

## Example login flow

1. Visit `http://localhost:3000` → not signed in → redirected to `/login`.
2. Sign in as `professor@gradeops.dev` → the app calls `GET /auth/me` → role
   `professor` → `/professor`.
3. Sign in as `rahul.ta@gradeops.dev` → `/ta`. Opening any `/professor/*` URL as
   a TA shows *Access denied* and redirects to `/ta`; the API returns `403` for
   professor endpoints and `404` for exams/submissions the TA is not assigned to.
4. A deep link opened while signed out (e.g. `/ta/reviews/<id>`) returns there
   after login (`/login?next=…`, restricted to same-origin paths).

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"rahul.ta@gradeops.dev","password":"gradeops-dev-2026"}' | jq -r .access_token)
curl -s localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/api/v1/ta/reviews -H "Authorization: Bearer $TOKEN"
```

## Testing

### Backend (pytest, real PostgreSQL)

The tests migrate a separate database with Alembic and truncate it between
tests. Create it once:

```bash
createdb gradeops_test     # user/password from TEST_DATABASE_URL
pytest tests/ -q
```

`TEST_DATABASE_URL` defaults to
`postgresql+asyncpg://gradeops:gradeops@localhost:5432/gradeops_test`. The
end-to-end workflow test (`tests/test_e2e_workflow.py`) runs real Tesseract
OCR and is skipped when Tesseract is not installed.

Coverage includes authentication, cross-course/cross-exam authorization (IDOR),
course/roster/TA management, exam lifecycle, every review transition and
invalid transition, override bounds, concurrency guards, gradebook/CSV,
finalisation, migrations (fresh, legacy data, round trip, drift), OpenAPI/TS
sync, and grading-engine correctness (no marks for length, similarity is not
correctness).

### Frontend

```bash
cd frontend
npm test            # vitest: role routing, review workflow, shortcuts, override validation
npm run typecheck   # tsc --noEmit
npm run lint        # next lint
npm run build
```

After changing API schemas, regenerate the shared types:

```bash
python -m scripts.export_openapi && (cd frontend && npm run gen:api)
```

### Browser end-to-end

`frontend/e2e/workflow.cjs` drives the full professor + TA workflow in Chromium
through the real UI and API (course → roster CSV → TA → exam → rubric → upload →
AI evaluation → TA approve/override/escalate with keyboard shortcuts →
professor resolves escalation → approve → publish → final CSV), and checks that
a TA gets *Access denied* on professor pages.

```bash
# API on :8000 (OCR_ENGINE=tesseract) and web on :3000, against a migrated database
python -m scripts.create_user --email e2e.prof@uni.edu --role professor --password e2e-prof-pass-1
python -m scripts.e2e_fixtures /tmp/gradeops-e2e
cd frontend && E2E_FILES=/tmp/gradeops-e2e npm run e2e
```

## Screenshots

Captured from the running app with the development seed data.

| | |
| --- | --- |
| **Professor overview**<br>![](docs/screenshots/professor-overview.png) | **Courses**<br>![](docs/screenshots/professor-courses.png) |
| **Exam command center**<br>![](docs/screenshots/professor-exam-command-center.png) | **Gradebook**<br>![](docs/screenshots/professor-gradebook.png) |
| **Exam analytics**<br>![](docs/screenshots/professor-analytics.png) | **Integrity review**<br>![](docs/screenshots/professor-integrity.png) |
| **Escalations**<br>![](docs/screenshots/professor-escalations.png) | **TA management**<br>![](docs/screenshots/professor-ta-management.png) |
| **TA overview**<br>![](docs/screenshots/ta-overview.png) | **TA review queue**<br>![](docs/screenshots/ta-review-queue.png) |
| **TA review screen**<br>![](docs/screenshots/ta-review-screen.png) | **Override dialog**<br>![](docs/screenshots/ta-override-dialog.png) |
| **Keyboard shortcuts**<br>![](docs/screenshots/ta-review-shortcuts.png) | **TA review history**<br>![](docs/screenshots/ta-history.png) |
| **Light theme**<br>![](docs/screenshots/ta-review-queue-light.png) | |

## Grading engine notes

`app/services/evaluation_engine.py` scores each question against its rubric:

- Marks come from **evidence for rubric key points** (semantic similarity of
  answer sentences to each key point, plus keyword support). Answer length or
  "effort" never earns marks; a long answer that matches nothing is flagged for
  manual grading instead.
- Partial-credit rules act as floors when their condition is evidenced;
  negative conditions deduct only on a strong match.
- If the embedding model cannot be loaded (offline host), grading falls back to
  keyword matching with confidence capped at 0.5 and the result marked
  `scoring_method: lexical` (`EMBEDDING_FALLBACK=error` fails instead).
- The similarity check compares answers to the same question across students.
  Pairs where both answers closely restate the rubric's key points are not
  flagged (correct answers to the same question are expected to be similar). A flag reads "Potential match — review required" and is evidence for
  the professor, never a verdict.

### Rubric JSON format

```json
{
  "title": "Exam",
  "items": [
    {
      "question_number": "Q1",
      "max_marks": 5,
      "key_points": ["Point 1", "Point 2"],
      "negative_conditions": ["Wrong formula"],
      "partial_credit_rules": [{ "condition": "Partial explanation", "marks": 2 }]
    }
  ]
}
```

PDF rubrics are parsed by `app/services/rubric_parser.py`. Samples:
`samples/ds_midsem_rubric.json`, `samples/quiz2_ma201_rubric.json`.

### OCR engines

| Engine | `OCR_ENGINE` | Notes |
| --- | --- | --- |
| Florence-2 | `florence2` | Handwriting; needs `torch` and a model download |
| Nougat | `nougat` | Academic documents |
| Tesseract | `tesseract` | CPU, no download; used by Docker and the tests |

When the configured engine fails to load, the pipeline falls back along
Florence → Nougat → Tesseract.

## Configuration reference

All settings are environment variables (see `.env.example`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://gradeops:gradeops@localhost:5432/gradeops` | Async PostgreSQL URL (also used by Alembic) |
| `ENVIRONMENT` | `development` | `production` refuses the default JWT secret and `AUTH_ENABLED=false` |
| `AUTH_ENABLED` | `true` | `false` re-opens the legacy anonymous workbench routes (demos only) |
| `JWT_SECRET_KEY` | placeholder | Token signing key — set a random value |
| `JWT_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `ALLOW_SELF_REGISTRATION` | `true` | Allow `POST /auth/register` (TA accounts only) |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost |
| `DB_AUTO_CREATE` | `false` | Run `create_all` on startup (throwaway experiments only) |
| `OCR_ENGINE` / `OCR_DEVICE` | `florence2` / `cpu` | OCR engine and device |
| `EMBEDDING_MODEL_ID` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model for rubric matching and similarity |
| `EMBEDDING_FALLBACK` | `lexical` | Behaviour when the embedding model is unavailable |
| `PLAGIARISM_SIMILARITY_THRESHOLD` | `0.92` | Similarity above which a pair is flagged |
| `MAX_UPLOAD_MB`, `PDF_DPI` | `50`, `200` | Upload limit and rasterisation DPI |
| `CORS_ORIGINS` | localhost:3000 | Allowed frontend origins |
| `NEXT_PUBLIC_API_URL` (frontend) | `http://localhost:8000` | API base URL for the web app |

## Known limitations

- Batch evaluation runs in an in-process asyncio queue (no external worker).
  A job interrupted by an API restart is marked failed once it has shown no
  progress for 20 minutes (checked when the exam or job is next viewed); the
  professor then re-runs evaluation. The legacy workbench's "evaluate all"
  progress is kept in memory only.
- One professor owns a course; there are no co-professors or course-level
  admin roles.
- Student records are global (`student_id` is unique across courses).
- The gradebook is per exam; there is no course-wide weighted grade matrix.
- OCR quality on handwriting depends on the engine; Tesseract is weak on
  cursive. Question segmentation relies on question labels being visible.
- There is no student-facing portal; "published" means grades are final and
  exportable.
