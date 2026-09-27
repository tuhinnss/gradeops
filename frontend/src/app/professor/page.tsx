"use client";

import { ActivityFeed } from "@/components/grading/ActivityFeed";
import { ExamTable } from "@/components/professor/ExamTable";
import { ButtonLink, Card, CardBody, CardHeader, EmptyState, ErrorState, PageHeader, SkeletonCards, SkeletonRows, StatCard } from "@/components/ui";
import { professor } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function ProfessorOverviewPage() {
  const { user } = useSession();
  const dash = useApi(() => professor.dashboard(), []);
  const d = dash.data;
  return (
    <>
      <PageHeader
        title={`Good day${user?.full_name ? `, ${user.full_name}` : ""}`}
        subtitle="What is happening across your courses right now."
        actions={
          <>
            <ButtonLink href="/professor/courses">Courses</ButtonLink>
            <ButtonLink href="/professor/exams/new" variant="primary">
              New exam
            </ButtonLink>
          </>
        }
      />
      {dash.error && <ErrorState message={dash.error} onRetry={dash.reload} />}
      {!d && !dash.error && <SkeletonCards count={8} />}
      {d && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Active courses" value={d.active_courses} href="/professor/courses" />
          <StatCard label="Active exams" value={d.active_exams} href="/professor/exams" />
          <StatCard label="Students" value={d.students} hint="Enrolled in active courses" />
          <StatCard label="Submissions" value={d.submissions} href="/professor/submissions?status=all" />
          <StatCard label="Pending TA reviews" value={d.pending_ta_reviews} tone={d.pending_ta_reviews ? "warning" : "success"} href="/professor/submissions?status=pending" hint={`${d.awaiting_professor_approval} awaiting your approval`} />
          <StatCard label="Escalated cases" value={d.escalated} tone={d.escalated ? "danger" : "neutral"} href="/professor/reviews/escalated" />
          <StatCard label="Integrity flags" value={d.integrity_flags_open} tone={d.integrity_flags_open ? "warning" : "neutral"} href="/professor/integrity" hint="Similarity flags awaiting review" />
          <StatCard label="Ready to publish" value={d.ready_to_publish} tone={d.ready_to_publish ? "violet" : "neutral"} href="/professor/gradebook" hint="Approved or locked exams" />
        </div>
      )}
      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Active exams" description="Grading progress across your courses." actions={<ButtonLink href="/professor/exams" size="sm" variant="ghost">All exams</ButtonLink>} />
          {d ? (
            <ExamTable
              compact
              exams={d.exams}
              empty={
                <div className="p-4">
                  <EmptyState title="No active exams" description="Create a course, then an exam, to start grading." action={<ButtonLink href="/professor/exams/new" variant="primary">Create exam</ButtonLink>} />
                </div>
              }
            />
          ) : (
            <SkeletonRows rows={4} className="p-4" />
          )}
        </Card>
        <Card>
          <CardHeader title="Recent activity" />
          <CardBody className="py-1">{d ? <ActivityFeed items={d.recent_activity} reviewBasePath="/professor/reviews" /> : <SkeletonRows rows={5} className="py-3" />}</CardBody>
        </Card>
      </div>
    </>
  );
}
