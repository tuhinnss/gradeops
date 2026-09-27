"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ExamStatusBadge } from "@/components/grading/Badges";
import { ExamAuditLog } from "@/components/professor/ExamAuditLog";
import { ExamPipeline } from "@/components/professor/ExamPipeline";
import { ExamSubmissionsTable } from "@/components/professor/ExamSubmissionsTable";
import { ExamTAPanel } from "@/components/professor/ExamTAPanel";
import { FinalizationPanel } from "@/components/professor/FinalizationPanel";
import { ProcessingPanel } from "@/components/professor/ProcessingPanel";
import { RubricPanel } from "@/components/professor/RubricPanel";
import { UploadSubmissionsPanel } from "@/components/professor/UploadSubmissionsPanel";
import { ButtonLink, Card, CardBody, CardHeader, ErrorState, Skeleton, SkeletonCards, StatCard } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { fmtDate, fmtMarks } from "@/lib/format";
import { useApi, useInterval } from "@/lib/hooks";

export default function ExamCommandCenter() {
  const { examId } = useParams<{ examId: string }>();
  const detail = useApi(() => exams.get(examId), [examId]);
  const [refreshKey, setRefreshKey] = useState(0);
  const e = detail.data;
  const reload = () => {
    void detail.reload();
    setRefreshKey((k) => k + 1);
  };
  // Keep counts live while the AI pipeline is running.
  useInterval(() => void detail.reload(), 4000, e?.status === "processing");

  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.reload} />;
  if (!e) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20 w-full" />
        <SkeletonCards count={6} />
      </div>
    );
  }
  const c = e.counts;
  const setupEditable = e.status === "draft" || e.status === "ta_review";
  const reviewed = c.ta_reviewed + c.professor_approved + c.published;

  return (
    <div className="space-y-4">
      <div>
        <Link href="/professor/exams" className="text-xs text-fg-subtle hover:text-fg">
          ← Exams
        </Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold text-fg">
              {e.name} <ExamStatusBadge status={e.status} />
            </h1>
            <p className="text-sm text-fg-muted">
              <Link href={`/professor/courses/${e.course_id}`} className="font-mono text-accent hover:underline">
                {e.course_code}
              </Link>{" "}
              {[` · ${e.course_name}`, e.exam_date && fmtDate(e.exam_date), `${c.submissions} students`, `${fmtMarks(e.rubric?.total_marks ?? e.total_marks)} marks`].filter(Boolean).join(" · ")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ButtonLink href={`/professor/submissions?exam=${e.id}&status=all`} size="sm">
              Review queue
            </ButtonLink>
            <ButtonLink href={`/professor/exams/${e.id}/analytics`} size="sm">
              Analytics
            </ButtonLink>
            <ButtonLink href={`/professor/exams/${e.id}/gradebook`} size="sm" variant="primary">
              Gradebook
            </ButtonLink>
          </div>
        </div>
      </div>

      <Card>
        <CardBody>
          <ExamPipeline exam={e} />
        </CardBody>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Total submissions" value={c.submissions} hint={c.uploaded ? `${c.uploaded} not yet processed` : undefined} />
        <StatCard label="AI processed" value={c.processed} hint={c.failed ? `${c.failed} failed` : c.processing ? `${c.processing} in progress` : undefined} tone={c.failed ? "danger" : "neutral"} />
        <StatCard label="Reviewed" value={reviewed} hint={`${c.professor_approved + c.published} professor-approved`} tone="success" />
        <StatCard label="Pending review" value={c.awaiting_ta} hint={c.needs_manual_grading ? `${c.needs_manual_grading} need manual grading` : undefined} tone={c.awaiting_ta ? "warning" : "neutral"} href={`/professor/submissions?exam=${e.id}&status=pending`} />
        <StatCard label="Escalated" value={c.escalated} tone={c.escalated ? "danger" : "neutral"} href={`/professor/reviews/escalated?exam=${e.id}`} />
        <StatCard label="Integrity flags" value={c.integrity_open} tone={c.integrity_open ? "warning" : "neutral"} href={`/professor/integrity?exam=${e.id}`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <ProcessingPanel exam={e} onChanged={reload} />
          <UploadSubmissionsPanel examId={e.id} disabled={!setupEditable} onUploaded={reload} />
          <ExamSubmissionsTable examId={e.id} editable={setupEditable} refreshKey={refreshKey} onChanged={reload} />
        </div>
        <div className="space-y-4">
          <FinalizationPanel exam={e} onChanged={(updated) => { detail.setData(updated); setRefreshKey((k) => k + 1); }} />
          <RubricPanel exam={e} editable={setupEditable} onChanged={(updated) => detail.setData(updated)} />
          <ExamTAPanel exam={e} editable={e.status !== "published" && e.status !== "locked"} onChanged={reload} />
          <Card>
            <CardHeader title="Exam history" />
            <CardBody className="max-h-96 overflow-y-auto py-1">
              <ExamAuditLog items={e.audit} />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
