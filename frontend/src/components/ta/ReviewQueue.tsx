"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { ConfidenceBadge, ReviewStatusBadge } from "@/components/grading/Badges";
import { Badge, Button, ButtonLink, EmptyState, ErrorState, Input, Label, Select, SkeletonRows, TD, TH, THead, TR, Table } from "@/components/ui";
import type { QueueFilters } from "@/lib/endpoints";
import { fmtMarks, fmtRelative } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ExamResponse, ReviewQueueResponse } from "@/lib/types";

const CONFIDENCE_RANGES: Record<string, { label: string; min?: number; max?: number }> = {
  "": { label: "Any confidence" },
  low: { label: "Low (< 50%)", max: 0.4999 },
  medium: { label: "Medium (50–70%)", min: 0.5, max: 0.6999 },
  high: { label: "High (≥ 70%)", min: 0.7 },
};

const STATUS_OPTIONS = [
  { value: "pending", label: "Awaiting review" },
  { value: "reviewed", label: "TA reviewed" },
  { value: "escalated", label: "Escalated" },
  { value: "approved", label: "Professor approved" },
  { value: "all", label: "All" },
];

const PAGE = 50;

/**
 * Filterable review queue shared by the TA queue and the professor's
 * submissions view. Filters live in the URL so a refresh keeps them.
 */
export function ReviewQueue({
  fetcher,
  exams,
  reviewBasePath,
  defaultStatus = "pending",
}: {
  fetcher: (f: QueueFilters) => Promise<ReviewQueueResponse>;
  exams: ExamResponse[];
  reviewBasePath: string;
  defaultStatus?: string;
}) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const get = (k: string, d = "") => params.get(k) ?? d;

  const filters = useMemo<QueueFilters>(() => {
    const range = CONFIDENCE_RANGES[get("confidence")] ?? CONFIDENCE_RANGES[""];
    return {
      exam_id: get("exam") || undefined,
      course_id: get("course") || undefined,
      status: get("status", defaultStatus),
      min_confidence: range.min,
      max_confidence: range.max,
      integrity: get("integrity") === "1" || undefined,
      manual: get("manual") === "1" || undefined,
      student: get("student") || undefined,
      question: get("question") || undefined,
      sort: (get("sort", "confidence_asc") as QueueFilters["sort"]) ?? "confidence_asc",
      limit: PAGE,
      offset: Number(get("offset", "0")) || 0,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, defaultStatus]);

  const queue = useApi(() => fetcher(filters), [JSON.stringify(filters)]);

  function set(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    router.replace(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  const courses = useMemo(() => {
    const seen = new Map<string, string>();
    exams.forEach((e) => seen.set(e.course_id, `${e.course_code} · ${e.course_name}`));
    return Array.from(seen.entries());
  }, [exams]);

  const data = queue.data;
  const offset = filters.offset ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-8">
        <div className="2xl:col-span-2">
          <Label htmlFor="f-exam">Exam</Label>
          <Select id="f-exam" value={get("exam")} onChange={(e) => set("exam", e.target.value)}>
            <option value="">All exams</option>
            {exams.map((e) => (
              <option key={e.id} value={e.id}>
                {e.course_code} · {e.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="f-course">Course</Label>
          <Select id="f-course" value={get("course")} onChange={(e) => set("course", e.target.value)}>
            <option value="">All courses</option>
            {courses.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="f-status">Status</Label>
          <Select id="f-status" value={get("status", defaultStatus)} onChange={(e) => set("status", e.target.value)}>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="f-conf">Confidence</Label>
          <Select id="f-conf" value={get("confidence")} onChange={(e) => set("confidence", e.target.value)}>
            {Object.entries(CONFIDENCE_RANGES).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="f-student">Student</Label>
          <Input id="f-student" placeholder="ID or name" defaultValue={get("student")} onKeyDown={(e) => e.key === "Enter" && set("student", (e.target as HTMLInputElement).value.trim())} onBlur={(e) => set("student", e.target.value.trim())} />
        </div>
        <div>
          <Label htmlFor="f-question">Question</Label>
          <Input id="f-question" placeholder="e.g. Q4" defaultValue={get("question")} onKeyDown={(e) => e.key === "Enter" && set("question", (e.target as HTMLInputElement).value.trim())} onBlur={(e) => set("question", e.target.value.trim())} />
        </div>
        <div>
          <Label htmlFor="f-sort">Sort</Label>
          <Select id="f-sort" value={get("sort", "confidence_asc")} onChange={(e) => set("sort", e.target.value)}>
            <option value="confidence_asc">Lowest confidence</option>
            <option value="confidence_desc">Highest confidence</option>
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
          </Select>
        </div>
        <div className="flex items-end gap-4 sm:col-span-2 lg:col-span-4 2xl:col-span-8">
          <label className="flex items-center gap-2 text-sm text-fg-muted">
            <input type="checkbox" checked={get("integrity") === "1"} onChange={(e) => set("integrity", e.target.checked ? "1" : "")} />
            Similarity flag only
          </label>
          <label className="flex items-center gap-2 text-sm text-fg-muted">
            <input type="checkbox" checked={get("manual") === "1"} onChange={(e) => set("manual", e.target.checked ? "1" : "")} />
            Needs manual grading
          </label>
          <span className="tabular ml-auto text-xs text-fg-subtle">{data ? `${data.total} submission${data.total === 1 ? "" : "s"}` : ""}</span>
        </div>
      </div>

      {queue.error && <ErrorState message={queue.error} onRetry={queue.reload} />}
      {queue.loading && !data && <SkeletonRows rows={8} />}
      {data && data.items.length === 0 && (
        <EmptyState title="Nothing here" description={filters.status === "pending" ? "No submissions are waiting for review with these filters." : "No submissions match these filters."} />
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          <Table>
            <THead>
              <tr>
                <TH>Student</TH>
                <TH>Exam</TH>
                <TH>Question</TH>
                <TH align="right">AI score</TH>
                <TH>Confidence</TH>
                <TH align="right">Total</TH>
                <TH>Status</TH>
                <TH>Flags</TH>
                <TH />
              </tr>
            </THead>
            <tbody>
              {data.items.map((i) => (
                <TR key={i.submission_id} onClick={() => router.push(`${reviewBasePath}/${i.submission_id}`)}>
                  <TD>
                    <div className="font-mono text-sm">{i.student_id}</div>
                    {i.student_name && <div className="text-xs text-fg-subtle">{i.student_name}</div>}
                  </TD>
                  <TD>
                    <div className="text-sm">{i.exam_name}</div>
                    <div className="text-xs text-fg-subtle">{i.course_code}</div>
                  </TD>
                  <TD className="font-medium">{i.focus?.question ?? "—"}</TD>
                  <TD align="right">{i.focus ? `${fmtMarks(i.focus.marks_awarded)} / ${fmtMarks(i.focus.max_marks)}` : "—"}</TD>
                  <TD>
                    <ConfidenceBadge value={i.focus?.confidence ?? i.min_confidence} />
                  </TD>
                  <TD align="right">
                    {fmtMarks(i.total)} / {fmtMarks(i.max_total)}
                  </TD>
                  <TD>
                    <ReviewStatusBadge status={i.review_status} />
                  </TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {i.needs_manual_grading && <Badge tone="warning">Manual</Badge>}
                      {i.integrity_flags > 0 && <Badge tone="danger">Similarity</Badge>}
                      {i.assigned_to_me && <Badge tone="info">Assigned to me</Badge>}
                    </div>
                  </TD>
                  <TD align="right">
                    <ButtonLink href={`${reviewBasePath}/${i.submission_id}`} size="sm" variant={i.review_status === "ai_evaluated" || i.review_status === "ta_pending" ? "primary" : "secondary"}>
                      Open review
                    </ButtonLink>
                    <div className="mt-0.5 text-[11px] text-fg-subtle">{fmtRelative(i.updated_at)}</div>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
          {data.total > PAGE && (
            <div className="flex items-center justify-between border-t border-line px-3 py-2 text-xs text-fg-subtle">
              <span className="tabular">
                {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
              </span>
              <div className="flex gap-2">
                <Button size="sm" disabled={offset === 0} onClick={() => set("offset", String(Math.max(0, offset - PAGE)))}>
                  Previous
                </Button>
                <Button size="sm" disabled={offset + PAGE >= data.total} onClick={() => set("offset", String(offset + PAGE))}>
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
