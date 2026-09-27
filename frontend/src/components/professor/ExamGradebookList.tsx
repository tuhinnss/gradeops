"use client";

import { ExamStatusBadge } from "@/components/grading/Badges";
import { Button, ButtonLink, EmptyState, TD, TH, THead, TR, Table } from "@/components/ui";
import { exams as examsApi } from "@/lib/endpoints";
import { downloadBlob, fmtMarks } from "@/lib/format";
import type { ExamResponse } from "@/lib/types";

/** Exams with links to their gradebooks and CSV export. */
export function ExamGradebookList({ exams }: { exams: ExamResponse[] }) {
  if (!exams.length) return <div className="p-4"><EmptyState title="No exams yet" /></div>;
  async function download(e: ExamResponse) {
    const final = e.status === "approved" || e.status === "locked" || e.status === "published";
    const { blob, filename } = await examsApi.downloadGradebook(e.id, final);
    downloadBlob(blob, filename);
  }
  return (
    <Table>
      <THead>
        <tr>
          <TH>Exam</TH>
          <TH>Status</TH>
          <TH align="right">Graded</TH>
          <TH align="right">Average</TH>
          <TH />
        </tr>
      </THead>
      <tbody>
        {exams.map((e) => (
          <TR key={e.id}>
            <TD>
              <div className="font-medium">{e.name}</div>
              <div className="text-xs text-fg-subtle">{e.course_code}</div>
            </TD>
            <TD>
              <ExamStatusBadge status={e.status} />
            </TD>
            <TD align="right">
              {e.counts.processed} / {e.counts.submissions}
            </TD>
            <TD align="right">{e.average_score !== null ? `${fmtMarks(e.average_score)} / ${fmtMarks(e.max_score)}` : "—"}</TD>
            <TD align="right">
              <div className="flex justify-end gap-2">
                <ButtonLink href={`/professor/exams/${e.id}/gradebook`} size="sm" variant="primary">
                  Open gradebook
                </ButtonLink>
                <Button size="sm" onClick={() => void download(e)} disabled={!e.counts.submissions}>
                  CSV
                </Button>
              </div>
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
