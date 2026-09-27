"use client";

import Link from "next/link";
import { BarList, ColumnChart, StackedBar, StackLegend } from "@/components/charts/Charts";
import { Card, CardBody, CardHeader, EmptyState, StatCard, TD, TH, THead, TR, Table } from "@/components/ui";
import { fmtConfidence, fmtMarks, fmtPct } from "@/lib/format";
import type { ExamAnalyticsResponse } from "@/lib/types";

function TableToggle({ children }: { children: React.ReactNode }) {
  return (
    <details className="mt-3 text-xs">
      <summary className="cursor-pointer text-fg-subtle hover:text-fg">View as table</summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

export function AnalyticsView({ data, reviewBasePath = "/professor/reviews" }: { data: ExamAnalyticsResponse; reviewBasePath?: string }) {
  const s = data.summary;
  if (s.count === 0) {
    return <EmptyState title="No evaluated submissions yet" description="Analytics appear once AI evaluation has run for this exam." />;
  }
  const hardest = [...data.questions].sort((a, b) => a.average_pct - b.average_pct)[0]?.question;
  const r = data.review;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Graded submissions" value={s.count} />
        <StatCard label="Average" value={`${fmtMarks(s.average)} / ${fmtMarks(s.max_total)}`} hint={fmtPct(s.average_pct, 1)} />
        <StatCard label="Median" value={fmtMarks(s.median)} />
        <StatCard label="Highest" value={fmtMarks(s.highest)} />
        <StatCard label="Lowest" value={fmtMarks(s.lowest)} />
        <StatCard label="Std deviation" value={fmtMarks(s.std_dev, 2)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Score distribution" description="Students per 10% band of the maximum score (current marks)." />
          <CardBody>
            <ColumnChart
              data={data.distribution.map((b) => ({ label: `${b.lower_pct}–${b.upper_pct}%`, value: b.count }))}
              unit="students"
              ariaLabel="Score distribution histogram"
            />
            <TableToggle>
              <Table className="rounded-md border border-line">
                <THead>
                  <tr>
                    <TH>Band</TH>
                    <TH align="right">Students</TH>
                  </tr>
                </THead>
                <tbody>
                  {data.distribution.map((b) => (
                    <TR key={b.label}>
                      <TD>{b.label}</TD>
                      <TD align="right">{b.count}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            </TableToggle>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Question difficulty" description="Average score as a share of each question's maximum. Lower is harder." />
          <CardBody>
            <BarList
              ariaLabel="Average percentage per question"
              max={100}
              data={data.questions.map((q) => ({
                label: q.question,
                value: q.average_pct,
                display: `${fmtMarks(q.average, 2)} / ${fmtMarks(q.max_marks)}`,
                sublabel: `${fmtPct(q.average_pct, 1)} average · ${q.attempts} students`,
                highlight: q.question === hardest,
              }))}
            />
            {hardest && <p className="mt-3 text-xs text-fg-subtle">Hardest question: <b className="text-fg">{hardest}</b></p>}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Question breakdown" description="Share of students with full, partial and zero credit (current marks) and how often reviewers changed the AI score." actions={<StackLegend labels={["Full credit", "Partial", "Zero"]} />} />
        <Table>
          <THead>
            <tr>
              <TH>Question</TH>
              <TH align="right">Average</TH>
              <TH align="right">Students</TH>
              <TH className="w-1/4">Full / partial / zero</TH>
              <TH align="right">Full</TH>
              <TH align="right">Partial</TH>
              <TH align="right">Zero</TH>
              <TH align="right">AI average</TH>
              <TH align="right">AI confidence</TH>
              <TH align="right">Changed by reviewers</TH>
            </tr>
          </THead>
          <tbody>
            {data.questions.map((q) => (
              <TR key={q.question}>
                <TD className="font-medium">{q.question}</TD>
                <TD align="right">
                  {fmtMarks(q.average, 2)} / {fmtMarks(q.max_marks)}
                </TD>
                <TD align="right">{q.attempts}</TD>
                <TD>
                  <StackedBar
                    ariaLabel={`${q.question}: ${q.full_credit_pct}% full, ${q.partial_pct}% partial, ${q.zero_pct}% zero`}
                    segments={[
                      { key: "full", label: "Full credit", value: q.full_credit_pct },
                      { key: "partial", label: "Partial", value: q.partial_pct },
                      { key: "zero", label: "Zero", value: q.zero_pct },
                    ]}
                  />
                </TD>
                <TD align="right">{fmtPct(q.full_credit_pct)}</TD>
                <TD align="right">{fmtPct(q.partial_pct)}</TD>
                <TD align="right">{fmtPct(q.zero_pct)}</TD>
                <TD align="right">{fmtMarks(q.ai_average, 2)}</TD>
                <TD align="right">{fmtConfidence(q.average_confidence)}</TD>
                <TD align="right">{q.overridden}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Human review" description="How reviewers treated the AI's grades." />
          <CardBody>
            <div className="grid grid-cols-2 gap-3">
              <StatCard label="TA override rate" value={fmtPct(r.ta_override_rate, 1)} hint="Of submissions a TA decided on" />
              <StatCard label="Professor override rate" value={fmtPct(r.professor_override_rate, 1)} hint="Of professor-approved submissions" />
              <StatCard label="AI / TA disagreement" value={fmtPct(r.ai_ta_disagreement_rate, 1)} hint={`Mean difference ${fmtMarks(r.ai_ta_mean_abs_diff, 2)} marks`} />
              <StatCard label="Similarity flags" value={data.integrity.open} hint={`${data.integrity.dismissed} dismissed · ${data.integrity.confirmed} confirmed`} tone={data.integrity.open ? "warning" : "neutral"} />
            </div>
            <dl className="mt-4 grid grid-cols-5 gap-2 text-center text-xs">
              {[
                ["Awaiting TA", r.awaiting_ta],
                ["TA reviewed", r.ta_reviewed],
                ["Escalated", r.escalated],
                ["Prof. approved", r.professor_approved],
                ["Published", r.published],
              ].map(([k, v]) => (
                <div key={k as string} className="rounded-md border border-line py-2">
                  <dt className="text-fg-subtle">{k}</dt>
                  <dd className="tabular text-base font-semibold text-fg">{v}</dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Most-missed rubric criteria" description="Share of students where the AI found no evidence for the criterion." />
          {data.criteria.length === 0 ? (
            <CardBody>
              <p className="text-sm text-fg-subtle">No per-criterion evidence recorded (results from before criterion tracking).</p>
            </CardBody>
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>Question</TH>
                  <TH>Criterion</TH>
                  <TH align="right">Missed</TH>
                  <TH align="right">Partial</TH>
                </tr>
              </THead>
              <tbody>
                {data.criteria.slice(0, 10).map((c) => (
                  <TR key={`${c.question}-${c.criterion}`}>
                    <TD className="font-medium">{c.question}</TD>
                    <TD className="max-w-xs truncate text-sm" >{c.criterion}</TD>
                    <TD align="right">{fmtPct(c.missed_rate)}</TD>
                    <TD align="right">{fmtPct(c.partial_rate)}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>

      {data.students && (
        <Card>
          <CardHeader title="Students" description="Current marks, highest first." />
          <Table>
            <THead>
              <tr>
                <TH>#</TH>
                <TH>Student</TH>
                <TH align="right">Score</TH>
                <TH align="right">Percentage</TH>
              </tr>
            </THead>
            <tbody>
              {data.students.map((st, i) => (
                <TR key={st.submission_id}>
                  <TD className="text-fg-subtle">{i + 1}</TD>
                  <TD>
                    <Link href={`${reviewBasePath}/${st.submission_id}`} className="font-mono text-accent hover:underline">
                      {st.student_id}
                    </Link>
                    {st.student_name && <span className="ml-2 text-fg-muted">{st.student_name}</span>}
                  </TD>
                  <TD align="right">{fmtMarks(st.final_score)}</TD>
                  <TD align="right">{fmtPct(st.percentage, 1)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </div>
  );
}
