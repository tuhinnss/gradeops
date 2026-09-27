import Link from "next/link";
import { ExamStatusBadge } from "@/components/grading/Badges";
import { EmptyState, ProgressBar } from "@/components/ui";
import type { TAExamResponse } from "@/lib/types";

export function ExamProgressList({ exams }: { exams: TAExamResponse[] }) {
  if (!exams.length) {
    return <EmptyState title="No exams assigned yet" description="A professor needs to add you to a course and assign you to an exam." />;
  }
  return (
    <ul className="divide-y divide-line">
      {exams.map((e) => {
        const reviewed = e.counts.ta_reviewed + e.counts.professor_approved + e.counts.published + e.counts.escalated;
        return (
          <li key={e.id} className="py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <Link href={`/ta/reviews?exam=${e.id}`} className="font-medium text-fg hover:underline">
                  {e.name}
                </Link>
                <div className="text-xs text-fg-subtle">
                  {e.course_code} · {e.course_name}
                </div>
              </div>
              <div className="flex items-center gap-3 text-xs text-fg-muted">
                <span className="tabular">
                  <b className="text-fg">{e.my_pending}</b> waiting for you
                </span>
                <span className="tabular">{e.my_reviewed} reviewed by you</span>
                <ExamStatusBadge status={e.status} />
              </div>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <ProgressBar value={reviewed} max={Math.max(e.counts.processed, 1)} label={`${e.name} review progress`} tone="success" />
              <span className="tabular w-24 shrink-0 text-right text-xs text-fg-subtle">
                {reviewed}/{e.counts.processed} reviewed
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
