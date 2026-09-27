"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/layout/Icon";
import { Alert, Badge, Button, Card, CardHeader, cx, ErrorState, Skeleton } from "@/components/ui";
import { review } from "@/lib/endpoints";
import { confidenceTone, fmtConfidence, fmtDateTime, fmtMarks } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { shortcutFor } from "@/lib/shortcuts";
import { ESCALATION_REASONS, type ReviewActionRequest, type ReviewDetailResponse, type ReviewQuestion } from "@/lib/types";
import { AnswerViewer } from "./AnswerViewer";
import { AuditTimeline } from "./AuditTimeline";
import { ConfidenceBadge, ReviewStatusBadge } from "./Badges";
import { EscalationDialog } from "./EscalationDialog";
import { OverrideDialog } from "./OverrideDialog";
import { ReturnDialog } from "./ReturnDialog";
import { RubricBreakdown } from "./RubricBreakdown";
import { ShortcutHelp } from "./ShortcutHelp";

type DialogKind = null | "override" | "escalate" | "resolve" | "return";

const FLASH_KEY = "gradeops:review-flash";

const REASON_LABEL: Record<string, string> = Object.fromEntries(ESCALATION_REASONS.map((r) => [r.value, r.label]));
const DOT: Record<string, string> = { success: "bg-emerald-500", warning: "bg-amber-500", danger: "bg-rose-500", neutral: "bg-fg-subtle" };

function initialQuestion(d: ReviewDetailResponse): number {
  if (!d.questions.length) return 0;
  let best = 0;
  d.questions.forEach((q, i) => {
    const b = d.questions[best];
    if (Number(q.requires_manual_grading) > Number(b.requires_manual_grading) || (q.requires_manual_grading === b.requires_manual_grading && q.confidence < b.confidence)) best = i;
  });
  return best;
}

/**
 * Split-screen review: original handwriting on the left; OCR, rubric evidence and
 * the AI's score on the right; approve / override / escalate below.
 */
export function ReviewWorkspace({
  submissionId,
  basePath,
  backHref,
  backLabel,
  initialAction,
}: {
  submissionId: string;
  basePath: string;
  backHref: string;
  backLabel: string;
  /** Open this dialog once the submission loads (e.g. "override" from the gradebook). */
  initialAction?: "override" | null;
}) {
  const router = useRouter();
  const detail = useApi(() => review.detail(submissionId), [submissionId]);
  const { error, loading, reload } = detail;
  // After auto-advancing, ignore the previous submission's data until the new one loads.
  const data = detail.data && detail.data.submission.id === submissionId ? detail.data : null;
  const [qIndex, setQIndex] = useState(0);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  // Auto-advancing remounts the page (new route param), so carry the confirmation over.
  useEffect(() => {
    try {
      const carried = sessionStorage.getItem(FLASH_KEY);
      if (carried) {
        sessionStorage.removeItem(FLASH_KEY);
        setFlash(carried);
      }
    } catch {
      /* storage unavailable */
    }
  }, []);
  const [showDetails, setShowDetails] = useState(false);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    if (data) setQIndex(initialQuestion(data));
  }, [data]);

  const loadedId = data?.submission.id;
  const canOverride = !!data?.permissions.can_override;
  useEffect(() => {
    if (loadedId && initialAction === "override" && canOverride) setDialog("override");
  }, [loadedId, initialAction, canOverride]);

  const question: ReviewQuestion | null = data?.questions[qIndex] ?? null;
  const perms = data?.permissions;
  const nav = data?.navigation;

  const go = useCallback((id: string | null | undefined) => id && router.push(`${basePath}/${id}`), [router, basePath]);

  const act = useCallback(
    async (body: Omit<ReviewActionRequest, "expected_review_status" | "overrides" | "notes" | "reason"> & Partial<ReviewActionRequest>, done: string) => {
      if (!data) return;
      setBusy(true);
      setActionError(null);
      try {
        await review.act(submissionId, {
          overrides: [],
          notes: null,
          reason: null,
          ...body,
          expected_review_status: data.submission.review_status,
        });
        setDialog(null);
        const next = data.navigation.next_pending_id;
        if (next && next !== submissionId) {
          const message = `${done} — opening the next submission`;
          setFlash(message);
          try {
            sessionStorage.setItem(FLASH_KEY, message);
          } catch {
            /* storage unavailable */
          }
          go(next);
        } else {
          setFlash(`${done}. No more submissions waiting in this exam.`);
          await reload();
        }
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "Action failed");
      } finally {
        setBusy(false);
      }
    },
    [data, submissionId, go, reload],
  );

  // Keyboard shortcuts (disabled while a dialog is open or the user is typing).
  // One listener for the component's lifetime reads the latest state from a ref,
  // so a keypress right after new data renders never hits a stale handler.
  const keyState = useRef({ dialog, data, perms, nav, busy, act, go });
  keyState.current = { dialog, data, perms, nav, busy, act, go };
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const { dialog, data, perms, nav, busy, act, go } = keyState.current;
      if (dialog || !data) return;
      const s = shortcutFor(e);
      if (!s) return;
      if (s.type === "approve" && perms?.can_approve && !busy) void act({ action: "approve" }, "Approved");
      else if (s.type === "override" && (perms?.can_override || perms?.can_resolve)) setDialog(perms?.can_override ? "override" : "resolve");
      else if (s.type === "escalate" && perms?.can_escalate) setDialog("escalate");
      else if (s.type === "prev") go(nav?.prev_id);
      else if (s.type === "next") go(nav?.next_id);
      else if (s.type === "details") setShowDetails((v) => !v);
      else if (s.type === "help") setHelp((v) => !v);
      else if (s.type === "question" && s.index < data.questions.length) setQIndex(s.index);
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const questionsForDialog = useMemo(() => data?.questions ?? [], [data]);

  if (loading && !data) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-16 w-full" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-[480px] w-full" />
          <Skeleton className="h-[480px] w-full" />
        </div>
      </div>
    );
  }
  if (error || !data) return <ErrorState message={error ?? "Could not load submission"} onRetry={reload} />;

  const sub = data.submission;
  const changed = sub.ai_total !== null && Math.abs((sub.ai_total ?? 0) - sub.total) > 1e-9;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link href={backHref} className="text-xs text-fg-subtle hover:text-fg">
            ← {backLabel}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold text-fg">
              <span className="font-mono">{sub.student_id}</span>
              {sub.student_name && <span className="ml-2 font-normal text-fg-muted">{sub.student_name}</span>}
            </h1>
            <ReviewStatusBadge status={sub.review_status} />
            {sub.needs_manual_grading && <Badge tone="warning">Needs manual grading</Badge>}
          </div>
          <p className="mt-0.5 text-sm text-fg-muted">
            {data.exam ? `${data.exam.course_code} · ${data.exam.name}` : "Unassigned submission"} · Total{" "}
            <span className="tabular font-medium text-fg">
              {fmtMarks(sub.total)} / {fmtMarks(sub.max_total)}
            </span>
            {changed && <span className="tabular text-fg-subtle"> (AI {fmtMarks(sub.ai_total)})</span>}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {nav && nav.queue_size > 0 && (
            <span className="tabular mr-1 text-xs text-fg-subtle">
              {nav.position ?? "–"} of {nav.queue_size}
            </span>
          )}
          <Button size="sm" variant="secondary" disabled={!nav?.prev_id} onClick={() => go(nav?.prev_id)} aria-label="Previous submission" title="Previous (←)">
            <Icon name="arrowLeft" className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="secondary" disabled={!nav?.next_id} onClick={() => go(nav?.next_id)} aria-label="Next submission" title="Next (→)">
            <Icon name="arrowRight" className="h-3.5 w-3.5" />
          </Button>
          <ShortcutHelp open={help} onToggle={() => setHelp((v) => !v)} />
        </div>
      </div>

      {flash && (
        <Alert tone="success" onDismiss={() => setFlash(null)}>
          {flash}
        </Alert>
      )}
      {actionError && !dialog && (
        <Alert tone="error" onDismiss={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
      {sub.review_status === "escalated" && (
        <Alert tone="warning">
          <span className="font-medium">Escalated</span> by {sub.escalated_by?.full_name ?? "a TA"} · {fmtDateTime(sub.escalated_at)} — {REASON_LABEL[sub.escalation_reason ?? ""] ?? sub.escalation_reason}
          {sub.escalation_notes && <span className="block text-xs">“{sub.escalation_notes}”</span>}
        </Alert>
      )}
      {perms?.read_only_reason && sub.review_status !== "escalated" && <Alert tone="info">{perms.read_only_reason}</Alert>}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* LEFT: original handwriting */}
        <Card className="overflow-hidden lg:sticky lg:top-20 lg:h-[calc(100vh-7rem)]">
          <AnswerViewer submissionId={sub.id} question={question?.question ?? null} pageCount={sub.page_count} />
        </Card>

        {/* RIGHT: OCR + AI grading + rubric */}
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Questions">
            {data.questions.map((q, i) => (
              <button
                key={q.question}
                type="button"
                role="tab"
                aria-selected={i === qIndex}
                onClick={() => setQIndex(i)}
                className={cx(
                  "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition",
                  i === qIndex ? "border-accent bg-accent/10 font-semibold text-fg" : "border-line text-fg-muted hover:bg-surface-raised",
                )}
              >
                <span className={cx("h-1.5 w-1.5 rounded-full", DOT[confidenceTone(q.confidence)])} aria-hidden />
                {q.question}
                <span className="tabular text-fg-subtle">
                  {fmtMarks(q.marks_awarded)}/{fmtMarks(q.max_marks)}
                </span>
              </button>
            ))}
          </div>

          {question && (
            <Card>
              <CardHeader
                title={
                  <span className="flex flex-wrap items-center gap-2">
                    Question {question.question.replace(/^Q/, "")}
                    <ConfidenceBadge value={question.confidence} label />
                    {question.is_blank && <Badge tone="neutral">Blank</Badge>}
                    {question.scoring_method === "lexical" && <Badge tone="warning" title="Semantic model was unavailable; keyword matching only">Keyword match only</Badge>}
                  </span>
                }
                actions={
                  <div className="text-right">
                    <div className="tabular text-lg font-semibold text-fg">
                      {fmtMarks(question.marks_awarded)} <span className="text-sm font-normal text-fg-subtle">/ {fmtMarks(question.max_marks)}</span>
                    </div>
                    {question.ai_marks_awarded !== null && Math.abs(question.ai_marks_awarded - question.marks_awarded) > 1e-9 && (
                      <div className="tabular text-xs text-fg-subtle">AI score {fmtMarks(question.ai_marks_awarded)}</div>
                    )}
                  </div>
                }
              />
              <div className="space-y-4 p-4">
                {question.requires_manual_grading && (
                  <Alert tone="warning">The AI could not tie this answer to the rubric with confidence. Grade it manually from the handwriting.</Alert>
                )}
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                    OCR text {question.answer?.ocr_confidence != null && <span className="font-normal normal-case">· OCR confidence {fmtConfidence(question.answer.ocr_confidence)}</span>}
                  </h3>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-surface-sunken p-3 font-mono text-xs leading-relaxed text-fg">
                    {question.answer?.text?.trim() || "(no text recognised)"}
                  </pre>
                </section>
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Rubric &amp; AI grading</h3>
                  <RubricBreakdown question={question} />
                </section>
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-fg-subtle">AI explanation</h3>
                  <p className="text-sm leading-relaxed text-fg-muted">{question.justification}</p>
                  {question.reviewer_comment && (
                    <p className="mt-2 rounded-md border-l-2 border-violet-500 bg-violet-500/5 px-3 py-2 text-sm text-fg">
                      <span className="text-xs font-semibold text-violet-700 dark:text-violet-300">Reviewer comment · </span>
                      {question.reviewer_comment}
                    </p>
                  )}
                </section>
              </div>
            </Card>
          )}

          {/* Actions */}
          <Card className="sticky bottom-3 z-10 shadow-lg">
            <div className="flex flex-wrap items-center gap-2 p-3">
              {perms?.can_approve && (
                <Button variant="success" loading={busy && !dialog} onClick={() => void act({ action: "approve" }, "Approved")} title="Approve (A)">
                  <Icon name="check" className="h-4 w-4" /> Approve <kbd className="ml-1 hidden rounded bg-white/20 px-1 text-[10px] sm:inline">A</kbd>
                </Button>
              )}
              {perms?.can_override && (
                <Button variant="secondary" onClick={() => setDialog("override")} title="Override (O)">
                  <Icon name="wrench" className="h-4 w-4" /> Override <kbd className="ml-1 hidden rounded border border-line px-1 text-[10px] sm:inline">O</kbd>
                </Button>
              )}
              {perms?.can_escalate && (
                <Button variant="secondary" onClick={() => setDialog("escalate")} title="Escalate (E)" className="text-rose-700 dark:text-rose-300">
                  <Icon name="flag" className="h-4 w-4" /> Escalate <kbd className="ml-1 hidden rounded border border-line px-1 text-[10px] sm:inline">E</kbd>
                </Button>
              )}
              {perms?.can_resolve && (
                <Button variant="primary" onClick={() => setDialog("resolve")}>
                  Resolve escalation
                </Button>
              )}
              {perms?.can_return && (
                <Button variant="ghost" onClick={() => setDialog("return")}>
                  Return to TA
                </Button>
              )}
              {!perms?.can_approve && !perms?.can_override && !perms?.can_escalate && !perms?.can_resolve && (
                <span className="text-sm text-fg-subtle">{perms?.read_only_reason ?? "No actions available"}</span>
              )}
              <button type="button" onClick={() => setShowDetails((v) => !v)} className="ml-auto text-xs text-fg-muted hover:text-fg" aria-expanded={showDetails}>
                {showDetails ? "Hide" : "Show"} details <kbd className="rounded border border-line px-1 text-[10px]">Space</kbd>
              </button>
            </div>
          </Card>

          {showDetails && (
            <Card>
              <CardHeader title="Review details" description="Similarity flags and the full audit trail for this submission." />
              <div className="space-y-5 p-4">
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Similarity flags</h3>
                  {data.integrity_flags.length === 0 ? (
                    <p className="text-sm text-fg-subtle">No similarity flags.</p>
                  ) : (
                    <ul className="space-y-1 text-sm">
                      {data.integrity_flags.map((f) => (
                        <li key={f.id} className="flex flex-wrap items-center gap-2">
                          <Badge tone={f.status === "open" ? "warning" : "neutral"}>{f.status === "open" ? "Review required" : f.status}</Badge>
                          {f.question}: potential match with <span className="font-mono">{f.other_student_id}</span>
                          <span className="tabular text-fg-subtle">({Math.round(f.similarity * 100)}% similar)</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Audit history</h3>
                  <AuditTimeline items={data.audit_history} />
                </section>
              </div>
            </Card>
          )}
        </div>
      </div>

      <OverrideDialog
        open={dialog === "override" || dialog === "resolve"}
        mode={dialog === "resolve" ? "resolve" : "override"}
        questions={questionsForDialog}
        focusQuestion={question?.question ?? null}
        busy={busy}
        error={actionError}
        onClose={() => {
          setDialog(null);
          setActionError(null);
        }}
        onSubmit={(v) =>
          void act(
            { action: dialog === "resolve" ? "resolve" : "override", overrides: v.overrides, reason: v.reason || null, notes: v.notes || null },
            dialog === "resolve" ? "Escalation resolved" : "Override saved",
          )
        }
      />
      <EscalationDialog
        open={dialog === "escalate"}
        busy={busy}
        error={actionError}
        onClose={() => {
          setDialog(null);
          setActionError(null);
        }}
        onSubmit={(reason, notes) => void act({ action: "escalate", reason, notes: notes || null }, "Escalated to the professor")}
      />
      <ReturnDialog
        open={dialog === "return"}
        busy={busy}
        error={actionError}
        onClose={() => {
          setDialog(null);
          setActionError(null);
        }}
        onSubmit={(notes) => void act({ action: "return_to_ta", notes }, "Returned to the TA queue")}
      />
    </div>
  );
}
