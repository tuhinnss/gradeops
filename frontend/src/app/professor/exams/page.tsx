"use client";

import { useState } from "react";
import { ExamTable } from "@/components/professor/ExamTable";
import { ButtonLink, Card, EmptyState, ErrorState, PageHeader, Select, SkeletonRows } from "@/components/ui";
import { courses, exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function ExamsPage() {
  const [courseId, setCourseId] = useState("");
  const [status, setStatus] = useState("");
  const courseList = useApi(() => courses.list("all"), []);
  const list = useApi(() => exams.list({ course_id: courseId || undefined, status: status || undefined }), [courseId, status]);
  return (
    <>
      <PageHeader
        title="Exams"
        subtitle="Every exam across your courses with its grading progress."
        actions={
          <>
            <Select aria-label="Course" className="w-52" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">All courses</option>
              {courseList.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.course_code} · {c.name}
                </option>
              ))}
            </Select>
            <Select aria-label="Status" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any status</option>
              <option value="draft">Setup</option>
              <option value="processing">AI processing</option>
              <option value="ta_review">TA review</option>
              <option value="approved">Approved</option>
              <option value="locked">Locked</option>
              <option value="published">Published</option>
            </Select>
            <ButtonLink href="/professor/exams/new" variant="primary">
              New exam
            </ButtonLink>
          </>
        }
      />
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      <Card>
        {list.data ? (
          <ExamTable exams={list.data} empty={<div className="p-4"><EmptyState title="No exams match" action={<ButtonLink href="/professor/exams/new" variant="primary">Create exam</ButtonLink>} /></div>} />
        ) : (
          !list.error && <SkeletonRows rows={5} className="p-4" />
        )}
      </Card>
    </>
  );
}
