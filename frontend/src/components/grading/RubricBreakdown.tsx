import { Badge, cx } from "@/components/ui";
import { fmtMarks } from "@/lib/format";
import type { CriterionScore, ReviewQuestion } from "@/lib/types";

const STATUS: Record<CriterionScore["status"], { label: string; tone: "success" | "warning" | "danger" | "neutral" | "violet" }> = {
  met: { label: "Met", tone: "success" },
  partial: { label: "Partial", tone: "warning" },
  missed: { label: "Not found", tone: "danger" },
  applied: { label: "Applied", tone: "violet" },
  not_applied: { label: "Not applied", tone: "neutral" },
};

/** Rubric criteria with the AI's per-criterion evidence. */
export function RubricBreakdown({ question }: { question: ReviewQuestion }) {
  const byCriterion = new Map(question.criteria.map((c) => [`${c.kind}:${c.criterion}`, c]));
  const keyPoints = question.rubric.key_points;
  const perPoint = keyPoints.length ? question.max_marks / keyPoints.length : 0;
  const extras = question.criteria.filter((c) => c.kind !== "key_point");

  if (!keyPoints.length && !extras.length) {
    return <p className="text-sm text-fg-subtle">No rubric criteria recorded for this question.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <table className="w-full text-sm">
        <thead className="bg-surface-raised text-[11px] uppercase tracking-wide text-fg-subtle">
          <tr>
            <th className="px-3 py-1.5 text-left font-semibold">Criterion</th>
            <th className="px-3 py-1.5 text-left font-semibold">AI</th>
            <th className="px-3 py-1.5 text-right font-semibold">Marks</th>
          </tr>
        </thead>
        <tbody>
          {keyPoints.map((kp) => {
            const c = byCriterion.get(`key_point:${kp}`);
            return (
              <tr key={kp} className="border-t border-line">
                <td className="px-3 py-2 text-fg">
                  {kp}
                  {c && <Evidence c={c} />}
                </td>
                <td className="px-3 py-2">{c ? <Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge> : <span className="text-xs text-fg-subtle">—</span>}</td>
                <td className="tabular whitespace-nowrap px-3 py-2 text-right text-fg">
                  {c ? fmtMarks(c.awarded) : "—"} <span className="text-fg-subtle">/ {fmtMarks(c?.max_marks ?? perPoint)}</span>
                </td>
              </tr>
            );
          })}
          {extras.map((c) => (
            <tr key={`${c.kind}:${c.criterion}`} className={cx("border-t border-line", c.status === "not_applied" && "opacity-70")}>
              <td className="px-3 py-2 text-fg">
                <span className="mr-1 text-[11px] font-semibold uppercase text-fg-subtle">{c.kind === "penalty" ? "Penalty" : "Partial rule"}</span>
                {c.criterion}
                <Evidence c={c} />
              </td>
              <td className="px-3 py-2">
                <Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge>
              </td>
              <td className="tabular whitespace-nowrap px-3 py-2 text-right text-fg">
                {c.kind === "penalty" ? fmtMarks(c.awarded) : `${fmtMarks(c.awarded)} / ${fmtMarks(c.max_marks)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Evidence({ c }: { c: CriterionScore }) {
  return (
    <div className="mt-0.5 text-[11px] text-fg-subtle">
      {c.semantic_similarity !== null && <>semantic {Math.round(c.semantic_similarity * 100)}% · </>}
      keywords {Math.round(c.keyword_overlap * 100)}%
    </div>
  );
}
