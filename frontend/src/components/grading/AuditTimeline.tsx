import { actionLabel, fmtDateTime, fmtMarks } from "@/lib/format";
import type { ReviewAuditItem } from "@/lib/types";
import { ESCALATION_REASONS } from "@/lib/types";

const REASON_LABEL: Record<string, string> = Object.fromEntries(ESCALATION_REASONS.map((r) => [r.value, r.label]));

export function AuditTimeline({ items }: { items: ReviewAuditItem[] }) {
  if (!items.length) return <p className="text-sm text-fg-subtle">No human review actions yet.</p>;
  return (
    <ol className="space-y-3">
      {items.map((a) => (
        <li key={a.id} className="relative border-l border-line pl-4">
          <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-surface bg-accent" aria-hidden />
          <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <span className="font-medium text-fg">{actionLabel(a.action)}</span>
            {a.question && (
              <span className="tabular text-fg-muted">
                {a.question}: {fmtMarks(a.old_marks)} → {fmtMarks(a.new_marks)}
              </span>
            )}
            <span className="text-xs text-fg-subtle">
              {a.reviewer ? `${a.reviewer.full_name || a.reviewer.email}${a.actor_role ? ` (${a.actor_role})` : ""}` : "system"} · {fmtDateTime(a.created_at)}
            </span>
          </div>
          {a.reason && <p className="text-xs text-fg-muted">Reason: {REASON_LABEL[a.reason] ?? a.reason}</p>}
          {a.notes && <p className="text-xs text-fg-muted">“{a.notes}”</p>}
        </li>
      ))}
    </ol>
  );
}
