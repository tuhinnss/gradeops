"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AnalyticsView } from "@/components/professor/AnalyticsView";
import { ErrorState, PageHeader, SkeletonCards } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function ExamAnalyticsPage() {
  const { examId } = useParams<{ examId: string }>();
  const a = useApi(() => exams.analytics(examId), [examId]);
  return (
    <>
      <PageHeader
        eyebrow={<Link href={`/professor/exams/${examId}`} className="hover:text-fg">← Exam</Link>}
        title={a.data ? `${a.data.exam_name} · Analytics` : "Analytics"}
        subtitle="Computed from current (human-reviewed where available) marks."
      />
      {a.error && <ErrorState message={a.error} onRetry={a.reload} />}
      {!a.data && !a.error && <SkeletonCards count={6} />}
      {a.data && <AnalyticsView data={a.data} />}
    </>
  );
}
