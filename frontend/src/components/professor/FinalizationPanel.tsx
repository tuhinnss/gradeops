"use client";

import { useState } from "react";
import { Alert, Button, Card, CardHeader, ConfirmDialog, ErrorState, Label, SkeletonRows, Textarea } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import type { ExamDetailResponse, FinalizationSummary } from "@/lib/types";

type Step = null | "approve" | "lock" | "publish" | "reopen";

function SummaryList({ s }: { s: FinalizationSummary }) {
  const rows: [string, number, boolean?][] = [
    ["Submissions", s.total],
    ["AI evaluated", s.evaluated],
    ["Awaiting human review", s.awaiting_ta, s.awaiting_ta > 0],
    ["TA reviewed", s.ta_reviewed],
    ["Escalations unresolved", s.escalated, s.escalated > 0],
    ["Professor approved", s.professor_approved],
    ["TA overrides", s.ta_overrides],
    ["Professor overrides", s.professor_overrides],
    ["Unresolved similarity flags", s.integrity_open, s.integrity_open > 0],
    ["Failed processing", s.failed, s.failed > 0],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
      {rows.map(([label, value, warn]) => (
        <div key={label} className="flex justify-between border-b border-line py-1">
          <dt className="text-fg-muted">{label}</dt>
          <dd className={`tabular font-medium ${warn ? "text-amber-700 dark:text-amber-300" : "text-fg"}`}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Professor controls: approve → lock → publish, and an audited reopen. */
export function FinalizationPanel({ exam, onChanged }: { exam: ExamDetailResponse; onChanged: (e: ExamDetailResponse) => void }) {
  const summary = useApi(() => exams.publishSummary(exam.id), [exam.id, exam.status, exam.updated_at, exam.counts]);
  const [step, setStep] = useState<Step>(null);
  const [notes, setNotes] = useState("");
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const s = summary.data;

  function open(next: Step) {
    setStep(next);
    setNotes("");
    setAck(false);
    setError(null);
  }

  async function confirm() {
    if (!step) return;
    setBusy(true);
    setError(null);
    try {
      const updated =
        step === "approve" ? await exams.approve(exam.id, notes || undefined)
        : step === "lock" ? await exams.lock(exam.id, notes || undefined)
        : step === "publish" ? await exams.publish(exam.id, ack, notes || undefined)
        : await exams.reopen(exam.id, notes);
      setStep(null);
      onChanged(updated);
      await summary.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const titles: Record<Exclude<Step, null>, string> = {
    approve: "Approve all grades",
    lock: "Lock grades",
    publish: "Publish grades",
    reopen: "Reopen grades",
  };
  const descriptions: Record<Exclude<Step, null>, string> = {
    approve: "Every TA-reviewed submission becomes professor-approved. TAs can no longer change grades.",
    lock: "Grades are frozen. Nothing can change until you reopen the exam.",
    publish: "Grades are released as final. Any later change requires an explicit, audited reopen.",
    reopen: "Published/locked grades become editable again. The reason is recorded in the audit trail.",
  };

  return (
    <Card>
      <CardHeader title="Finalisation" description="You are the final authority on released grades." />
      <div className="space-y-3 p-4">
        {summary.error && <ErrorState message={summary.error} onRetry={summary.reload} />}
        {!s && !summary.error && <SkeletonRows rows={3} />}
        {s && (
          <>
            {s.blockers.length > 0 && (
              <Alert tone="warning">
                <ul className="list-inside list-disc">
                  {s.blockers.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              </Alert>
            )}
            {s.blockers.length === 0 && s.warnings.map((w) => <Alert key={w} tone="info">{w}</Alert>)}
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={!s.can_approve} onClick={() => open("approve")}>
                Approve exam
              </Button>
              <Button disabled={!s.can_lock} onClick={() => open("lock")}>
                Lock grades
              </Button>
              <Button variant="success" disabled={!s.can_publish} onClick={() => open("publish")}>
                Publish grades
              </Button>
              <Button variant="ghost" disabled={!s.can_reopen} onClick={() => open("reopen")}>
                Reopen grades
              </Button>
            </div>
          </>
        )}
      </div>
      <ConfirmDialog
        open={!!step}
        title={step ? titles[step] : ""}
        description={step ? descriptions[step] : undefined}
        confirmLabel={step ? titles[step] : "Confirm"}
        tone={step === "publish" ? "success" : step === "reopen" ? "danger" : "primary"}
        busy={busy}
        confirmDisabled={(step === "reopen" && notes.trim().length < 5) || (step === "publish" && !!s?.integrity_open && !ack)}
        onClose={() => setStep(null)}
        onConfirm={() => void confirm()}
      >
        <div className="space-y-3">
          {error && <Alert tone="error">{error}</Alert>}
          {s && step !== "reopen" && <SummaryList s={s} />}
          {step === "publish" && s && s.integrity_open > 0 && (
            <label className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-fg">
              <input type="checkbox" className="mt-0.5" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              I have seen the {s.integrity_open} unresolved similarity flag(s) and want to publish anyway.
            </label>
          )}
          <div>
            <Label htmlFor="final-notes" hint={step === "reopen" ? "(required, min 5 characters)" : "(optional)"}>
              {step === "reopen" ? "Reason for reopening" : "Notes for the audit trail"}
            </Label>
            <Textarea id="final-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
      </ConfirmDialog>
    </Card>
  );
}
