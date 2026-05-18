"use client";

import { useState } from "react";
import {
  getReviewState,
  submitReviewAction,
  type QuestionResult,
  type ReviewState,
} from "@/lib/api";

type Props = {
  submissionId: string;
  results: QuestionResult[];
  onUpdated: (state: ReviewState) => void;
};

export function ReviewPanel({ submissionId, results, onUpdated }: Props) {
  const [status, setStatus] = useState<string>("pending");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, number>>(() =>
    Object.fromEntries(results.map((r) => [r.question, r.marks_awarded]))
  );

  async function load() {
    try {
      const s = await getReviewState(submissionId);
      setStatus(s.review_status);
      setNotes(s.reviewer_notes ?? "");
      onUpdated(s);
    } catch {
      /* optional */
    }
  }

  async function act(action: "approve" | "reject" | "override") {
    setBusy(true);
    try {
      const ov =
        action === "override"
          ? results.map((r) => ({
              question: r.question,
              marks_awarded: overrides[r.question] ?? r.marks_awarded,
            }))
          : [];
      const s = await submitReviewAction(submissionId, action, notes || undefined, ov);
      setStatus(s.review_status);
      onUpdated(s);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-violet-500/30 bg-violet-950/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-violet-300">
          Human review · {status}
        </span>
        <button
          type="button"
          onClick={() => void load()}
          className="text-xs text-zinc-400 hover:text-white"
        >
          Refresh
        </button>
      </div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Reviewer notes…"
        className="mt-2 w-full rounded border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white"
        rows={2}
      />
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {results.map((r) => (
          <label key={r.question} className="flex items-center gap-2 text-xs text-zinc-400">
            <span className="font-mono text-violet-300">{r.question}</span>
            <input
              type="number"
              step="0.5"
              min={0}
              max={r.max_marks}
              value={overrides[r.question] ?? r.marks_awarded}
              onChange={(e) =>
                setOverrides((o) => ({ ...o, [r.question]: Number(e.target.value) }))
              }
              className="w-16 rounded border border-white/10 bg-black/50 px-1 py-0.5 text-white"
            />
            <span>/ {r.max_marks}</span>
          </label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void act("approve")}
          className="rounded bg-emerald-700 px-3 py-1 text-xs text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void act("override")}
          className="rounded bg-violet-700 px-3 py-1 text-xs text-white hover:bg-violet-600 disabled:opacity-50"
        >
          Save overrides
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void act("reject")}
          className="rounded border border-rose-500/40 px-3 py-1 text-xs text-rose-200 hover:bg-rose-950/40 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
