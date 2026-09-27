"use client";

import { useState } from "react";
import { ConfidenceBadge, ReviewStatusBadge, SubmissionStatusBadge } from "@/components/grading/Badges";
import { Badge, Button, ButtonLink, Card, CardHeader, ConfirmDialog, EmptyState, ErrorState, Select, SkeletonRows, TD, TH, THead, TR, Table } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { fmtMarks } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ReviewStatus, SubmissionRow } from "@/lib/types";

export function ExamSubmissionsTable({ examId, editable, refreshKey, onChanged }: { examId: string; editable: boolean; refreshKey: number; onChanged: () => void }) {
  const [filter, setFilter] = useState<ReviewStatus | "">("");
  const list = useApi(() => exams.submissions(examId, { review_status: filter || undefined }), [examId, filter, refreshKey]);
  const [deleting, setDeleting] = useState<SubmissionRow | null>(null);
  const [busy, setBusy] = useState(false);

  async function remove(s: SubmissionRow) {
    setBusy(true);
    try {
      await exams.deleteSubmission(examId, s.id);
      setDeleting(null);
      await list.reload();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Submissions"
        description={list.data ? `${list.data.total} submission${list.data.total === 1 ? "" : "s"}` : undefined}
        actions={
          <Select aria-label="Filter by review status" className="w-48" value={filter} onChange={(e) => setFilter(e.target.value as ReviewStatus | "")}>
            <option value="">All review states</option>
            <option value="ai_evaluated">Review required</option>
            <option value="ta_pending">Returned to TA</option>
            <option value="ta_approved">TA approved</option>
            <option value="ta_overridden">TA overridden</option>
            <option value="escalated">Escalated</option>
            <option value="professor_approved">Professor approved</option>
            <option value="published">Published</option>
            <option value="not_evaluated">Not evaluated</option>
          </Select>
        }
      />
      {list.error && <div className="p-4"><ErrorState message={list.error} onRetry={list.reload} /></div>}
      {!list.data && !list.error && <SkeletonRows rows={4} className="p-4" />}
      {list.data && list.data.items.length === 0 && <div className="p-4"><EmptyState title="No submissions" description={filter ? "Nothing in this state." : "Upload answer sheets to begin."} /></div>}
      {list.data && list.data.items.length > 0 && (
        <Table>
          <THead>
            <tr>
              <TH>Student</TH>
              <TH>Status</TH>
              <TH align="right">AI</TH>
              <TH align="right">Final</TH>
              <TH>Confidence</TH>
              <TH>Reviewer</TH>
              <TH />
            </tr>
          </THead>
          <tbody>
            {list.data.items.map((s) => (
              <TR key={s.id}>
                <TD>
                  <div className="font-mono text-sm">{s.student_id}</div>
                  <div className="text-xs text-fg-subtle">{s.student_name ?? s.source_filename}</div>
                </TD>
                <TD>
                  <div className="flex flex-wrap gap-1">
                    {s.status === "evaluated" ? <ReviewStatusBadge status={s.review_status} /> : <SubmissionStatusBadge status={s.status} />}
                    {s.integrity_open > 0 && <Badge tone="danger">Similarity</Badge>}
                    {s.needs_manual_grading && s.review_status === "ai_evaluated" && <Badge tone="warning">Manual</Badge>}
                  </div>
                  {s.error_message && <div className="mt-0.5 max-w-[14rem] truncate text-[11px] text-rose-600 dark:text-rose-400" title={s.error_message}>{s.error_message}</div>}
                </TD>
                <TD align="right">{fmtMarks(s.ai_total_marks)}</TD>
                <TD align="right" className="whitespace-nowrap font-medium">
                  {s.status === "evaluated" ? `${fmtMarks(s.total_marks)} / ${fmtMarks(s.max_total)}` : "—"}
                </TD>
                <TD>{s.min_confidence !== null ? <ConfidenceBadge value={s.min_confidence} /> : "—"}</TD>
                <TD className="text-xs text-fg-muted">{s.reviewed_by?.full_name ?? (s.assigned_ta ? `→ ${s.assigned_ta.full_name}` : "—")}</TD>
                <TD align="right">
                  <div className="flex justify-end gap-1">
                    {s.status === "evaluated" && (
                      <ButtonLink href={`/professor/reviews/${s.id}`} size="sm">
                        Review
                      </ButtonLink>
                    )}
                    {editable && (s.review_status === "not_evaluated" || s.review_status === "ai_evaluated") && s.status !== "processing" && (
                      <Button size="sm" variant="ghost" onClick={() => setDeleting(s)} aria-label={`Remove submission ${s.student_id}`}>
                        Remove
                      </Button>
                    )}
                  </div>
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <ConfirmDialog
        open={!!deleting}
        title={`Remove ${deleting?.student_id}'s submission?`}
        description="Use this for a wrong or duplicate upload. Submissions that have been reviewed by a human cannot be removed."
        confirmLabel="Remove submission"
        tone="danger"
        busy={busy}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && void remove(deleting)}
      />
    </Card>
  );
}
