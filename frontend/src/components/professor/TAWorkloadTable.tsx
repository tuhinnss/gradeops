"use client";

import { useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, ConfirmDialog, EmptyState, ErrorState, Input, Label, Modal, ProgressBar, Select, SkeletonRows, TD, TH, THead, TR, Table } from "@/components/ui";
import { courses, exams as examsApi } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import type { ExamResponse, TAWorkload } from "@/lib/types";

/** TA staffing and workload for one course: add/remove TAs, assign them to exams. */
export function TAWorkloadTable({ courseId, archived, onChanged }: { courseId: string; archived: boolean; onChanged?: () => void }) {
  const tas = useApi(() => courses.tas(courseId), [courseId]);
  const exams = useApi(() => examsApi.list({ course_id: courseId }), [courseId]);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<TAWorkload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await Promise.all([tas.reload(), exams.reload()]);
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const activeTas = (tas.data ?? []).filter((t) => t.active);
  const former = (tas.data ?? []).filter((t) => !t.active);

  return (
    <Card>
      <CardHeader
        title="Teaching assistants"
        description="Workload counts come from exam assignments and the review audit log."
        actions={!archived && <Button variant="primary" size="sm" onClick={() => setAdding(true)}>Add TA</Button>}
      />
      {error && <div className="px-4 pt-3"><Alert tone="error" onDismiss={() => setError(null)}>{error}</Alert></div>}
      {tas.error && <div className="p-4"><ErrorState message={tas.error} onRetry={tas.reload} /></div>}
      {!tas.data && !tas.error && <SkeletonRows rows={3} className="p-4" />}
      {tas.data && activeTas.length === 0 && (
        <div className="p-4">
          <EmptyState title="No TAs on this course" description="Add a TA by email, then assign them to exams." />
        </div>
      )}
      {activeTas.length > 0 && (
        <Table>
          <THead>
            <tr>
              <TH>TA</TH>
              <TH>Assigned exams</TH>
              <TH align="right">Assigned</TH>
              <TH align="right">Reviewed</TH>
              <TH align="right">Pending</TH>
              <TH align="right">Escalated</TH>
              <TH align="right">Overrides</TH>
              <TH>Progress</TH>
              <TH />
            </tr>
          </THead>
          <tbody>
            {activeTas.map((t) => (
              <TaRow key={t.user.id} ta={t} exams={exams.data ?? []} busy={busy} archived={archived} onAssign={(examId) => run(() => examsApi.assignTa(examId, t.user.id))} onUnassign={(examId) => run(() => examsApi.unassignTa(examId, t.user.id))} onRemove={() => setRemoving(t)} />
            ))}
          </tbody>
        </Table>
      )}
      {former.length > 0 && (
        <p className="border-t border-line px-4 py-2 text-xs text-fg-subtle">Former TAs (history kept): {former.map((t) => t.user.full_name || t.user.email).join(", ")}</p>
      )}
      <AddTADialog
        open={adding}
        onClose={() => setAdding(false)}
        onAdd={async (body) => {
          await courses.addTa(courseId, body);
          setAdding(false);
          await tas.reload();
          onChanged?.();
        }}
      />
      <ConfirmDialog
        open={!!removing}
        title={`Remove ${removing?.user.full_name || removing?.user.email}?`}
        description="They lose access to this course and its exams immediately. Their submission assignments return to the shared queue; their review history is kept."
        confirmLabel="Remove TA"
        tone="danger"
        busy={busy}
        onClose={() => setRemoving(null)}
        onConfirm={() => removing && void run(() => courses.removeTa(courseId, removing.user.id)).then(() => setRemoving(null))}
      />
    </Card>
  );
}

function TaRow({ ta, exams, busy, archived, onAssign, onUnassign, onRemove }: { ta: TAWorkload; exams: ExamResponse[]; busy: boolean; archived: boolean; onAssign: (examId: string) => void; onUnassign: (examId: string) => void; onRemove: () => void }) {
  const assignedIds = new Set(ta.assigned_exams.map((e) => e.id));
  const available = exams.filter((e) => !assignedIds.has(e.id));
  const done = ta.assigned_submissions - ta.pending;
  return (
    <TR>
      <TD>
        <div className="font-medium">{ta.user.full_name || ta.user.email}</div>
        <div className="text-xs text-fg-subtle">{ta.user.email}</div>
      </TD>
      <TD>
        <div className="flex flex-wrap items-center gap-1">
          {ta.assigned_exams.map((e) => (
            <Badge key={e.id} tone="info">
              {e.name}
              {!archived && (
                <button type="button" className="ml-0.5 opacity-60 hover:opacity-100" onClick={() => onUnassign(e.id)} disabled={busy} aria-label={`Unassign from ${e.name}`}>
                  ×
                </button>
              )}
            </Badge>
          ))}
          {!archived && available.length > 0 && (
            <Select aria-label={`Assign ${ta.user.full_name} to exam`} className="h-7 w-36 text-xs" value="" onChange={(e) => e.target.value && onAssign(e.target.value)} disabled={busy}>
              <option value="">+ Assign exam</option>
              {available.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </Select>
          )}
        </div>
      </TD>
      <TD align="right">{ta.assigned_submissions}</TD>
      <TD align="right">{ta.reviewed}</TD>
      <TD align="right">{ta.pending}</TD>
      <TD align="right">{ta.escalated}</TD>
      <TD align="right">{ta.overrides}</TD>
      <TD className="w-28">
        <ProgressBar value={done} max={Math.max(ta.assigned_submissions, 1)} tone="success" label={`${ta.user.full_name} review progress`} />
      </TD>
      <TD align="right">
        {!archived && (
          <Button size="sm" variant="ghost" onClick={onRemove}>
            Remove
          </Button>
        )}
      </TD>
    </TR>
  );
}

function AddTADialog({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (body: { email: string; full_name?: string | null; password?: string | null }) => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [create, setCreate] = useState(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await onAdd({ email: email.trim(), full_name: create ? name.trim() || null : null, password: create ? password : null });
      setEmail("");
      setName("");
      setPassword("");
      setCreate(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add TA");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add a teaching assistant"
      description="TAs only see exams you assign them to, and cannot change rubrics, rosters or publish grades."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!email.includes("@") || (create && password.length < 8)} onClick={() => void submit()}>
            Add TA
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {error && <Alert tone="error">{error}</Alert>}
        <div>
          <Label htmlFor="ta-email">TA email</Label>
          <Input id="ta-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm text-fg-muted">
          <input type="checkbox" checked={create} onChange={(e) => setCreate(e.target.checked)} />
          Create a new TA account (if they have not registered)
        </label>
        {create && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="ta-name">Full name</Label>
              <Input id="ta-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="ta-pw" hint="(min 8, share securely)">Initial password</Label>
              <Input id="ta-pw" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
