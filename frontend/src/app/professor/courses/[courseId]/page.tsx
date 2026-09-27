"use client";

import { ActivityFeed } from "@/components/grading/ActivityFeed";
import { useCourse } from "@/components/professor/CourseContext";
import { ExamTable } from "@/components/professor/ExamTable";
import { ButtonLink, Card, CardBody, CardHeader, EmptyState, SkeletonRows, StatCard } from "@/components/ui";
import { courses, exams } from "@/lib/endpoints";
import { fmtPct } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export default function CourseOverviewPage() {
  const { course } = useCourse();
  const list = useApi(() => exams.list({ course_id: course.id }), [course.id]);
  const activity = useApi(() => courses.activity(course.id), [course.id]);
  const s = course.stats;
  const active = list.data?.filter((e) => e.status !== "published") ?? [];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Students" value={s.student_count} href={`/professor/courses/${course.id}/students`} />
        <StatCard label="TAs" value={s.ta_count} href={`/professor/courses/${course.id}/tas`} />
        <StatCard label="Active exams" value={s.active_exam_count} hint={`${s.exam_count} in total`} href={`/professor/courses/${course.id}/exams`} />
        <StatCard label="Pending reviews" value={s.pending_reviews} tone={s.pending_reviews ? "warning" : "neutral"} />
        <StatCard label="Escalated" value={s.escalated} tone={s.escalated ? "danger" : "neutral"} href="/professor/reviews/escalated" />
        <StatCard label="Average score" value={fmtPct(s.average_score_pct, 1)} hint="Evaluated submissions" />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Grading status"
            description="Exams in this course that are not yet published."
            actions={<ButtonLink href={`/professor/exams/new?course=${course.id}`} size="sm" variant="primary">New exam</ButtonLink>}
          />
          {list.data ? (
            <ExamTable compact exams={active} empty={<div className="p-4"><EmptyState title="No exams in progress" /></div>} />
          ) : (
            <SkeletonRows rows={3} className="p-4" />
          )}
        </Card>
        <div className="space-y-4">
          {course.description && (
            <Card>
              <CardHeader title="About" />
              <CardBody>
                <p className="whitespace-pre-line text-sm text-fg-muted">{course.description}</p>
              </CardBody>
            </Card>
          )}
          <Card>
            <CardHeader title="Recent activity" />
            <CardBody className="py-1">{activity.data ? <ActivityFeed items={activity.data} reviewBasePath="/professor/reviews" /> : <SkeletonRows rows={4} className="py-3" />}</CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
