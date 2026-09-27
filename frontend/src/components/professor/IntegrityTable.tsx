"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Badge, Button, EmptyState, Label, Modal, Textarea } from "@/components/ui";
import { professor } from "@/lib/endpoints";
import { fmtDateTime, fmtMarks } from "@/lib/format";
import type { IntegrityFlagResponse, IntegrityFlagStatus } from "@/lib/types";

const STATUS: Record<IntegrityFlagStatus, { label: string; tone: "warning" | "neutral" | "danger" }> = {
  open: { label: "Review required", tone: "warning" },
  dismissed: { label: "No concern", tone: "neutral" },
  confirmed: { label: "Concern confirmed", tone: "danger" },
};

/**
 * Similarity flags. Wording is deliberately neutral: a flag is a potential match
 * for the professor to assess, never a finding of plagiarism.
 */
export function IntegrityTable({ flags, onChanged }: { flags: IntegrityFlagResponse[]; onChanged: () => void }) {
  const [deciding, setDeciding] = useState<{ flag: IntegrityFlagResponse; status: IntegrityFlagStatus } | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide() {
    if (!deciding) return;
    setBusy(true);
    setError(null);
    try {
      await professor.resolveFlag(deciding.flag.id, deciding.status, notes.trim());
      setDeciding(null);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save decision");
    } finally {
      setBusy(false);
    }
  }

  if (!flags.length) return <div className="p-4"><EmptyState title="No similarity flags" description="Flags appear after AI processing when two answers to the same question are unusually similar." /></div>;
  return (
    <>
      <ul className="divide-y divide-line">
        {flags.map((f) => (
          <li key={f.id} className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={STATUS[f.status].tone}>{STATUS[f.status].label}</Badge>
                  <span className="text-sm font-medium text-fg">Similarity flag · {f.question}</span>
                  <span className="tabular text-sm text-fg-muted">{Math.round(f.similarity * 100)}% similar</span>
                </div>
                <p className="mt-0.5 text-xs text-fg-subtle">
                  {f.course_code} · {f.exam_name}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {f.status === "open" ? (
                  <>
                    <Button size="sm" onClick={() => { setDeciding({ flag: f, status: "dismissed" }); setNotes(""); }}>
                      No concern
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => { setDeciding({ flag: f, status: "confirmed" }); setNotes(""); }}>
                      Confirm concern
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => { setDeciding({ flag: f, status: "open" }); setNotes(""); }}>
                    Reopen
                  </Button>
                )}
              </div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {[f.a, f.b].map((side) => (
                <div key={side.submission_id} className="rounded-md border border-line bg-surface-raised p-3">
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <Link href={`/professor/reviews/${side.submission_id}`} className="font-mono text-accent hover:underline">
                      {side.student_id}
                    </Link>
                    <span className="text-xs text-fg-subtle">
                      {side.student_name ?? ""} · score {fmtMarks(side.score)}
                    </span>
                  </div>
                  <p className="line-clamp-4 whitespace-pre-wrap font-mono text-xs text-fg-muted">{side.excerpt || "(no OCR excerpt stored)"}</p>
                </div>
              ))}
            </div>
            {f.status !== "open" && (
              <p className="mt-2 text-xs text-fg-muted">
                Decision by {f.resolved_by?.full_name ?? "—"} · {fmtDateTime(f.resolved_at)}
                {f.resolution_notes && <> — “{f.resolution_notes}”</>}
              </p>
            )}
          </li>
        ))}
      </ul>
      <Modal
        open={!!deciding}
        onClose={() => setDeciding(null)}
        title={deciding?.status === "confirmed" ? "Confirm integrity concern" : deciding?.status === "dismissed" ? "Mark as no concern" : "Reopen flag"}
        description="Your determination and note are recorded. Grades are not changed automatically."
        footer={
          <>
            <Button onClick={() => setDeciding(null)} disabled={busy}>Cancel</Button>
            <Button variant={deciding?.status === "confirmed" ? "danger" : "primary"} loading={busy} disabled={deciding?.status !== "open" && !notes.trim()} onClick={() => void decide()}>
              Save decision
            </Button>
          </>
        }
      >
        {error && <Alert tone="error" className="mb-3">{error}</Alert>}
        <Label htmlFor="flag-notes" hint={deciding?.status === "open" ? "(optional)" : "(required)"}>Notes</Label>
        <Textarea id="flag-notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Modal>
    </>
  );
}
