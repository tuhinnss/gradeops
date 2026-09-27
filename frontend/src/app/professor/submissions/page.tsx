"use client";

import { Suspense } from "react";
import { ReviewQueue } from "@/components/ta/ReviewQueue";
import { PageHeader, SkeletonRows } from "@/components/ui";
import { exams, professor } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function ProfessorSubmissionsPage() {
  const list = useApi(() => exams.list(), []);
  return (
    <>
      <PageHeader title="Submissions" subtitle="Every graded submission across your exams. Open one to review, override or approve it." />
      <Suspense fallback={<SkeletonRows rows={6} />}>
        <ReviewQueue fetcher={professor.submissions} exams={list.data ?? []} reviewBasePath="/professor/reviews" defaultStatus="all" />
      </Suspense>
    </>
  );
}
