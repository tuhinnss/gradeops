"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { EscalationQueue } from "@/components/professor/EscalationQueue";
import { Card, ErrorState, PageHeader, Select, SkeletonRows } from "@/components/ui";
import { exams, professor } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

function Escalations() {
  const params = useSearchParams();
  const router = useRouter();
  const examId = params.get("exam") ?? "";
  const includeResolved = params.get("resolved") === "1";
  const list = useApi(() => professor.escalations({ exam_id: examId || undefined, include_resolved: includeResolved }), [examId, includeResolved]);
  const examList = useApi(() => exams.list(), []);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v);
    else next.delete(k);
    router.replace(`/professor/reviews/escalated${next.toString() ? `?${next}` : ""}`);
  };
  return (
    <>
      <PageHeader
        title="Review & escalations"
        subtitle="Cases TAs sent to you. Open one to inspect the handwriting, change marks, resolve it, or return it to the TA with notes."
        actions={
          <>
            <Select aria-label="Exam" className="w-56" value={examId} onChange={(e) => set("exam", e.target.value)}>
              <option value="">All exams</option>
              {examList.data?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.course_code} · {e.name}
                </option>
              ))}
            </Select>
            <label className="flex items-center gap-2 text-sm text-fg-muted">
              <input type="checkbox" checked={includeResolved} onChange={(e) => set("resolved", e.target.checked ? "1" : "")} />
              Include resolved
            </label>
          </>
        }
      />
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      <Card>{list.data ? <EscalationQueue items={list.data} /> : !list.error && <SkeletonRows rows={5} className="p-4" />}</Card>
    </>
  );
}

export default function EscalationsPage() {
  return (
    <Suspense>
      <Escalations />
    </Suspense>
  );
}
