"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { BulkUploadSection } from "@/components/BulkUploadSection";
import { ReviewPanel } from "@/components/ReviewPanel";
import {
  annotatedPdfHref,
  evaluateAll,
  evaluateSubmission,
  getApiBase,
  getResults,
  type BulkUploadItem,
  type EvaluationResponse,
  type QuestionResult,
  uploadAnswerSheet,
  uploadRubric,
} from "@/lib/api";

type StoredSubmission = {
  id: string;
  studentId: string;
  filename: string;
};

const STORAGE_KEY = "gradeops:dashboard:v1";

type Persisted = {
  rubricId: string | null;
  rubricName: string;
  rubricFilename: string | null;
  questionCount: number | null;
  submissions: StoredSubmission[];
};

function loadPersisted(): Persisted | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Persisted;
  } catch {
    return null;
  }
}

function savePersisted(data: Persisted) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function GradeOpsDashboard() {
  const [rubricName, setRubricName] = useState("Exam Rubric");
  const [rubricId, setRubricId] = useState<string | null>(null);
  const [rubricFilename, setRubricFilename] = useState<string | null>(null);
  const [questionCount, setQuestionCount] = useState<number | null>(null);
  const [rubricBusy, setRubricBusy] = useState(false);

  const [studentId, setStudentId] = useState("");
  const [sheetBusy, setSheetBusy] = useState(false);

  const [submissions, setSubmissions] = useState<
    (StoredSubmission & { evaluation?: EvaluationResponse; loading?: boolean; error?: string })[]
  >([]);

  const [banner, setBanner] = useState<string | null>(null);
  const [evaluateAllBusy, setEvaluateAllBusy] = useState(false);
  const [evaluateAllProgress, setEvaluateAllProgress] = useState<string | null>(null);
  const hydrated = useRef(false);

  const apiBase = useMemo(() => getApiBase(), []);

  const persist = useCallback(() => {
    savePersisted({
      rubricId,
      rubricName,
      rubricFilename,
      questionCount,
      submissions: submissions.map(({ id, studentId, filename }) => ({
        id,
        studentId,
        filename,
      })),
    });
  }, [rubricId, rubricName, rubricFilename, questionCount, submissions]);

  useEffect(() => {
    const p = loadPersisted();
    if (p) {
      setRubricId(p.rubricId);
      setRubricName(p.rubricName);
      setRubricFilename(p.rubricFilename);
      setQuestionCount(p.questionCount);
      setSubmissions(
        p.submissions.map((s) => ({
          ...s,
          evaluation: undefined,
          loading: false,
          error: undefined,
        }))
      );
    }
    hydrated.current = true;
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !hydrated.current) return;
    persist();
  }, [persist]);

  const loadEvaluationFromServer = useCallback(async (s: StoredSubmission) => {
    try {
      const data = await getResults(s.id);
      if (data.results && Array.isArray(data.results)) {
        const evaluation: EvaluationResponse = {
          submission_id: String(data.submission_id ?? s.id),
          student_id: String(data.student_id ?? s.studentId),
          results: data.results as QuestionResult[],
          total: Number(data.total ?? 0),
          max_total: Number(data.max_total ?? data.total ?? 0),
          plagiarism_flags:
            (data.plagiarism_flags as EvaluationResponse["plagiarism_flags"]) ?? [],
          annotated_pdf_url: (data.annotated_pdf_url as string | null) ?? null,
        };
        return { ...s, evaluation, loading: false, error: undefined };
      }
    } catch {
      /* not evaluated yet */
    }
    return { ...s, loading: false };
  }, []);

  const refreshEvaluations = useCallback(() => {
    setSubmissions((prev) => {
      (async () => {
        const next = await Promise.all(prev.map((s) => loadEvaluationFromServer(s)));
        setSubmissions(next);
      })();
      return prev.map((s) => ({ ...s, loading: true, error: undefined }));
    });
  }, [loadEvaluationFromServer]);

  useEffect(() => {
    if (submissions.length === 0) return;
    let cancelled = false;
    (async () => {
      const next = await Promise.all(
        submissions.map(async (s) => {
          if (s.evaluation) return s;
          try {
            const data = await getResults(s.id);
            if (cancelled) return s;
            if (data.results && Array.isArray(data.results)) {
              const evaluation: EvaluationResponse = {
                submission_id: String(data.submission_id ?? s.id),
                student_id: String(data.student_id ?? s.studentId),
                results: data.results as QuestionResult[],
                total: Number(data.total ?? 0),
                max_total: Number(data.max_total ?? data.total ?? 0),
                plagiarism_flags:
                  (data.plagiarism_flags as EvaluationResponse["plagiarism_flags"]) ?? [],
                annotated_pdf_url: (data.annotated_pdf_url as string | null) ?? null,
              };
              return { ...s, evaluation };
            }
          } catch {
            /* ignore */
          }
          return s;
        })
      );
      if (!cancelled) setSubmissions(next);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once per id list
  }, [submissions.map((s) => s.id).join(",")]);

  async function onRubricUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBanner(null);
    setRubricBusy(true);
    try {
      const res = await uploadRubric(file, rubricName.trim() || "Exam Rubric");
      setRubricId(res.id);
      setRubricFilename(res.filename);
      setQuestionCount(res.question_count);
      setBanner(`Rubric saved: ${res.question_count} questions parsed.`);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Rubric upload failed");
    } finally {
      setRubricBusy(false);
      e.target.value = "";
    }
  }

  async function onSheetUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!studentId.trim()) {
      setBanner("Enter a student ID before uploading an answer sheet.");
      e.target.value = "";
      return;
    }
    setBanner(null);
    setSheetBusy(true);
    try {
      const res = await uploadAnswerSheet(file, studentId.trim(), rubricId);
      setSubmissions((prev) => [
        {
          id: res.id,
          studentId: studentId.trim(),
          filename: res.filename,
        },
        ...prev,
      ]);
      setBanner(`Uploaded answer sheet for ${studentId.trim()}.`);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSheetBusy(false);
      e.target.value = "";
    }
  }

  async function onEvaluateAll() {
    if (!rubricId) {
      setBanner("Upload a marking scheme first (or link rubric on upload).");
      return;
    }
    if (submissions.length === 0) {
      setBanner("No submissions to evaluate.");
      return;
    }

    setEvaluateAllBusy(true);
    setEvaluateAllProgress(null);
    setBanner(null);
    setSubmissions((prev) =>
      prev.map((s) => ({ ...s, loading: true, error: undefined }))
    );

    try {
      const ids = submissions.map((s) => s.id);
      const result = await evaluateAll(rubricId, ids, (current, total) => {
        setEvaluateAllProgress(
          total > 0 ? `Evaluating ${current}/${total}...` : "Evaluating..."
        );
      });

      const next = await Promise.all(submissions.map((s) => loadEvaluationFromServer(s)));
      setSubmissions(next);

      if (result.failed_count === 0 && result.success_count > 0) {
        setBanner("All submissions evaluated successfully");
      } else if (result.failed_count > 0) {
        setBanner(
          `Evaluated ${result.success_count}/${result.total_processed}; ${result.failed_count} failed.`
        );
      } else if (result.total_processed === 0) {
        setBanner("No submissions to evaluate.");
      } else {
        setBanner("All submissions evaluated successfully");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Evaluate all failed";
      setBanner(msg);
      setSubmissions((prev) => prev.map((s) => ({ ...s, loading: false })));
    } finally {
      setEvaluateAllBusy(false);
      setEvaluateAllProgress(null);
    }
  }

  async function onEvaluate(submissionId: string) {
    if (!rubricId) {
      setBanner("Upload a marking scheme first (or link rubric on upload).");
      return;
    }
    setSubmissions((prev) =>
      prev.map((s) =>
        s.id === submissionId ? { ...s, loading: true, error: undefined } : s
      )
    );
    try {
      const evaluation = await evaluateSubmission(submissionId, rubricId, true);
      setSubmissions((prev) =>
        prev.map((s) =>
          s.id === submissionId ? { ...s, evaluation, loading: false } : s
        )
      );
      setBanner(`Evaluation complete for submission ${submissionId.slice(0, 8)}…`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Evaluation failed";
      setSubmissions((prev) =>
        prev.map((s) =>
          s.id === submissionId ? { ...s, loading: false, error: msg } : s
        )
      );
      setBanner(msg);
    }
  }

  function clearSession() {
    localStorage.removeItem(STORAGE_KEY);
    setRubricId(null);
    setRubricFilename(null);
    setQuestionCount(null);
    setSubmissions([]);
    setBanner("Session cleared.");
  }

  return (
    <div className="bg-grid min-h-screen">
      <header className="border-b border-white/10 bg-black/40 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-400/90">
              GRADEOPS
            </p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              Handwritten exam grading
            </h1>
            <p className="mt-2 max-w-xl text-sm text-zinc-400">
              Upload a marking scheme (JSON or PDF), add student answer PDFs, run evaluation,
              then download annotated papers and review per-question marks and remarks.
            </p>
          </div>
          <div className="flex flex-col gap-3">
            <AppNav />
            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-xs text-zinc-400">
              <div className="font-mono text-zinc-300">API</div>
              <div className="mt-1 break-all">{apiBase}</div>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-10 px-4 py-10">
        {banner && (
          <div
            className={`rounded-lg border px-4 py-3 text-sm ${
              banner.toLowerCase().includes("fail") || banner.includes("Enter")
                ? "border-rose-500/40 bg-rose-950/40 text-rose-100"
                : "border-emerald-500/30 bg-emerald-950/30 text-emerald-100"
            }`}
          >
            {banner}
          </div>
        )}

        <section className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-zinc-950/60 p-6 shadow-xl shadow-black/40">
            <h2 className="text-lg font-semibold text-white">1. Marking scheme</h2>
            <p className="mt-1 text-sm text-zinc-500">
              JSON (recommended) or PDF. Parsed questions drive grading.
            </p>
            <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-zinc-500">
              Rubric title
            </label>
            <input
              type="text"
              value={rubricName}
              onChange={(e) => setRubricName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-sm text-white outline-none ring-sky-500/40 focus:ring-2"
              placeholder="e.g. Physics Midterm"
            />
            <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-zinc-500">
              File (.json or .pdf)
            </label>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-50">
                <input
                  type="file"
                  accept=".json,.pdf,application/json,application/pdf"
                  className="hidden"
                  disabled={rubricBusy}
                  onChange={onRubricUpload}
                />
                {rubricBusy ? "Uploading…" : "Choose rubric file"}
              </label>
              {rubricId && (
                <span className="text-xs text-zinc-400">
                  ID <span className="font-mono text-zinc-200">{rubricId}</span>
                  {questionCount != null ? ` · ${questionCount} questions` : ""}
                </span>
              )}
            </div>
            {rubricFilename && (
              <p className="mt-3 text-xs text-zinc-500">
                Last file: <span className="text-zinc-300">{rubricFilename}</span>
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-white/10 bg-zinc-950/60 p-6 shadow-xl shadow-black/40">
            <h2 className="text-lg font-semibold text-white">2. Answer sheets</h2>
            <p className="mt-1 text-sm text-zinc-500">
              PDF only. Each upload needs a student identifier.
            </p>
            <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-zinc-500">
              Student ID
            </label>
            <input
              type="text"
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-sm text-white outline-none ring-sky-500/40 focus:ring-2"
              placeholder="e.g. STU-2024-001"
            />
            <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-zinc-500">
              Answer PDF
            </label>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/10 disabled:opacity-50">
                <input
                  type="file"
                  accept=".pdf,application/pdf"
                  className="hidden"
                  disabled={sheetBusy}
                  onChange={onSheetUpload}
                />
                {sheetBusy ? "Uploading…" : "Choose PDF"}
              </label>
              {!rubricId && (
                <span className="text-xs text-amber-400/90">
                  Upload a rubric first so evaluation can run.
                </span>
              )}
            </div>
          </div>
        </section>

        <BulkUploadSection
          rubricId={rubricId}
          onBanner={setBanner}
          onUploaded={(items: BulkUploadItem[]) => {
            setSubmissions((prev) => [
              ...items.map((u) => ({
                id: u.id,
                studentId: u.student_id,
                filename: u.filename,
              })),
              ...prev,
            ]);
          }}
        />

        <section className="rounded-2xl border border-white/10 bg-zinc-950/60 p-6 shadow-xl shadow-black/40">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-white">3. Submissions & results</h2>
              <p className="mt-1 text-sm text-zinc-500">
                Evaluate each paper, then expand a row for per-question marks and AI remarks.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={refreshEvaluations}
                disabled={evaluateAllBusy}
                className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-white hover:bg-white/10 disabled:opacity-50"
              >
                Refresh from server
              </button>
              <button
                type="button"
                onClick={() => void onEvaluateAll()}
                disabled={evaluateAllBusy || !rubricId || submissions.length === 0}
                className="rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {evaluateAllBusy
                  ? evaluateAllProgress ?? "Evaluating..."
                  : "Evaluate All"}
              </button>
              <button
                type="button"
                onClick={clearSession}
                disabled={evaluateAllBusy}
                className="rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-xs font-medium text-rose-100 hover:bg-rose-950/50 disabled:opacity-50"
              >
                Clear list
              </button>
            </div>
          </div>

          {submissions.length === 0 ? (
            <p className="mt-8 text-center text-sm text-zinc-500">
              No answer sheets yet. Upload at least one PDF above.
            </p>
          ) : (
            <ul className="mt-6 space-y-4">
              {submissions.map((s) => (
                <li
                  key={s.id}
                  className="overflow-hidden rounded-xl border border-white/10 bg-black/40"
                >
                  <SubmissionCard
                    submission={s}
                    rubricId={rubricId}
                    onEvaluate={() => void onEvaluate(s.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>

      <footer className="border-t border-white/10 py-8 text-center text-xs text-zinc-600">
        GRADEOPS · Configure <code className="text-zinc-500">NEXT_PUBLIC_API_URL</code> in{" "}
        <code className="text-zinc-500">frontend/.env.local</code>
      </footer>
    </div>
  );
}

function SubmissionCard({
  submission: s,
  rubricId,
  onEvaluate,
}: {
  submission: StoredSubmission & {
    evaluation?: EvaluationResponse;
    loading?: boolean;
    error?: string;
  };
  rubricId: string | null;
  onEvaluate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ev = s.evaluation;
  const pdfHref =
    ev && s.id ? annotatedPdfHref(ev.annotated_pdf_url, s.id) : annotatedPdfHref(null, s.id);

  return (
    <div>
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-white">{s.studentId}</span>
            <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
              {s.filename}
            </span>
          </div>
          <p className="mt-1 font-mono text-[11px] text-zinc-500">{s.id}</p>
          {s.error && <p className="mt-2 text-xs text-rose-400">{s.error}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {ev && (
            <span className="rounded-lg border border-emerald-500/30 bg-emerald-950/40 px-3 py-1.5 text-sm font-medium text-emerald-200">
              {ev.total} / {ev.max_total} marks
            </span>
          )}
          <a
            href={pdfHref}
            target="_blank"
            rel="noreferrer"
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium ${
              ev
                ? "border-sky-500/40 bg-sky-950/40 text-sky-200 hover:bg-sky-950/60"
                : "pointer-events-none border-white/5 text-zinc-600"
            }`}
          >
            Annotated PDF
          </a>
          <button
            type="button"
            disabled={s.loading || !rubricId}
            onClick={onEvaluate}
            className="rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {s.loading ? "Evaluating…" : ev ? "Re-evaluate" : "Evaluate"}
          </button>
          {ev && (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-zinc-300 hover:bg-white/5"
            >
              {open ? "Hide details" : "Question breakdown"}
            </button>
          )}
        </div>
      </div>
      {open && ev && (
        <div className="border-t border-white/10 bg-black/30 p-4">
          <QuestionTable results={ev.results} />
          <ReviewPanel
            submissionId={s.id}
            results={ev.results}
            onUpdated={() => {}}
          />
          {ev.plagiarism_flags?.length > 0 && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-950/30 p-3 text-xs text-amber-100">
              <div className="font-semibold text-amber-200">Plagiarism flags</div>
              <ul className="mt-2 list-inside list-disc space-y-1">
                {ev.plagiarism_flags.map((f, i) => (
                  <li key={i}>{f.note}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function QuestionTable({ results }: { results: QuestionResult[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-zinc-500">
            <th className="py-2 pr-4">Question</th>
            <th className="py-2 pr-4">Marks</th>
            <th className="py-2 pr-4">Confidence</th>
            <th className="py-2">Remark / justification</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.question} className="border-b border-white/5 align-top text-zinc-200">
              <td className="py-3 pr-4 font-mono text-sky-300">
                {r.question}
                {r.is_blank && (
                  <span className="ml-2 rounded bg-rose-500/20 px-1.5 text-[10px] text-rose-300">
                    blank
                  </span>
                )}
              </td>
              <td className="py-3 pr-4 whitespace-nowrap">
                <span className="font-semibold text-white">{r.marks_awarded}</span>
                <span className="text-zinc-500"> / {r.max_marks}</span>
              </td>
              <td className="py-3 pr-4 text-zinc-400">{(r.confidence * 100).toFixed(0)}%</td>
              <td className="py-3 text-xs leading-relaxed text-zinc-400">{r.justification}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
