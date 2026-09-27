"use client";

import { ExamGradebookList } from "@/components/professor/ExamGradebookList";
import { Card, ErrorState, PageHeader, SkeletonRows } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function GradebookIndexPage() {
  const list = useApi(() => exams.list(), []);
  return (
    <>
      <PageHeader title="Gradebook" subtitle="Open an exam's gradebook to inspect, override and export grades. Exports before approval are marked PROVISIONAL." />
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      <Card>{list.data ? <ExamGradebookList exams={list.data} /> : !list.error && <SkeletonRows rows={4} className="p-4" />}</Card>
    </>
  );
}
