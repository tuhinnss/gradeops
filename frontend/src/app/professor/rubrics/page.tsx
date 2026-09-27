"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Card, EmptyState, ErrorState, Modal, PageHeader, SkeletonRows, TD, TH, THead, TR, Table, Textarea } from "@/components/ui";
import { rubrics } from "@/lib/endpoints";
import { fmtDate, fmtMarks } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { RubricSummary } from "@/lib/types";

function RubricEditor({ rubric, onClose, onSaved }: { rubric: RubricSummary; onClose: () => void; onSaved: () => void }) {
  const detail = useApi(() => rubrics.get(rubric.id), [rubric.id]);
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const value = text ?? (detail.data ? JSON.stringify(detail.data.structured_data, null, 2) : "");

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const parsed = JSON.parse(value);
      await rubrics.update(rubric.id, { structured_data: parsed });
      onSaved();
    } catch (err) {
      setError(err instanceof SyntaxError ? `Invalid JSON: ${err.message}` : err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={`Edit rubric · ${rubric.name}`}
      description="Questions, marks, key points, partial-credit rules and penalties. Editing is blocked once an exam using this rubric is processing or finalised; re-run evaluation afterwards."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!detail.data || text === null} onClick={() => void save()}>
            Save rubric
          </Button>
        </>
      }
    >
      {error && <Alert tone="error" className="mb-3">{error}</Alert>}
      {!detail.data ? <SkeletonRows rows={6} /> : <Textarea aria-label="Rubric JSON" rows={22} className="font-mono text-xs" value={value} onChange={(e) => setText(e.target.value)} spellCheck={false} />}
    </Modal>
  );
}

export default function RubricsPage() {
  const list = useApi(() => rubrics.list(), []);
  const [editing, setEditing] = useState<RubricSummary | null>(null);
  return (
    <>
      <PageHeader title="Rubrics" subtitle="Marking schemes you have uploaded. Upload new ones from an exam's page." />
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      <Card>
        {!list.data && !list.error && <SkeletonRows rows={4} className="p-4" />}
        {list.data && list.data.length === 0 && <div className="p-4"><EmptyState title="No rubrics yet" description="Open an exam and upload its marking scheme (JSON or PDF)." /></div>}
        {list.data && list.data.length > 0 && (
          <Table>
            <THead>
              <tr>
                <TH>Rubric</TH>
                <TH>Source</TH>
                <TH align="right">Questions</TH>
                <TH align="right">Total marks</TH>
                <TH>Used by</TH>
                <TH>Created</TH>
                <TH />
              </tr>
            </THead>
            <tbody>
              {list.data.map((r) => (
                <TR key={r.id}>
                  <TD className="font-medium">{r.name}</TD>
                  <TD className="text-xs text-fg-muted">{r.source_filename}</TD>
                  <TD align="right">{r.question_count}</TD>
                  <TD align="right">{fmtMarks(r.total_marks)}</TD>
                  <TD className="text-sm">
                    {r.used_by_exams.length === 0 ? <span className="text-fg-subtle">—</span> : r.used_by_exams.map((e) => (
                      <Link key={e.id} href={`/professor/exams/${e.id}`} className="mr-2 text-accent hover:underline">
                        {e.name}
                      </Link>
                    ))}
                  </TD>
                  <TD className="text-fg-muted">{fmtDate(r.created_at)}</TD>
                  <TD align="right">
                    <Button size="sm" onClick={() => setEditing(r)}>
                      View / edit
                    </Button>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {editing && (
        <RubricEditor
          rubric={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void list.reload();
          }}
        />
      )}
    </>
  );
}
