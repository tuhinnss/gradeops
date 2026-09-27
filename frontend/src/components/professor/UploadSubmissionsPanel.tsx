"use client";

import { useRef, useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, Input, TD, TH, THead, TR, Table } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import type { MappingItemResult, SubmissionUploadResponse } from "@/lib/types";

const STATUS: Record<MappingItemResult["status"], { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  ok: { label: "Ready", tone: "success" },
  not_enrolled: { label: "Not on roster", tone: "warning" },
  duplicate_in_upload: { label: "Duplicate", tone: "danger" },
  already_submitted: { label: "Already submitted", tone: "danger" },
  invalid: { label: "Invalid", tone: "danger" },
};

/**
 * Upload answer-sheet PDFs with student mapping validated against the course
 * roster before anything is stored.
 */
export function UploadSubmissionsPanel({ examId, disabled, onUploaded }: { examId: string; disabled?: boolean; onUploaded: (r: SubmissionUploadResponse) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [ids, setIds] = useState<string[]>([]);
  const [results, setResults] = useState<MappingItemResult[] | null>(null);
  const [autoEnroll, setAutoEnroll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error" | "warning"; text: string } | null>(null);

  async function validate(list: File[], studentIds: string[], enroll = autoEnroll) {
    setBusy(true);
    setMessage(null);
    try {
      const res = await exams.validateMapping(examId, list.map((f, i) => ({ filename: f.name, student_id: studentIds[i] || null })), enroll);
      setResults(res.items);
      setIds(res.items.map((r, i) => studentIds[i] || r.student_id || ""));
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Validation failed" });
    } finally {
      setBusy(false);
    }
  }

  function choose(list: FileList | null) {
    const pdfs = Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!pdfs.length) return setMessage({ tone: "error", text: "Choose one or more PDF files." });
    setFiles(pdfs);
    setIds(pdfs.map(() => ""));
    void validate(pdfs, pdfs.map(() => ""));
  }

  async function upload() {
    if (!results) return;
    const ready = results.map((r, i) => ({ r, i })).filter(({ r }) => r.status === "ok");
    setBusy(true);
    setMessage(null);
    try {
      const res = await exams.uploadSubmissions(
        examId,
        ready.map(({ i }) => files[i]),
        ready.map(({ i }) => ids[i] || null),
        autoEnroll,
      );
      const failed = res.failed.length ? ` · ${res.failed.length} rejected` : "";
      setMessage({ tone: res.failed.length ? "warning" : "success", text: `${res.uploaded.length} answer sheet(s) uploaded${failed}.${res.warnings.length ? ` ${res.warnings.join(" ")}` : ""}` });
      setFiles([]);
      setResults(null);
      onUploaded(res);
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const ok = results?.filter((r) => r.status === "ok").length ?? 0;
  return (
    <Card>
      <CardHeader
        title="Answer sheets"
        description="PDF scans, one per student. Student IDs are read from the file name (e.g. 240122065_midsem.pdf) and checked against the roster."
        actions={
          <>
            <input ref={fileRef} type="file" multiple accept=".pdf,application/pdf" className="hidden" onChange={(e) => choose(e.target.files)} />
            <Button size="sm" variant="primary" disabled={disabled || busy} onClick={() => fileRef.current?.click()}>
              Choose PDFs
            </Button>
          </>
        }
      />
      <div className="space-y-3 p-4">
        {disabled && <p className="text-sm text-fg-subtle">Uploads are closed while the exam is processing or finalised.</p>}
        {message && <Alert tone={message.tone} onDismiss={() => setMessage(null)}>{message.text}</Alert>}
        {results && (
          <>
            <label className="flex items-center gap-2 text-sm text-fg-muted">
              <input
                type="checkbox"
                checked={autoEnroll}
                onChange={(e) => {
                  setAutoEnroll(e.target.checked);
                  void validate(files, ids, e.target.checked);
                }}
              />
              Add students who are not on the roster yet
            </label>
            <Table className="rounded-md border border-line">
              <THead>
                <tr>
                  <TH>File</TH>
                  <TH>Student ID</TH>
                  <TH>Student</TH>
                  <TH>Check</TH>
                </tr>
              </THead>
              <tbody>
                {results.map((r, i) => (
                  <TR key={`${r.filename}-${i}`}>
                    <TD className="max-w-[16rem] truncate font-mono text-xs">{r.filename}</TD>
                    <TD>
                      <Input aria-label={`Student ID for ${r.filename}`} className="h-8 w-40 font-mono" value={ids[i] ?? ""} onChange={(e) => setIds((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))} />
                    </TD>
                    <TD className="text-fg-muted">{r.student_name || "—"}</TD>
                    <TD>
                      <Badge tone={STATUS[r.status].tone} title={r.message ?? undefined}>{STATUS[r.status].label}</Badge>
                      {r.message && r.status !== "ok" && <div className="mt-0.5 text-[11px] text-fg-subtle">{r.message}</div>}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => void validate(files, ids)} loading={busy}>
                Re-check mapping
              </Button>
              <Button variant="primary" onClick={() => void upload()} disabled={!ok || busy}>
                Upload {ok} of {results.length}
              </Button>
              <Button variant="ghost" onClick={() => { setFiles([]); setResults(null); }}>
                Cancel
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
