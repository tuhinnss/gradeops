"use client";

import { useEffect, useState } from "react";
import { TAWorkloadTable } from "@/components/professor/TAWorkloadTable";
import { ButtonLink, EmptyState, ErrorState, PageHeader, Select, SkeletonRows } from "@/components/ui";
import { courses } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function TAManagementPage() {
  const list = useApi(() => courses.list("active"), []);
  const [courseId, setCourseId] = useState("");
  useEffect(() => {
    if (!courseId && list.data?.length) setCourseId(list.data[0].id);
  }, [list.data, courseId]);
  const course = list.data?.find((c) => c.id === courseId);
  return (
    <>
      <PageHeader
        title="TA management"
        subtitle="Staff each course, assign TAs to exams and track review workload."
        actions={
          list.data && list.data.length > 0 && (
            <Select aria-label="Course" className="w-64" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              {list.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.course_code} · {c.name}
                </option>
              ))}
            </Select>
          )
        }
      />
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <SkeletonRows rows={4} />}
      {list.data && list.data.length === 0 && <EmptyState title="No active courses" action={<ButtonLink href="/professor/courses" variant="primary">Create a course</ButtonLink>} />}
      {course && <TAWorkloadTable key={course.id} courseId={course.id} archived={false} />}
    </>
  );
}
