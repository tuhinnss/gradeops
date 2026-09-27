"use client";

import { ExamProgressList } from "@/components/ta/ExamProgressList";
import { Card, CardBody, ErrorState, PageHeader, SkeletonRows } from "@/components/ui";
import { ta } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

export default function TAExamsPage() {
  const exams = useApi(() => ta.exams(), []);
  return (
    <>
      <PageHeader title="My exams" subtitle="Exams you are assigned to review. Select an exam to open its queue." />
      {exams.error && <ErrorState message={exams.error} onRetry={exams.reload} />}
      <Card>
        <CardBody className="py-1">{exams.data ? <ExamProgressList exams={exams.data} /> : <SkeletonRows rows={4} className="py-3" />}</CardBody>
      </Card>
    </>
  );
}
