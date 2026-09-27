"use client";

import { Suspense } from "react";
import { ReviewQueue } from "@/components/ta/ReviewQueue";
import { PageHeader, SkeletonRows } from "@/components/ui";
import { ta } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function TAReviewQueuePage() {
  const exams = useApi(() => ta.exams(), []);
  return (
    <>
      <PageHeader title="Review queue" subtitle="AI-graded submissions waiting for your decision. Lowest-confidence work comes first." />
      <Suspense fallback={<SkeletonRows rows={6} />}>
        <ReviewQueue fetcher={ta.queue} exams={exams.data ?? []} reviewBasePath="/ta/reviews" />
      </Suspense>
    </>
  );
}
