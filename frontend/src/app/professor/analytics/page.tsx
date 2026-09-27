"use client";

import { useEffect, useState } from "react";
import { AnalyticsView } from "@/components/professor/AnalyticsView";
import { ButtonLink, EmptyState, ErrorState, PageHeader, Select, SkeletonCards } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function ProfessorAnalyticsPage() {
  const list = useApi(() => exams.list(), []);
  const [examId, setExamId] = useState("");
  useEffect(() => {
    if (examId || !list.data?.length) return;
    const graded = list.data.find((e) => e.counts.processed > 0) ?? list.data[0];
    setExamId(graded.id);
  }, [list.data, examId]);
  const exam = list.data?.find((e) => e.id === examId);
  const analytics = useApi(() => (examId ? exams.analytics(examId) : Promise.resolve(null)), [examId]);
  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Exam, question and student-level results. Course comparisons are on each course's Analytics tab."
        actions={
          <>
            {list.data && list.data.length > 0 && (
              <Select aria-label="Exam" className="w-64" value={examId} onChange={(e) => setExamId(e.target.value)}>
                {list.data.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.course_code} · {e.name}
                  </option>
                ))}
              </Select>
            )}
            {exam && <ButtonLink href={`/professor/courses/${exam.course_id}/analytics`}>Course view</ButtonLink>}
          </>
        }
      />
      {list.data && list.data.length === 0 && <EmptyState title="No exams yet" />}
      {analytics.error && <ErrorState message={analytics.error} onRetry={analytics.reload} />}
      {examId && !analytics.data && !analytics.error && <SkeletonCards count={6} />}
      {analytics.data && <AnalyticsView data={analytics.data} />}
    </>
  );
}
