"use client";

import { useCourse } from "@/components/professor/CourseContext";
import { ExamGradebookList } from "@/components/professor/ExamGradebookList";
import { Card, CardHeader, ErrorState, SkeletonRows } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function CourseGradebookPage() {
  const { course } = useCourse();
  const list = useApi(() => exams.list({ course_id: course.id }), [course.id]);
  return (
    <Card>
      <CardHeader title="Gradebooks" description="One gradebook per exam. Exports before approval are marked PROVISIONAL." />
      {list.error && <div className="p-4"><ErrorState message={list.error} onRetry={list.reload} /></div>}
      {list.data ? <ExamGradebookList exams={list.data} /> : !list.error && <SkeletonRows rows={3} className="p-4" />}
    </Card>
  );
}
