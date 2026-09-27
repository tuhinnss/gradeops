"use client";

import { useEffect, useMemo, useState } from "react";
import { Alert, Button, FieldError, Input, Label, Modal, Textarea } from "@/components/ui";
import { fmtMarks } from "@/lib/format";
import { changedOverrides, validateOverride, type OverrideDraft } from "@/lib/overrides";
import type { QuestionOverride, ReviewQuestion } from "@/lib/types";

const REASON_SUGGESTIONS = [
  "Correct method not recognised by AI",
  "OCR misread the answer",
  "Partial credit per rubric",
  "Answer does not meet the rubric",
  "Calculation error missed by AI",
];

export type OverrideSubmit = { overrides: QuestionOverride[]; reason: string; notes: string };

/**
 * Change marks for one or more questions. Used for TA overrides and, with
 * ``mode="resolve"``, for a professor resolving an escalation (changes optional).
 */
export function OverrideDialog({
  open,
  questions,
  focusQuestion,
  mode = "override",
  busy,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean;
  questions: ReviewQuestion[];
  focusQuestion: string | null;
  mode?: "override" | "resolve";
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (v: OverrideSubmit) => void;
}) {
  const [drafts, setDrafts] = useState<OverrideDraft[]>([]);
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!open) return;
    setDrafts(questions.map((q) => ({ question: q.question, maxMarks: q.max_marks, current: q.marks_awarded, value: "", comment: "" })));
    setReason("");
    setNotes("");
  }, [open, questions]);

  const ordered = useMemo(() => {
    if (!focusQuestion) return drafts;
    return [...drafts].sort((a, b) => Number(b.question === focusQuestion) - Number(a.question === focusQuestion));
  }, [drafts, focusQuestion]);

  const errors = drafts.map(validateOverride);
  const changes = changedOverrides(drafts);
  const hasErrors = errors.some(Boolean);
  const needReason = mode === "override" || changes.length > 0;
  const canSubmit =
    !hasErrors &&
    (mode === "resolve" ? notes.trim().length > 0 || changes.length > 0 : changes.length > 0) &&
    (!needReason || reason.trim().length >= 3);

  function update(question: string, patch: Partial<OverrideDraft>) {
    setDrafts((ds) => ds.map((d) => (d.question === question ? { ...d, ...patch } : d)));
  }

  return (
    <Modal
      open={open}
      size="lg"
      onClose={onClose}
      title={mode === "resolve" ? "Resolve escalation" : "Override marks"}
      description={
        mode === "resolve"
          ? "Adjust marks if needed, then record your decision. The submission becomes professor-approved."
          : "Enter new marks only for questions you are changing. Every change is recorded with the reason."
      }
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={busy}
            disabled={!canSubmit}
            onClick={() => onSubmit({ overrides: changes, reason: reason.trim(), notes: notes.trim() })}
          >
            {mode === "resolve" ? "Resolve & approve" : `Save ${changes.length || ""} override${changes.length === 1 ? "" : "s"}`}
          </Button>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit({ overrides: changes, reason: reason.trim(), notes: notes.trim() });
        }}
      >
        {error && <Alert tone="error">{error}</Alert>}
        <div className="overflow-hidden rounded-md border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-raised text-[11px] uppercase tracking-wide text-fg-subtle">
              <tr>
                <th className="px-3 py-1.5 text-left">Question</th>
                <th className="px-3 py-1.5 text-right">Current</th>
                <th className="px-3 py-1.5 text-left">New marks</th>
                <th className="px-3 py-1.5 text-left">Comment (optional)</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((d) => {
                const err = errors[drafts.indexOf(d)];
                return (
                  <tr key={d.question} className="border-t border-line align-top">
                    <td className="px-3 py-2 font-medium text-fg">{d.question}</td>
                    <td className="tabular px-3 py-2 text-right text-fg-muted">
                      {fmtMarks(d.current)} / {fmtMarks(d.maxMarks)}
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        type="number"
                        inputMode="decimal"
                        step="0.5"
                        min={0}
                        max={d.maxMarks}
                        aria-label={`New marks for ${d.question}`}
                        aria-invalid={!!err}
                        placeholder={fmtMarks(d.current)}
                        value={d.value}
                        onChange={(e) => update(d.question, { value: e.target.value })}
                        className="w-24"
                        autoFocus={d.question === focusQuestion}
                      />
                      <FieldError>{err}</FieldError>
                    </td>
                    <td className="px-3 py-2">
                      <Input aria-label={`Comment for ${d.question}`} value={d.comment} onChange={(e) => update(d.question, { comment: e.target.value })} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {needReason && (
          <div>
            <Label htmlFor="override-reason" hint="(required)">
              Reason
            </Label>
            <Input id="override-reason" list="override-reasons" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
            <datalist id="override-reasons">
              {REASON_SUGGESTIONS.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </div>
        )}
        <div>
          <Label htmlFor="override-notes" hint={mode === "resolve" ? "(required if marks are unchanged)" : "(optional)"}>
            Notes
          </Label>
          <Textarea id="override-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} />
        </div>
      </form>
    </Modal>
  );
}
