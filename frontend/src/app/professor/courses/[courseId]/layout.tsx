"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CourseContext } from "@/components/professor/CourseContext";
import { CourseFormDialog } from "@/components/professor/CourseFormDialog";
import { Badge, Button, ErrorState, RouteTabs, Skeleton } from "@/components/ui";
import { courses } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function CourseLayout({ children }: { children: React.ReactNode }) {
  const { courseId } = useParams<{ courseId: string }>();
  const course = useApi(() => courses.get(courseId), [courseId]);
  const [editing, setEditing] = useState(false);
  const c = course.data;
  const base = `/professor/courses/${courseId}`;

  if (course.error) return <ErrorState message={course.error} onRetry={course.reload} />;
  if (!c) return <Skeleton className="h-24 w-full" />;
  return (
    <CourseContext.Provider value={{ course: c, reload: course.reload }}>
      <div className="mb-4">
        <Link href="/professor/courses" className="text-xs text-fg-subtle hover:text-fg">
          ← Courses
        </Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="font-mono text-xs font-semibold text-accent">{c.course_code}</div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-fg">
              {c.name}
              {c.status === "archived" && <Badge>Archived</Badge>}
            </h1>
            <p className="text-sm text-fg-muted">{[c.semester, c.academic_year].filter(Boolean).join(" · ") || "No term set"}</p>
          </div>
          <Button size="sm" onClick={() => setEditing(true)}>
            Edit course
          </Button>
        </div>
      </div>
      <div className="mb-5">
        <RouteTabs
          items={[
            { href: base, label: "Overview", exact: true },
            { href: `${base}/students`, label: "Students", count: c.stats.student_count },
            { href: `${base}/tas`, label: "TAs", count: c.stats.ta_count },
            { href: `${base}/exams`, label: "Exams", count: c.stats.exam_count },
            { href: `${base}/gradebook`, label: "Gradebook" },
            { href: `${base}/analytics`, label: "Analytics" },
          ]}
        />
      </div>
      {children}
      <CourseFormDialog
        open={editing}
        course={c}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          void course.reload();
        }}
      />
    </CourseContext.Provider>
  );
}
