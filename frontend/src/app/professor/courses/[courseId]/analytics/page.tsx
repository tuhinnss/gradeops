"use client";

import Link from "next/link";
import { BarList } from "@/components/charts/Charts";
import { ExamStatusBadge } from "@/components/grading/Badges";
import { useCourse } from "@/components/professor/CourseContext";
import { Card, CardBody, CardHeader, EmptyState, ErrorState, SkeletonRows, StatCard, TD, TH, THead, TR, Table } from "@/components/ui";
import { courses } from "@/lib/endpoints";
import { fmtMarks, fmtPct } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export default function CourseAnalyticsPage() {
  const { course } = useCourse();
  const a = useApi(() => courses.analytics(course.id), [course.id]);
  if (a.error) return <ErrorState message={a.error} onRetry={a.reload} />;
  if (!a.data) return <SkeletonRows rows={5} />;
  const graded = a.data.exams.filter((e) => e.summary.count > 0);
  const o = a.data.overall;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard label="Graded submissions" value={o.count} hint="Across all exams" />
        <StatCard label="Average" value={fmtPct(o.average, 1)} hint="Of each exam's maximum" />
        <StatCard label="Median" value={fmtPct(o.median, 1)} />
        <StatCard label="Range" value={o.count ? `${fmtPct(o.lowest)} – ${fmtPct(o.highest)}` : "—"} />
      </div>
      <Card>
        <CardHeader title="Average score by exam" description="Mean current score as a share of the exam's maximum." />
        <CardBody>
          {graded.length === 0 ? (
            <EmptyState title="No graded exams yet" />
          ) : (
            <BarList
              ariaLabel="Average percentage per exam"
              max={100}
              data={graded.map((e) => ({ label: e.exam_name, value: e.summary.average_pct ?? 0, display: fmtPct(e.summary.average_pct, 1), sublabel: `${e.summary.count} students` }))}
            />
          )}
        </CardBody>
      </Card>
      <Card>
        <Table>
          <THead>
            <tr>
              <TH>Exam</TH>
              <TH>Status</TH>
              <TH align="right">Graded</TH>
              <TH align="right">Average</TH>
              <TH align="right">Median</TH>
              <TH align="right">Highest</TH>
              <TH align="right">Lowest</TH>
            </tr>
          </THead>
          <tbody>
            {a.data.exams.map((e) => (
              <TR key={e.exam_id}>
                <TD>
                  <Link href={`/professor/exams/${e.exam_id}/analytics`} className="font-medium text-accent hover:underline">
                    {e.exam_name}
                  </Link>
                </TD>
                <TD>
                  <ExamStatusBadge status={e.status} />
                </TD>
                <TD align="right">{e.summary.count}</TD>
                <TD align="right">{e.summary.count ? `${fmtMarks(e.summary.average)} / ${fmtMarks(e.summary.max_total)}` : "—"}</TD>
                <TD align="right">{fmtMarks(e.summary.median)}</TD>
                <TD align="right">{fmtMarks(e.summary.highest)}</TD>
                <TD align="right">{fmtMarks(e.summary.lowest)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
