"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Card, CardHeader, ConfirmDialog, ProgressBar } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useInterval } from "@/lib/hooks";
import type { BatchJobResponse, ExamDetailResponse } from "@/lib/types";

/** Start the AI pipeline for an exam and monitor its batch job. */
export function ProcessingPanel({ exam, onChanged }: { exam: ExamDetailResponse; onChanged: () => void }) {
  const [job, setJob] = useState<BatchJobResponse | null>(exam.latest_job ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRe, setConfirmRe] = useState(false);
  useEffect(() => setJob(exam.latest_job ?? null), [exam.latest_job]);

  const running = job?.status === "queued" || job?.status === "running";
  useInterval(async () => {
    if (!job) return;
    const next = await exams.job(job.id);
    setJob(next);
    if (next.status !== "queued" && next.status !== "running") onChanged();
  }, 2000, running);

  const c = exam.counts;
  const unevaluated = c.uploaded + c.failed;
  const canRun = (exam.status === "draft" || exam.status === "ta_review") && !!exam.rubric;

  async function start(reevaluate: boolean) {
    setBusy(true);
    setError(null);
    try {
      setJob(await exams.evaluate(exam.id, reevaluate));
      setConfirmRe(false);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start evaluation");
    } finally {
      setBusy(false);
    }
  }

  const done = job ? job.completed_count + job.failed_count : 0;
  return (
    <Card>
      <CardHeader
        title="AI processing"
        description="OCR → question segmentation → rubric evaluation → similarity check. Results are provisional until reviewed."
        actions={
          <>
            <Button size="sm" variant="primary" loading={busy && !confirmRe} disabled={!canRun || running || unevaluated === 0} onClick={() => void start(false)}>
              {unevaluated ? `Evaluate ${unevaluated} submission${unevaluated === 1 ? "" : "s"}` : "All evaluated"}
            </Button>
            <Button size="sm" disabled={!canRun || running || c.processed === 0} onClick={() => setConfirmRe(true)}>
              Re-evaluate all
            </Button>
          </>
        }
      />
      <div className="space-y-3 p-4">
        {!exam.rubric && <Alert tone="warning">Upload a rubric before running evaluation.</Alert>}
        {error && <Alert tone="error" onDismiss={() => setError(null)}>{error}</Alert>}
        {job ? (
          <div>
            <div className="mb-1 flex justify-between text-xs text-fg-muted">
              <span>
                Latest job · <b className="text-fg">{job.status}</b>
              </span>
              <span className="tabular">
                {done} / {job.total_count} processed{job.failed_count ? ` · ${job.failed_count} failed` : ""}
              </span>
            </div>
            <ProgressBar value={done} max={Math.max(job.total_count, 1)} tone={job.failed_count ? "warning" : "accent"} label="Processing progress" />
            {job.errors.length > 0 && (
              <details className="mt-2 text-xs text-fg-muted">
                <summary className="cursor-pointer">{job.errors.length} error(s)</summary>
                <ul className="mt-1 list-inside list-disc">
                  {job.errors.slice(0, 20).map((e, i) => (
                    <li key={i} className="break-all">
                      {e.submission_id ? `${e.submission_id.slice(0, 8)}…: ` : ""}
                      {e.error ?? e.message}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ) : (
          <p className="text-sm text-fg-subtle">No evaluation has run for this exam yet.</p>
        )}
      </div>
      <ConfirmDialog
        open={confirmRe}
        title="Re-evaluate every submission?"
        description="All AI grades are recomputed and every submission returns to “review required”. Previous TA and professor decisions stay in the audit history but no longer apply."
        confirmLabel="Re-evaluate all"
        tone="danger"
        busy={busy}
        onClose={() => setConfirmRe(false)}
        onConfirm={() => void start(true)}
      />
    </Card>
  );
}
