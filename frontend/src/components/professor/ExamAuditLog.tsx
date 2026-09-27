import { EmptyState } from "@/components/ui";
import { actionLabel, fmtDateTime } from "@/lib/format";
import type { ExamAuditItem } from "@/lib/types";

export function ExamAuditLog({ items }: { items: ExamAuditItem[] }) {
  if (!items.length) return <EmptyState title="No exam events yet" />;
  return (
    <ol className="divide-y divide-line">
      {items.map((a) => (
        <li key={a.id} className="flex items-start justify-between gap-3 py-2 text-sm">
          <div className="min-w-0">
            <span className="font-medium text-fg">{actionLabel(a.action)}</span>
            {a.from_status && a.to_status && a.from_status !== a.to_status && (
              <span className="text-xs text-fg-subtle">
                {" "}
                · {a.from_status.replace(/_/g, " ")} → {a.to_status.replace(/_/g, " ")}
              </span>
            )}
            {a.notes && <p className="text-xs text-fg-muted">“{a.notes}”</p>}
          </div>
          <div className="shrink-0 text-right text-xs text-fg-subtle">
            {a.actor ? a.actor.full_name || a.actor.email : "system"}
            <br />
            {fmtDateTime(a.created_at)}
          </div>
        </li>
      ))}
    </ol>
  );
}
