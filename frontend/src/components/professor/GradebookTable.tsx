"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AuditTimeline } from "@/components/grading/AuditTimeline";
import { Badge, Button, ButtonLink, EmptyState, Input, Modal, SkeletonRows, TD, TH, THead, TR, Table } from "@/components/ui";
import { review } from "@/lib/endpoints";
import { fmtMarks, fmtPct, REVIEW_STATUS } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { GradebookResponse, GradebookRow } from "@/lib/types";

function HistoryModal({ row, onClose }: { row: GradebookRow; onClose: () => void }) {
  const d = useApi(() => review.detail(row.submission_id!), [row.submission_id]);
  return (
    <Modal open onClose={onClose} size="lg" title={`History · ${row.student_id}`} description={row.student_name ?? undefined}>
      {d.data ? <AuditTimeline items={d.data.audit_history} /> : <SkeletonRows rows={3} />}
    </Modal>
  );
}

export function GradebookTable({ gb }: { gb: GradebookResponse }) {
  const [filter, setFilter] = useState("");
  const [showQuestions, setShowQuestions] = useState(false);
  const [history, setHistory] = useState<GradebookRow | null>(null);
  const rows = useMemo(
    () => gb.rows.filter((r) => !filter || `${r.student_id} ${r.student_name ?? ""}`.toLowerCase().includes(filter.toLowerCase())),
    [gb.rows, filter],
  );
  const frozen = gb.status === "locked" || gb.status === "published";

  if (!gb.rows.length) return <div className="p-4"><EmptyState title="No students or submissions yet" /></div>;
  return (
    <>
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2">
        <Input aria-label="Filter students" placeholder="Filter students…" className="w-56" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <label className="flex items-center gap-2 text-sm text-fg-muted">
          <input type="checkbox" checked={showQuestions} onChange={(e) => setShowQuestions(e.target.checked)} />
          Per-question marks
        </label>
        <span className="tabular ml-auto text-xs text-fg-subtle">{rows.length} of {gb.rows.length} rows</span>
      </div>
      <Table>
        <THead>
          <tr>
            <TH>Student ID</TH>
            <TH>Name</TH>
            <TH align="right">AI score</TH>
            <TH align="right">TA score</TH>
            <TH align="right">Professor</TH>
            <TH align="right">Final</TH>
            {showQuestions && gb.questions.map((q) => <TH key={q} align="right">{q}</TH>)}
            <TH>Status</TH>
            <TH>Integrity</TH>
            <TH>Reviewed by</TH>
            <TH />
          </tr>
        </THead>
        <tbody>
          {rows.map((r) => (
            <TR key={r.submission_id ?? r.student_id}>
              <TD className="font-mono">{r.student_id}</TD>
              <TD className="text-fg-muted">{r.student_name || "—"}</TD>
              <TD align="right">{fmtMarks(r.ai_score)}</TD>
              <TD align="right">{fmtMarks(r.ta_score)}</TD>
              <TD align="right">{fmtMarks(r.professor_score)}</TD>
              <TD align="right" className="font-semibold">
                {r.final_score !== null ? (
                  <>
                    {fmtMarks(r.final_score)}
                    <span className="ml-1 text-xs font-normal text-fg-subtle">{fmtPct(r.percentage)}</span>
                  </>
                ) : (
                  "—"
                )}
                {r.overridden && <span className="ml-1 text-violet-600 dark:text-violet-300" title="Differs from the AI score">•</span>}
              </TD>
              {showQuestions && gb.questions.map((q) => <TD key={q} align="right">{fmtMarks(r.question_scores[q])}</TD>)}
              <TD>
                <Badge tone={r.review_status ? REVIEW_STATUS[r.review_status].tone : "neutral"}>{r.status_label}</Badge>
              </TD>
              <TD>{r.integrity_flags > 0 ? <Badge tone="warning">{r.integrity_flags} flag{r.integrity_flags > 1 ? "s" : ""}</Badge> : <span className="text-fg-subtle">—</span>}</TD>
              <TD className="text-xs text-fg-muted">
                {r.reviewed_by ?? "—"}
                {r.approved_by && <div className="text-fg-subtle">✓ {r.approved_by}</div>}
              </TD>
              <TD align="right">
                {r.submission_id && (
                  <div className="flex justify-end gap-1">
                    <ButtonLink href={`/professor/reviews/${r.submission_id}`} size="sm" variant="ghost">
                      View
                    </ButtonLink>
                    {!frozen && r.review_status && r.review_status !== "not_evaluated" && (
                      <ButtonLink href={`/professor/reviews/${r.submission_id}?action=override`} size="sm" variant="ghost">
                        Override
                      </ButtonLink>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setHistory(r)}>
                      History
                    </Button>
                  </div>
                )}
              </TD>
            </TR>
          ))}
        </tbody>
      </Table>
      {frozen && (
        <p className="border-t border-line px-4 py-2 text-xs text-fg-subtle">
          Grades are {gb.status}. <Link href={`/professor/exams/${gb.exam_id}`} className="text-accent hover:underline">Reopen the exam</Link> to change them.
        </p>
      )}
      {history && <HistoryModal row={history} onClose={() => setHistory(null)} />}
    </>
  );
}
