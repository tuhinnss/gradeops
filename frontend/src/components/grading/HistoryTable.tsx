import Link from "next/link";
import { Badge, EmptyState, TD, TH, THead, TR, Table } from "@/components/ui";
import { actionLabel, fmtDateTime, fmtMarks } from "@/lib/format";
import type { ReviewHistoryItem } from "@/lib/types";
import { ESCALATION_REASONS } from "@/lib/types";

const TONE: Record<string, "success" | "violet" | "danger" | "neutral"> = { approve: "success", override: "violet", escalate: "danger" };
const REASON_LABEL: Record<string, string> = Object.fromEntries(ESCALATION_REASONS.map((r) => [r.value, r.label]));

export function HistoryTable({ items, reviewBasePath }: { items: ReviewHistoryItem[]; reviewBasePath: string }) {
  if (!items.length) return <EmptyState title="No review history yet" description="Your approvals, overrides and escalations will be listed here." />;
  return (
    <Table>
      <THead>
        <tr>
          <TH>Date</TH>
          <TH>Exam</TH>
          <TH>Student</TH>
          <TH>Question</TH>
          <TH>Action</TH>
          <TH align="right">Old marks</TH>
          <TH align="right">New marks</TH>
          <TH>Reason / notes</TH>
        </tr>
      </THead>
      <tbody>
        {items.map((h) => (
          <TR key={h.id}>
            <TD className="whitespace-nowrap text-xs text-fg-muted">{fmtDateTime(h.created_at)}</TD>
            <TD>
              <div className="text-sm">{h.exam_name ?? "—"}</div>
              <div className="text-xs text-fg-subtle">{h.course_code}</div>
            </TD>
            <TD>
              <Link href={`${reviewBasePath}/${h.submission_id}`} className="font-mono text-accent hover:underline">
                {h.student_id}
              </Link>
            </TD>
            <TD>{h.question ?? "—"}</TD>
            <TD>
              <Badge tone={TONE[h.action] ?? "neutral"}>{actionLabel(h.action)}</Badge>
            </TD>
            <TD align="right">{fmtMarks(h.old_marks)}</TD>
            <TD align="right">{fmtMarks(h.new_marks)}</TD>
            <TD className="max-w-xs text-xs text-fg-muted">
              {h.reason && <div>{REASON_LABEL[h.reason] ?? h.reason}</div>}
              {h.notes && <div className="truncate">“{h.notes}”</div>}
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
