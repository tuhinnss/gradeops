"use client";

const INPUT = "mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-sm text-white outline-none ring-sky-500/40 focus:ring-2";
const LABEL = "mt-4 block text-xs font-medium uppercase tracking-wide text-zinc-500";
const PANEL = "rounded-2xl border border-white/10 bg-zinc-950/60 p-6 shadow-xl shadow-black/40";

export function RubricUploadCard({
  rubricName, onRubricName, rubricId, questionCount, rubricFilename, busy, onFile,
}: {
  rubricName: string;
  onRubricName: (v: string) => void;
  rubricId: string | null;
  questionCount: number | null;
  rubricFilename: string | null;
  busy: boolean;
  onFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className={PANEL}>
      <h2 className="text-lg font-semibold text-white">1. Marking scheme</h2>
      <p className="mt-1 text-sm text-zinc-500">JSON (recommended) or PDF. Parsed questions drive grading.</p>
      <label className={LABEL}>Rubric title</label>
      <input type="text" value={rubricName} onChange={(e) => onRubricName(e.target.value)} className={INPUT} placeholder="e.g. Physics Midterm" />
      <label className={LABEL}>File (.json or .pdf)</label>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500">
          <input type="file" accept=".json,.pdf,application/json,application/pdf" className="hidden" disabled={busy} onChange={onFile} />
          {busy ? "Uploading…" : "Choose rubric file"}
        </label>
        {rubricId && (
          <span className="text-xs text-zinc-400">
            ID <span className="font-mono text-zinc-200">{rubricId}</span>
            {questionCount != null ? ` · ${questionCount} questions` : ""}
          </span>
        )}
      </div>
      {rubricFilename && (
        <p className="mt-3 text-xs text-zinc-500">
          Last file: <span className="text-zinc-300">{rubricFilename}</span>
        </p>
      )}
    </div>
  );
}

export function AnswerSheetUploadCard({
  studentId, onStudentId, busy, hasRubric, onFile,
}: {
  studentId: string;
  onStudentId: (v: string) => void;
  busy: boolean;
  hasRubric: boolean;
  onFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className={PANEL}>
      <h2 className="text-lg font-semibold text-white">2. Answer sheets</h2>
      <p className="mt-1 text-sm text-zinc-500">PDF only. Each upload needs a student identifier.</p>
      <label className={LABEL}>Student ID</label>
      <input type="text" value={studentId} onChange={(e) => onStudentId(e.target.value)} className={INPUT} placeholder="e.g. STU-2024-001" />
      <label className={LABEL}>Answer PDF</label>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/10">
          <input type="file" accept=".pdf,application/pdf" className="hidden" disabled={busy} onChange={onFile} />
          {busy ? "Uploading…" : "Choose PDF"}
        </label>
        {!hasRubric && <span className="text-xs text-amber-400/90">Upload a rubric first so evaluation can run.</span>}
      </div>
    </div>
  );
}
