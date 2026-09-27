import { Badge } from "@/components/ui";
import { confidenceTone, EXAM_STATUS, fmtConfidence, REVIEW_STATUS, SUBMISSION_STATUS } from "@/lib/format";
import type { ExamStatus, ReviewStatus, SubmissionStatus } from "@/lib/types";

export function ConfidenceBadge({ value, label = false }: { value: number | null | undefined; label?: boolean }) {
  return (
    <Badge tone={confidenceTone(value)} title="AI confidence">
      {label && "Confidence "}
      <span className="tabular">{fmtConfidence(value)}</span>
    </Badge>
  );
}

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const s = REVIEW_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function ExamStatusBadge({ status }: { status: ExamStatus }) {
  const s = EXAM_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function SubmissionStatusBadge({ status }: { status: SubmissionStatus }) {
  const s = SUBMISSION_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}
