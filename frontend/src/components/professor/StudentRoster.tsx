"use client";

import { useRef, useState } from "react";
import { Alert, Button, Card, CardHeader, ConfirmDialog, EmptyState, ErrorState, Input, Label, SkeletonRows, TD, TH, THead, TR, Table } from "@/components/ui";
import { courses } from "@/lib/endpoints";
import { fmtDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { StudentImportResponse, StudentResponse } from "@/lib/types";

export function StudentRoster({ courseId, archived, onChanged }: { courseId: string; archived: boolean; onChanged: () => void }) {
  const roster = useApi(() => courses.students(courseId), [courseId]);
  const [form, setForm] = useState({ student_id: "", name: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error" | "warning"; text: string } | null>(null);
  const [dropping, setDropping] = useState<StudentResponse | null>(null);
  const [filter, setFilter] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function report(res: StudentImportResponse) {
    const parts = [`${res.enrolled + res.reactivated} enrolled`, `${res.created} new student records`];
    if (res.already_enrolled) parts.push(`${res.already_enrolled} already enrolled`);
    setMessage({ tone: res.errors.length ? "warning" : "success", text: parts.join(" · ") + (res.errors.length ? ` · ${res.errors.length} rows skipped: ${res.errors.slice(0, 3).join("; ")}` : "") });
    void roster.reload();
    onChanged();
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      report(await courses.addStudents(courseId, [{ student_id: form.student_id.trim(), name: form.name.trim(), email: form.email.trim() || null }]));
      setForm({ student_id: "", name: "", email: "" });
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not add student" });
    } finally {
      setBusy(false);
    }
  }

  async function importCsv(file: File) {
    setBusy(true);
    setMessage(null);
    try {
      report(await courses.importCsv(courseId, file));
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Import failed" });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function drop(s: StudentResponse) {
    setBusy(true);
    try {
      await courses.dropStudent(courseId, s.id);
      setDropping(null);
      await roster.reload();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const rows = (roster.data ?? []).filter((s) => !filter || `${s.student_id} ${s.name} ${s.email ?? ""}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="space-y-4">
      {!archived && (
        <Card>
          <CardHeader title="Add students" description="Add one student, or import a CSV with columns student_id, name, email." />
          <form onSubmit={add} className="grid items-end gap-3 p-4 sm:grid-cols-[1fr_1.5fr_1.5fr_auto_auto]">
            <div>
              <Label htmlFor="s-id">Student ID</Label>
              <Input id="s-id" required pattern="[A-Za-z0-9_.\-]+" value={form.student_id} onChange={(e) => setForm({ ...form, student_id: e.target.value })} />
            </div>
            <div>
              <Label htmlFor="s-name">Name</Label>
              <Input id="s-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label htmlFor="s-email" hint="(optional)">Email</Label>
              <Input id="s-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <Button type="submit" variant="primary" loading={busy} disabled={!form.student_id.trim()}>
              Add
            </Button>
            <div>
              <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && void importCsv(e.target.files[0])} />
              <Button onClick={() => fileRef.current?.click()} disabled={busy}>
                Import CSV
              </Button>
            </div>
          </form>
          {message && (
            <div className="px-4 pb-4">
              <Alert tone={message.tone} onDismiss={() => setMessage(null)}>
                {message.text}
              </Alert>
            </div>
          )}
        </Card>
      )}
      <Card>
        <CardHeader
          title="Roster"
          description={roster.data ? `${roster.data.length} enrolled student${roster.data.length === 1 ? "" : "s"}` : undefined}
          actions={<Input aria-label="Filter students" placeholder="Filter…" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-48" />}
        />
        {roster.error && <div className="p-4"><ErrorState message={roster.error} onRetry={roster.reload} /></div>}
        {!roster.data && !roster.error && <SkeletonRows rows={5} className="p-4" />}
        {roster.data && roster.data.length === 0 && <div className="p-4"><EmptyState title="No students enrolled" description="Add students individually or import a CSV." /></div>}
        {rows.length > 0 && (
          <Table>
            <THead>
              <tr>
                <TH>Student ID</TH>
                <TH>Name</TH>
                <TH>Email</TH>
                <TH>Enrolled</TH>
                <TH />
              </tr>
            </THead>
            <tbody>
              {rows.map((s) => (
                <TR key={s.id}>
                  <TD className="font-mono">{s.student_id}</TD>
                  <TD>{s.name || "—"}</TD>
                  <TD className="text-fg-muted">{s.email ?? "—"}</TD>
                  <TD className="text-fg-muted">{fmtDate(s.enrolled_at)}</TD>
                  <TD align="right">
                    {!archived && (
                      <Button size="sm" variant="ghost" onClick={() => setDropping(s)}>
                        Remove
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <ConfirmDialog
        open={!!dropping}
        title={`Remove ${dropping?.student_id} from the course?`}
        description="The enrolment is marked as dropped. Existing submissions and grades are kept."
        confirmLabel="Remove student"
        tone="danger"
        busy={busy}
        onClose={() => setDropping(null)}
        onConfirm={() => dropping && void drop(dropping)}
      />
    </div>
  );
}
