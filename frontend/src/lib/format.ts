import type { ExamStatus, ReviewStatus, SubmissionStatus } from "./types";

export function fmtMarks(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(digits);
}

export function fmtScore(value: number | null | undefined, max: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return max ? `${fmtMarks(value)} / ${fmtMarks(max)}` : fmtMarks(value);
}

export function fmtPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** Confidence is stored 0–1. */
export function fmtConfidence(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtRelative(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "—";
  const diff = (now.getTime() - new Date(value).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return fmtDate(value);
}

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "violet";

export const REVIEW_STATUS: Record<ReviewStatus, { label: string; tone: Tone }> = {
  not_evaluated: { label: "Not evaluated", tone: "neutral" },
  ai_evaluated: { label: "Review required", tone: "info" },
  ta_pending: { label: "Returned to TA", tone: "warning" },
  ta_approved: { label: "TA approved", tone: "success" },
  ta_overridden: { label: "TA overridden", tone: "violet" },
  escalated: { label: "Escalated", tone: "danger" },
  professor_approved: { label: "Professor approved", tone: "success" },
  published: { label: "Published", tone: "success" },
};

export const EXAM_STATUS: Record<ExamStatus, { label: string; tone: Tone }> = {
  draft: { label: "Setup", tone: "neutral" },
  processing: { label: "AI processing", tone: "info" },
  ta_review: { label: "TA review", tone: "warning" },
  approved: { label: "Professor approved", tone: "violet" },
  locked: { label: "Locked", tone: "violet" },
  published: { label: "Published", tone: "success" },
};

export const SUBMISSION_STATUS: Record<SubmissionStatus, { label: string; tone: Tone }> = {
  uploaded: { label: "Uploaded", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  ocr_complete: { label: "OCR complete", tone: "info" },
  evaluated: { label: "AI evaluated", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export const AUDIT_ACTION_LABEL: Record<string, string> = {
  approve: "Approved",
  override: "Overridden",
  escalate: "Escalated",
  resolve: "Escalation resolved",
  return_to_ta: "Returned to TA",
  re_evaluated: "AI re-evaluated",
  professor_approve_exam: "Professor approved (exam)",
  publish: "Published",
  reopen: "Reopened",
  created: "Exam created",
  rubric_uploaded: "Rubric uploaded",
  rubric_linked: "Rubric linked",
  rubric_edited: "Rubric edited",
  ta_assigned: "TA assigned",
  ta_unassigned: "TA unassigned",
  distributed: "Submissions distributed",
  submissions_uploaded: "Submissions uploaded",
  submission_deleted: "Submission removed",
  processing_started: "AI processing started",
  processing_finished: "AI processing finished",
  lock: "Grades locked",
  gradebook_exported: "Gradebook exported",
};

export function actionLabel(action: string): string {
  return AUDIT_ACTION_LABEL[action] ?? action.replace(/_/g, " ");
}

export function confidenceTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined) return "neutral";
  if (value < 0.5) return "danger";
  if (value < 0.7) return "warning";
  return "success";
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
