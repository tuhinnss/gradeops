import { cx } from "@/components/ui";
import type { ExamResponse } from "@/lib/types";

const STEPS = [
  { key: "upload", label: "Upload" },
  { key: "ocr", label: "OCR" },
  { key: "segmentation", label: "Segmentation" },
  { key: "evaluation", label: "Evaluation" },
  { key: "integrity", label: "Integrity check" },
  { key: "ta_review", label: "TA review" },
  { key: "professor", label: "Professor approval" },
  { key: "published", label: "Published" },
] as const;

/** Index of the current step derived from real exam state and counts. */
export function pipelineStep(exam: Pick<ExamResponse, "status" | "stage" | "counts">): number {
  const c = exam.counts;
  switch (exam.stage) {
    case "published":
      return 8;
    case "approved":
    case "locked":
    case "professor_approval":
      return 6;
    case "ta_review":
      return 5;
    case "ai_processing":
      return c.processed > 0 ? 3 : 1;
    default:
      return c.submissions > 0 ? 1 : 0;
  }
}

export function ExamPipeline({ exam }: { exam: Pick<ExamResponse, "status" | "stage" | "counts"> }) {
  const current = pipelineStep(exam);
  return (
    <ol className="flex flex-wrap items-center gap-y-2 text-xs" aria-label="Grading pipeline">
      {STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s.key} className="flex items-center" aria-current={active ? "step" : undefined}>
            <span
              className={cx(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium",
                done && "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
                active && "bg-accent/15 text-accent-strong ring-1 ring-accent/40",
                !done && !active && "text-fg-subtle",
              )}
            >
              <span className={cx("grid h-4 w-4 place-items-center rounded-full text-[10px]", done ? "bg-emerald-500 text-white" : active ? "bg-accent text-white" : "bg-surface-sunken")}>
                {done ? "✓" : i + 1}
              </span>
              {s.label}
            </span>
            {i < STEPS.length - 1 && <span className={cx("mx-1 h-px w-3", done ? "bg-emerald-500/60" : "bg-line")} aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
