"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ExamStatusBadge } from "@/components/grading/Badges";
import { GradebookTable } from "@/components/professor/GradebookTable";
import { Alert, Button, Card, ErrorState, PageHeader, SkeletonRows } from "@/components/ui";
import { exams } from "@/lib/endpoints";
import { downloadBlob, fmtMarks } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export default function ExamGradebookPage() {
  const { examId } = useParams<{ examId: string }>();
  const gb = useApi(() => exams.gradebook(examId), [examId]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"provisional" | "final" | null>(null);

  async function download(final: boolean) {
    setBusy(final ? "final" : "provisional");
    setError(null);
    try {
      const { blob, filename } = await exams.downloadGradebook(examId, final);
      downloadBlob(blob, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  const d = gb.data;
  return (
    <>
      <PageHeader
        eyebrow={
          <Link href={`/professor/exams/${examId}`} className="hover:text-fg">
            ← {d ? `${d.course_code} · ${d.exam_name}` : "Exam"}
          </Link>
        }
        title={
          <span className="flex items-center gap-2">
            Gradebook {d && <ExamStatusBadge status={d.status} />}
          </span>
        }
        subtitle={d ? `Maximum ${fmtMarks(d.max_score)} marks · ${d.is_final ? "final grades (professor-approved)" : "provisional — not yet approved"}` : undefined}
        actions={
          <>
            <Button onClick={() => void download(false)} loading={busy === "provisional"} disabled={!d}>
              Export CSV
            </Button>
            <Button variant="primary" onClick={() => void download(true)} loading={busy === "final"} disabled={!d?.is_final} title={d?.is_final ? undefined : "Available once the exam is approved"}>
              Export final gradebook
            </Button>
          </>
        }
      />
      {error && <Alert tone="error" className="mb-3" onDismiss={() => setError(null)}>{error}</Alert>}
      {gb.error && <ErrorState message={gb.error} onRetry={gb.reload} />}
      <Card>{d ? <GradebookTable gb={d} /> : !gb.error && <SkeletonRows rows={8} className="p-4" />}</Card>
    </>
  );
}
