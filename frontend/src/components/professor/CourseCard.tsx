import Link from "next/link";
import { Badge } from "@/components/ui";
import { fmtPct } from "@/lib/format";
import type { CourseResponse } from "@/lib/types";

export function CourseCard({ course, actions }: { course: CourseResponse; actions?: React.ReactNode }) {
  const s = course.stats;
  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface">
      <div className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <div className="font-mono text-xs font-semibold text-accent">{course.course_code}</div>
          <Link href={`/professor/courses/${course.id}`} className="block truncate text-base font-semibold text-fg hover:underline">
            {course.name}
          </Link>
          <div className="text-xs text-fg-subtle">{[course.semester, course.academic_year].filter(Boolean).join(" · ") || "No term set"}</div>
        </div>
        {course.status === "archived" && <Badge>Archived</Badge>}
      </div>
      <dl className="grid grid-cols-3 gap-y-3 px-4 py-3 text-center">
        {[
          ["Students", s.student_count],
          ["TAs", s.ta_count],
          ["Active exams", s.active_exam_count],
          ["Pending reviews", s.pending_reviews],
          ["Escalated", s.escalated],
          ["Average", fmtPct(s.average_score_pct)],
        ].map(([label, value]) => (
          <div key={label as string}>
            <dt className="text-[11px] text-fg-subtle">{label}</dt>
            <dd className="tabular text-sm font-semibold text-fg">{value}</dd>
          </div>
        ))}
      </dl>
      {actions && <div className="mt-auto flex gap-2 border-t border-line px-4 py-2.5">{actions}</div>}
    </div>
  );
}
