"use client";

import { Suspense } from "react";
import { HistoryTable } from "@/components/grading/HistoryTable";
import { ReviewQueue } from "@/components/ta/ReviewQueue";
import { Card, CardHeader, PageHeader, SkeletonRows } from "@/components/ui";
import { ta } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function TAEscalationsPage() {
  const exams = useApi(() => ta.exams(), []);
  const mine = useApi(() => ta.history({ action: "escalate", limit: 200 }), []);
  return (
    <>
      <PageHeader title="Escalations" subtitle="Submissions sent to the professor. Only the professor can resolve them." />
      <Suspense fallback={<SkeletonRows rows={4} />}>
        <ReviewQueue fetcher={ta.queue} exams={exams.data ?? []} reviewBasePath="/ta/reviews" defaultStatus="escalated" />
      </Suspense>
      <Card className="mt-6">
        <CardHeader title="Escalated by you" description="Every escalation you have raised, including resolved ones." />
        {mine.data ? <HistoryTable items={mine.data.items} reviewBasePath="/ta/reviews" /> : <SkeletonRows rows={3} className="p-4" />}
      </Card>
    </>
  );
}
