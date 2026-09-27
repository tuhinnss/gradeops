"use client";

import { useMemo, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { BulkUploadSection } from "@/components/BulkUploadSection";
import { SubmissionCard } from "@/components/workbench/SubmissionCard";
import { AnswerSheetUploadCard, RubricUploadCard } from "@/components/workbench/UploadCards";
import { useWorkbenchSession } from "@/components/workbench/useWorkbenchSession";
import { evaluateAll, evaluateSubmission, getApiBase, uploadAnswerSheet, uploadRubric, type BulkUploadItem } from "@/lib/api";

/**
 * Original single-upload grading workbench (rubric → answer sheets → evaluate).
 * Kept for quick one-off grading; course-based grading lives in /professor.
 */
export function GradeOpsDashboard() {
  const wb = useWorkbenchSession();
  const { rubricId, submissions, setSubmissions } = wb;
  const [rubricBusy, setRubricBusy] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [sheetBusy, setSheetBusy] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [evaluateAllBusy, setEvaluateAllBusy] = useState(false);
  const [evaluateAllProgress, setEvaluateAllProgress] = useState<string | null>(null);
  const apiBase = useMemo(() => getApiBase(), []);

  async function onRubricUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBanner(null);
    setRubricBusy(true);
    try {
      const res = await uploadRubric(file, wb.rubricName.trim() || "Exam Rubric");
      wb.setRubricId(res.id);
      wb.setRubricFilename(res.filename);
      wb.setQuestionCount(res.question_count);
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
      setSubmissions((prev) => [{ id: res.id, studentId: studentId.trim(), filename: res.filename }, ...prev]);
      setBanner(`Uploaded answer sheet for ${studentId.trim()}.`);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSheetBusy(false);
      e.target.value = "";
    }
  }

  async function onEvaluateAll() {
    if (!rubricId) return setBanner("Upload a marking scheme first (or link rubric on upload).");
    if (submissions.length === 0) return setBanner("No submissions to evaluate.");
    setEvaluateAllBusy(true);
    setEvaluateAllProgress(null);
    setBanner(null);
    setSubmissions((prev) => prev.map((s) => ({ ...s, loading: true, error: undefined })));
    try {
      const result = await evaluateAll(rubricId, submissions.map((s) => s.id), (current, total) =>
        setEvaluateAllProgress(total > 0 ? `Evaluating ${current}/${total}...` : "Evaluating..."),
      );
      await wb.refreshAll(submissions);
      if (result.failed_count > 0) setBanner(`Evaluated ${result.success_count}/${result.total_processed}; ${result.failed_count} failed.`);
      else if (result.total_processed === 0) setBanner("No submissions to evaluate.");
      else setBanner("All submissions evaluated successfully");
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Evaluate all failed");
      setSubmissions((prev) => prev.map((s) => ({ ...s, loading: false })));
    } finally {
      setEvaluateAllBusy(false);
      setEvaluateAllProgress(null);
    }
  }

  async function onEvaluate(submissionId: string) {
    if (!rubricId) return setBanner("Upload a marking scheme first (or link rubric on upload).");
    setSubmissions((prev) => prev.map((s) => (s.id === submissionId ? { ...s, loading: true, error: undefined } : s)));
    try {
      const evaluation = await evaluateSubmission(submissionId, rubricId, true);
      setSubmissions((prev) => prev.map((s) => (s.id === submissionId ? { ...s, evaluation, loading: false } : s)));
      setBanner(`Evaluation complete for submission ${submissionId.slice(0, 8)}…`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Evaluation failed";
      setSubmissions((prev) => prev.map((s) => (s.id === submissionId ? { ...s, loading: false, error: msg } : s)));
      setBanner(msg);
    }
  }

  const bannerIsError = banner && (banner.toLowerCase().includes("fail") || banner.includes("Enter"));

  return (
    <div className="bg-grid min-h-screen">
      <header className="border-b border-white/10 bg-black/40 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-400/90">GRADEOPS · Workbench</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Handwritten exam grading</h1>
            <p className="mt-2 max-w-xl text-sm text-zinc-400">
              Upload a marking scheme (JSON or PDF), add student answer PDFs, run evaluation, then download annotated papers and review per-question marks and remarks.
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
          <div className={`rounded-lg border px-4 py-3 text-sm ${bannerIsError ? "border-rose-500/40 bg-rose-950/40 text-rose-100" : "border-emerald-500/30 bg-emerald-950/30 text-emerald-100"}`}>
            {banner}
          </div>
        )}

        <section className="grid gap-6 lg:grid-cols-2">
          <RubricUploadCard
            rubricName={wb.rubricName}
            onRubricName={wb.setRubricName}
            rubricId={rubricId}
            questionCount={wb.questionCount}
            rubricFilename={wb.rubricFilename}
            busy={rubricBusy}
            onFile={onRubricUpload}
          />
          <AnswerSheetUploadCard studentId={studentId} onStudentId={setStudentId} busy={sheetBusy} hasRubric={!!rubricId} onFile={onSheetUpload} />
        </section>

        <BulkUploadSection
          rubricId={rubricId}
          onBanner={setBanner}
          onUploaded={(items: BulkUploadItem[]) =>
            setSubmissions((prev) => [...items.map((u) => ({ id: u.id, studentId: u.student_id, filename: u.filename })), ...prev])
          }
        />

        <section className="rounded-2xl border border-white/10 bg-zinc-950/60 p-6 shadow-xl shadow-black/40">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-white">3. Submissions & results</h2>
              <p className="mt-1 text-sm text-zinc-500">Evaluate each paper, then expand a row for per-question marks and AI remarks.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setSubmissions((prev) => prev.map((s) => ({ ...s, loading: true, error: undefined })));
                  void wb.refreshAll(submissions);
                }}
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
                {evaluateAllBusy ? evaluateAllProgress ?? "Evaluating..." : "Evaluate All"}
              </button>
              <button
                type="button"
                onClick={() => {
                  wb.clear();
                  setBanner("Session cleared.");
                }}
                disabled={evaluateAllBusy}
                className="rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-xs font-medium text-rose-100 hover:bg-rose-950/50 disabled:opacity-50"
              >
                Clear list
              </button>
            </div>
          </div>

          {submissions.length === 0 ? (
            <p className="mt-8 text-center text-sm text-zinc-500">No answer sheets yet. Upload at least one PDF above.</p>
          ) : (
            <ul className="mt-6 space-y-4">
              {submissions.map((s) => (
                <li key={s.id} className="overflow-hidden rounded-xl border border-white/10 bg-black/40">
                  <SubmissionCard submission={s} rubricId={rubricId} onEvaluate={() => void onEvaluate(s.id)} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>

      <footer className="border-t border-white/10 py-8 text-center text-xs text-zinc-600">
        GRADEOPS · Configure <code className="text-zinc-500">NEXT_PUBLIC_API_URL</code> in <code className="text-zinc-500">frontend/.env.local</code>
      </footer>
    </div>
  );
}
