import Link from "next/link";
import { EmptyState } from "@/components/ui";
import { actionLabel, fmtMarks, fmtRelative } from "@/lib/format";
import type { ActivityItem } from "@/lib/types";

/** Recent persisted audit events (never synthesised). */
export function ActivityFeed({ items, reviewBasePath }: { items: ActivityItem[]; reviewBasePath?: string }) {
  if (!items.length) return <EmptyState title="No activity yet" description="Review and exam actions will appear here as they happen." />;
  return (
    <ul className="divide-y divide-line">
      {items.map((a, i) => (
        <li key={`${a.kind}-${a.created_at}-${i}`} className="flex items-start justify-between gap-3 py-2.5 text-sm">
          <div className="min-w-0">
            <span className="font-medium text-fg">{actionLabel(a.action)}</span>
            {a.student_id && (
              <>
                {" · "}
                {reviewBasePath && a.submission_id ? (
                  <Link href={`${reviewBasePath}/${a.submission_id}`} className="font-mono text-accent hover:underline">
                    {a.student_id}
                  </Link>
                ) : (
                  <span className="font-mono">{a.student_id}</span>
                )}
              </>
            )}
            {a.question && (
              <span className="tabular text-fg-muted">
                {" "}
                · {a.question} {fmtMarks(a.old_marks)} → {fmtMarks(a.new_marks)}
              </span>
            )}
            <div className="truncate text-xs text-fg-subtle">
              {a.exam_name}
              {a.actor && ` · ${a.actor.full_name || a.actor.email}`}
              {a.notes && ` · “${a.notes}”`}
            </div>
          </div>
          <span className="shrink-0 text-xs text-fg-subtle">{fmtRelative(a.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}
