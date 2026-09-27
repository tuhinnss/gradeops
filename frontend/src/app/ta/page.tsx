"use client";

import { ActivityFeed } from "@/components/grading/ActivityFeed";
import { ExamProgressList } from "@/components/ta/ExamProgressList";
import { ButtonLink, Card, CardBody, CardHeader, ErrorState, PageHeader, SkeletonCards, SkeletonRows, StatCard } from "@/components/ui";
import { ta } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function TAOverviewPage() {
  const session = useSession();
  const dash = useApi(() => ta.dashboard(), []);
  const exams = useApi(() => ta.exams(), []);
  const d = dash.data;
  return (
    <>
      <PageHeader
        title={`Welcome${session.user?.full_name ? `, ${session.user.full_name.split(" ")[0]}` : ""}`}
        subtitle="Your review workload across assigned exams."
        actions={
          <ButtonLink href="/ta/reviews" variant="primary">
            {d && d.pending_reviews > 0 ? `Start reviewing (${d.pending_reviews})` : "Open review queue"}
          </ButtonLink>
        }
      />
      {dash.error && <ErrorState message={dash.error} onRetry={dash.reload} />}
      {!d && !dash.error && <SkeletonCards count={6} />}
      {d && (
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <StatCard label="Assigned exams" value={d.assigned_exams} href="/ta/exams" />
          <StatCard label="Pending reviews" value={d.pending_reviews} tone={d.pending_reviews ? "warning" : "success"} href="/ta/reviews" />
          <StatCard label="Reviewed today" value={d.reviewed_today} />
          <StatCard label="Total reviewed" value={d.total_reviewed} href="/ta/history" />
          <StatCard label="Overrides" value={d.overrides} tone="violet" />
          <StatCard label="Open escalations" value={d.escalations_open} hint={`${d.escalations_total} escalated in total`} tone={d.escalations_open ? "danger" : "neutral"} href="/ta/escalations" />
        </div>
      )}
      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="My exams" description="Review progress for exams you are assigned to." />
          <CardBody className="py-1">{exams.data ? <ExamProgressList exams={exams.data} /> : <SkeletonRows rows={3} className="py-3" />}</CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="My recent activity" />
          <CardBody className="py-1">{d ? <ActivityFeed items={d.recent_activity} reviewBasePath="/ta/reviews" /> : <SkeletonRows rows={4} className="py-3" />}</CardBody>
        </Card>
      </div>
    </>
  );
}
