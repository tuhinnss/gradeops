"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, Select } from "@/components/ui";
import { courses, exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import type { ExamDetailResponse } from "@/lib/types";

export function ExamTAPanel({ exam, editable, onChanged }: { exam: ExamDetailResponse; editable: boolean; onChanged: () => void }) {
  const staff = useApi(() => courses.tas(exam.course_id), [exam.course_id]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const assigned = new Set(exam.tas.map((t) => t.id));
  const available = (staff.data ?? []).filter((t) => t.active && !assigned.has(t.user.id));

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fn();
      if (ok) setMessage({ tone: "success", text: typeof res === "object" && res && "total" in res ? `${ok}: ${(res as { total: number }).total} submission(s)` : ok });
      onChanged();
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Action failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Assigned TAs" description="Only TAs assigned here can see and review this exam." />
      <div className="space-y-3 p-4">
        {message && <Alert tone={message.tone} onDismiss={() => setMessage(null)}>{message.text}</Alert>}
        <div className="flex flex-wrap gap-1.5">
          {exam.tas.length === 0 && <span className="text-sm text-fg-subtle">No TAs assigned.</span>}
          {exam.tas.map((t) => (
            <Badge key={t.id} tone="info">
              {t.full_name || t.email}
              {editable && (
                <button type="button" className="ml-0.5 opacity-60 hover:opacity-100" onClick={() => void run(() => exams.unassignTa(exam.id, t.id))} disabled={busy} aria-label={`Unassign ${t.full_name}`}>
                  ×
                </button>
              )}
            </Badge>
          ))}
        </div>
        {editable && (
          <div className="flex flex-wrap items-center gap-2">
            {available.length > 0 ? (
              <Select aria-label="Assign a TA" className="w-56" value="" onChange={(e) => e.target.value && void run(() => exams.assignTa(exam.id, e.target.value))} disabled={busy}>
                <option value="">Assign a course TA…</option>
                {available.map((t) => (
                  <option key={t.user.id} value={t.user.id}>
                    {t.user.full_name || t.user.email}
                  </option>
                ))}
              </Select>
            ) : (
              <span className="text-xs text-fg-subtle">
                All course TAs are assigned. <Link href={`/professor/courses/${exam.course_id}/tas`} className="text-accent hover:underline">Add TAs to the course</Link>
              </span>
            )}
            {exam.tas.length > 1 && (
              <Button size="sm" onClick={() => void run(() => exams.distribute(exam.id), "Distributed")} disabled={busy} title="Give each submission awaiting review to one TA, round-robin">
                Split work between TAs
              </Button>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
