/** Validation for mark overrides (mirrors the backend's rules). */
export type OverrideDraft = { question: string; maxMarks: number; current: number; value: string; comment: string };

export function parseMarks(value: string): number | null {
  if (value.trim() === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function validateOverride(d: OverrideDraft): string | null {
  if (d.value.trim() === "") return null; // unchanged
  const n = parseMarks(d.value);
  if (n === null) return "Enter a number";
  if (n < 0) return "Marks cannot be negative";
  if (n > d.maxMarks) return `Maximum is ${d.maxMarks}`;
  return null;
}

export function changedOverrides(drafts: OverrideDraft[]) {
  return drafts
    .filter((d) => d.value.trim() !== "" && validateOverride(d) === null)
    .map((d) => ({ ...d, marks: Math.round((parseMarks(d.value) as number) * 100) / 100 }))
    .filter((d) => Math.abs(d.marks - d.current) > 1e-9 || d.comment.trim() !== "")
    .map((d) => ({ question: d.question, marks_awarded: d.marks, justification: d.comment.trim() || undefined }));
}
