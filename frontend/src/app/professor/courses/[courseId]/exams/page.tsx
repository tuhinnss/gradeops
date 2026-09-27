"use client";

import { useCourse } from "@/components/professor/CourseContext";
import { ExamTable } from "@/components/professor/ExamTable";
import { ButtonLink, Card, CardHeader, EmptyState, ErrorState, SkeletonRows } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function CourseExamsPage() {
  const { course } = useCourse();
  const list = useApi(() => exams.list({ course_id: course.id }), [course.id]);
  return (
    <Card>
      <CardHeader
        title="Exams"
        actions={course.status === "active" && <ButtonLink href={`/professor/exams/new?course=${course.id}`} size="sm" variant="primary">New exam</ButtonLink>}
      />
      {list.error && <div className="p-4"><ErrorState message={list.error} onRetry={list.reload} /></div>}
      {list.data ? <ExamTable exams={list.data} empty={<div className="p-4"><EmptyState title="No exams yet" description="Create an exam to upload a rubric and answer sheets." /></div>} /> : !list.error && <SkeletonRows rows={3} className="p-4" />}
    </Card>
  );
}
