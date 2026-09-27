"use client";

import { useRef, useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Input, Label, Modal, TD, TH, THead, TR, Table } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { fmtMarks } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ExamDetailResponse } from "@/lib/types";

/** Current rubric for an exam, with upload/replace (JSON or PDF marking scheme). */
export function RubricPanel({ exam, editable, onChanged }: { exam: ExamDetailResponse; editable: boolean; onChanged: (e: ExamDetailResponse) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState(false);
  const rubric = exam.rubric;
  const mismatch = rubric && exam.total_marks && Math.abs(rubric.total_marks - exam.total_marks) > 1e-6;

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      onChanged(await exams.uploadRubric(exam.id, file, name.trim() || undefined));
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rubric upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <Card>
      <CardHeader
        title="Rubric"
        description="Marking scheme the AI grades against. JSON is most reliable; typed solution PDFs are parsed too."
        actions={rubric && <Button size="sm" variant="ghost" onClick={() => setViewing(true)}>View criteria</Button>}
      />
      <div className="space-y-3 p-4">
        {error && <Alert tone="error">{error}</Alert>}
        {rubric ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-fg">{rubric.name}</span>
            <Badge>{rubric.source_type.toUpperCase()}</Badge>
            <span className="tabular text-fg-muted">
              {rubric.question_count} questions · {fmtMarks(rubric.total_marks)} marks
            </span>
          </div>
        ) : (
          <EmptyState title="No rubric yet" description="Upload the marking scheme before running AI evaluation." />
        )}
        {mismatch && (
          <Alert tone="warning">
            Rubric totals {fmtMarks(rubric!.total_marks)} marks but the exam is set to {fmtMarks(exam.total_marks)}. Check the rubric parse.
          </Alert>
        )}
        {editable && (
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[12rem] flex-1">
              <Label htmlFor="rubric-name" hint="(optional)">Rubric name</Label>
              <Input id="rubric-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={`${exam.name} rubric`} />
            </div>
            <input ref={fileRef} type="file" accept=".json,.pdf,application/json,application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} />
            <Button variant={rubric ? "secondary" : "primary"} loading={busy} onClick={() => fileRef.current?.click()}>
              {rubric ? "Replace rubric" : "Upload rubric"}
            </Button>
          </div>
        )}
        {rubric && editable && exam.counts.processed > 0 && (
          <p className="text-xs text-fg-subtle">Replacing the rubric does not change existing AI grades; re-run evaluation afterwards.</p>
        )}
      </div>
      {viewing && <RubricCriteriaModal examId={exam.id} onClose={() => setViewing(false)} />}
    </Card>
  );
}

function RubricCriteriaModal({ examId, onClose }: { examId: string; onClose: () => void }) {
  const detail = useApi(() => exams.rubric(examId), [examId]);
  return (
    <Modal open onClose={onClose} size="lg" title={detail.data?.name ?? "Rubric"} description={detail.data ? `${detail.data.question_count} questions · ${fmtMarks(detail.data.total_marks)} marks` : undefined}>
      {detail.error && <Alert tone="error">{detail.error}</Alert>}
      {detail.data && (
        <Table>
          <THead>
            <tr>
              <TH>Question</TH>
              <TH align="right">Marks</TH>
              <TH>Key points</TH>
            </tr>
          </THead>
          <tbody>
            {detail.data.structured_data.items.map((i) => (
              <TR key={i.question_number}>
                <TD className="font-medium">{i.question_number}</TD>
                <TD align="right">{fmtMarks(i.max_marks)}</TD>
                <TD>
                  <ul className="list-inside list-disc text-xs text-fg-muted">
                    {i.key_points.map((k) => (
                      <li key={k}>{k}</li>
                    ))}
                    {i.partial_credit_rules.map((r) => (
                      <li key={r.condition}>Partial: {r.condition} ({fmtMarks(r.marks)})</li>
                    ))}
                    {i.negative_conditions.map((n) => (
                      <li key={n}>Penalty: {n}</li>
                    ))}
                    {!i.key_points.length && <li className="text-amber-700 dark:text-amber-300">No key points — manual grading required</li>}
                  </ul>
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
    </Modal>
  );
}
