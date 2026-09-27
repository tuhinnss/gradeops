"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { IntegrityTable } from "@/components/professor/IntegrityTable";
import { Card, ErrorState, PageHeader, Select, SkeletonRows } from "@/components/ui";
import { exams, professor } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import type { IntegrityFlagStatus } from "@/lib/types";

function Integrity() {
  const params = useSearchParams();
  const router = useRouter();
  const examId = params.get("exam") ?? "";
  const status = (params.get("status") ?? "open") as IntegrityFlagStatus | "all";
  const flags = useApi(() => professor.integrity({ exam_id: examId || undefined, status: status === "all" ? undefined : status }), [examId, status]);
  const examList = useApi(() => exams.list(), []);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v);
    else next.delete(k);
    router.replace(`/professor/integrity${next.toString() ? `?${next}` : ""}`);
  };
  return (
    <>
      <PageHeader
        title="Integrity"
        subtitle="Potential matches between answers to the same question. These are review prompts, not findings — you make the determination."
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
            <Select aria-label="Status" className="w-44" value={status} onChange={(e) => set("status", e.target.value)}>
              <option value="open">Review required</option>
              <option value="dismissed">No concern</option>
              <option value="confirmed">Concern confirmed</option>
              <option value="all">All</option>
            </Select>
          </>
        }
      />
      {flags.error && <ErrorState message={flags.error} onRetry={flags.reload} />}
      <Card>{flags.data ? <IntegrityTable flags={flags.data} onChanged={() => void flags.reload()} /> : !flags.error && <SkeletonRows rows={4} className="p-4" />}</Card>
    </>
  );
}

export default function IntegrityPage() {
  return (
    <Suspense>
      <Integrity />
    </Suspense>
  );
}
