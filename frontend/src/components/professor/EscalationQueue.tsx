"use client";

import { useRouter } from "next/navigation";
import { ConfidenceBadge, ReviewStatusBadge } from "@/components/grading/Badges";
import { ButtonLink, EmptyState, TD, TH, THead, TR, Table } from "@/components/ui";
import { fmtMarks, fmtRelative } from "@/lib/format";
import type { EscalationResponse } from "@/lib/types";

export function EscalationQueue({ items }: { items: EscalationResponse[] }) {
  const router = useRouter();
  if (!items.length) return <div className="p-4"><EmptyState title="No escalations" description="Submissions TAs escalate for your decision appear here." /></div>;
  return (
    <Table>
      <THead>
        <tr>
          <TH>Student</TH>
          <TH>Exam</TH>
          <TH>Escalated by</TH>
          <TH>Reason</TH>
          <TH align="right">AI score</TH>
          <TH align="right">TA score</TH>
          <TH>Confidence</TH>
          <TH>Status</TH>
          <TH />
        </tr>
      </THead>
      <tbody>
        {items.map((e) => (
          <TR key={e.submission_id} onClick={() => router.push(`/professor/reviews/${e.submission_id}`)}>
            <TD>
              <div className="font-mono text-sm">{e.student_id}</div>
              {e.student_name && <div className="text-xs text-fg-subtle">{e.student_name}</div>}
            </TD>
            <TD>
              <div className="text-sm">{e.exam_name}</div>
              <div className="text-xs text-fg-subtle">{e.course_code}</div>
            </TD>
            <TD className="text-sm">
              {e.escalated_by?.full_name ?? "—"}
              <div className="text-xs text-fg-subtle">{fmtRelative(e.escalated_at)}</div>
            </TD>
            <TD className="max-w-xs">
              <div className="text-sm font-medium">{e.reason_label ?? e.reason}</div>
              {e.notes && <div className="truncate text-xs text-fg-muted" title={e.notes}>“{e.notes}”</div>}
            </TD>
            <TD align="right">{fmtMarks(e.ai_score)}</TD>
            <TD align="right">{fmtMarks(e.ta_score)}</TD>
            <TD>
              <ConfidenceBadge value={e.min_confidence} />
            </TD>
            <TD>
              <ReviewStatusBadge status={e.review_status} />
            </TD>
            <TD align="right">
              <ButtonLink href={`/professor/reviews/${e.submission_id}`} size="sm" variant={e.review_status === "escalated" ? "primary" : "secondary"}>
                {e.review_status === "escalated" ? "Inspect & resolve" : "View"}
              </ButtonLink>
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
