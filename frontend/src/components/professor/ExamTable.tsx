"use client";

import { useRouter } from "next/navigation";
import { ExamStatusBadge } from "@/components/grading/Badges";
import { EmptyState, ProgressBar, TD, TH, THead, TR, Table } from "@/components/ui";
import { fmtDate, fmtMarks } from "@/lib/format";
import type { ExamResponse } from "@/lib/types";

/** ``compact`` drops date / processed / average columns for narrow placements. */
export function ExamTable({ exams, empty, compact = false }: { exams: ExamResponse[]; empty?: React.ReactNode; compact?: boolean }) {
  const router = useRouter();
  if (!exams.length) return <>{empty ?? <EmptyState title="No exams yet" />}</>;
  return (
    <Table>
      <THead>
        <tr>
          <TH>Exam</TH>
          {!compact && <TH>Date</TH>}
          <TH align="right">Submissions</TH>
          {!compact && <TH align="right">Processed</TH>}
          <TH align="right">Pending</TH>
          <TH align="right">Reviewed</TH>
          <TH align="right">Escalated</TH>
          {!compact && <TH align="right">Average</TH>}
          <TH>Status</TH>
        </tr>
      </THead>
      <tbody>
        {exams.map((e) => {
          const c = e.counts;
          const reviewed = c.ta_reviewed + c.professor_approved + c.published;
          return (
            <TR key={e.id} onClick={() => router.push(`/professor/exams/${e.id}`)}>
              <TD>
                <div className="min-w-[10rem] font-medium">{e.name}</div>
                <div className="text-xs text-fg-subtle">
                  {e.course_code} · {e.exam_type}
                </div>
              </TD>
              {!compact && <TD className="whitespace-nowrap text-sm text-fg-muted">{fmtDate(e.exam_date)}</TD>}
              <TD align="right">{c.submissions}</TD>
              {!compact && (
                <TD align="right">
                  {c.processed}
                  {c.failed > 0 && <span className="ml-1 text-xs text-rose-600 dark:text-rose-400">({c.failed} failed)</span>}
                </TD>
              )}
              <TD align="right">{c.awaiting_ta}</TD>
              <TD align="right">
                <div className="flex items-center justify-end gap-2">
                  <span>{reviewed}</span>
                  <div className="w-16">
                    <ProgressBar value={reviewed} max={Math.max(c.processed, 1)} tone="success" label="Review progress" />
                  </div>
                </div>
              </TD>
              <TD align="right" className={c.escalated ? "font-semibold text-rose-600 dark:text-rose-400" : ""}>
                {c.escalated}
              </TD>
              {!compact && <TD align="right" className="whitespace-nowrap">{e.average_score !== null ? `${fmtMarks(e.average_score)} / ${fmtMarks(e.max_score)}` : "—"}</TD>}
              <TD>
                <ExamStatusBadge status={e.status} />
              </TD>
            </TR>
          );
        })}
      </tbody>
    </Table>
  );
}
