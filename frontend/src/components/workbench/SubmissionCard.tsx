"use client";

import { useState } from "react";
import { ReviewPanel } from "@/components/ReviewPanel";
import { annotatedPdfHref } from "@/lib/api";
import { QuestionTable } from "./QuestionTable";
import type { WorkbenchSubmission } from "./useWorkbenchSession";

export function SubmissionCard({ submission: s, rubricId, onEvaluate }: { submission: WorkbenchSubmission; rubricId: string | null; onEvaluate: () => void }) {
  const [open, setOpen] = useState(false);
  const ev = s.evaluation;
  const pdfHref = annotatedPdfHref(ev?.annotated_pdf_url ?? null, s.id);

  return (
    <div>
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-white">{s.studentId}</span>
            <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">{s.filename}</span>
          </div>
          <p className="mt-1 font-mono text-[11px] text-zinc-500">{s.id}</p>
          {s.error && <p className="mt-2 text-xs text-rose-400">{s.error}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {ev && (
            <span className="rounded-lg border border-emerald-500/30 bg-emerald-950/40 px-3 py-1.5 text-sm font-medium text-emerald-200">
              {ev.total} / {ev.max_total} marks
            </span>
          )}
          <a
            href={pdfHref}
            target="_blank"
            rel="noreferrer"
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium ${ev ? "border-sky-500/40 bg-sky-950/40 text-sky-200 hover:bg-sky-950/60" : "pointer-events-none border-white/5 text-zinc-600"}`}
          >
            Annotated PDF
          </a>
          <button
            type="button"
            disabled={s.loading || !rubricId}
            onClick={onEvaluate}
            className="rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {s.loading ? "Evaluating…" : ev ? "Re-evaluate" : "Evaluate"}
          </button>
          {ev && (
            <button type="button" onClick={() => setOpen((o) => !o)} className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-zinc-300 hover:bg-white/5">
              {open ? "Hide details" : "Question breakdown"}
            </button>
          )}
        </div>
      </div>
      {open && ev && (
        <div className="border-t border-white/10 bg-black/30 p-4">
          <QuestionTable results={ev.results} />
          <ReviewPanel submissionId={s.id} results={ev.results} onUpdated={() => {}} />
          {ev.plagiarism_flags?.length > 0 && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-950/30 p-3 text-xs text-amber-100">
              <div className="font-semibold text-amber-200">Similarity flags (review required)</div>
              <ul className="mt-2 list-inside list-disc space-y-1">
                {ev.plagiarism_flags.map((f, i) => (
                  <li key={i}>{f.note}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
