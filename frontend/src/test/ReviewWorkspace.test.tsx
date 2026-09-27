import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReviewDetailResponse } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const detail = vi.fn();
const act = vi.fn();
vi.mock("@/lib/endpoints", () => ({
  review: {
    detail: (...a: unknown[]) => detail(...a),
    act: (...a: unknown[]) => act(...a),
    answerImage: vi.fn().mockResolvedValue({ url: "blob:mock", page: 0, cropped: true }),
  },
}));

import { ReviewWorkspace } from "@/components/grading/ReviewWorkspace";

function fixture(overrides: Partial<ReviewDetailResponse["permissions"]> = {}, status: ReviewDetailResponse["submission"]["review_status"] = "ai_evaluated"): ReviewDetailResponse {
  const q = (question: string, marks: number, max: number, confidence: number) => ({
    question, max_marks: max, marks_awarded: marks, ai_marks_awarded: marks, confidence,
    justification: `${question} AI explanation`, reviewer_comment: null, is_blank: false,
    requires_manual_grading: false, scoring_method: "semantic",
    criteria: [{ criterion: "Correct formula", kind: "key_point" as const, max_marks: max, awarded: marks, status: "met" as const, semantic_similarity: 0.7, keyword_overlap: 0.6 }],
    key_points_matched: ["Correct formula"], key_points_partial: [], key_points_missed: [], negative_triggers: [],
    rubric: { key_points: ["Correct formula"], partial_credit_rules: [], negative_conditions: [] },
    answer: { text: `${question} handwritten text`, ocr_confidence: 0.8, page_index: 0, bbox: null, is_blank: false },
  });
  return {
    submission: {
      id: "sub-1", student_id: "240122065", student_name: "Asha", source_filename: "a.pdf", status: "evaluated",
      review_status: status, page_count: 2, total: 7.5, max_total: 10, ai_total: 7.5, ta_total: null, professor_total: null,
      min_confidence: 0.61, needs_manual_grading: false, reviewer_notes: null, escalation_reason: null, escalation_notes: null,
      escalated_by: null, escalated_at: null, reviewed_by: null, reviewed_at: null, approved_by: null, approved_at: null,
      assigned_ta: null, has_annotated_pdf: true,
    },
    exam: { id: "exam-1", name: "Midsem", status: "ta_review", course_code: "CS3001", course_name: "DS" },
    questions: [q("Q1", 4, 5, 0.9), q("Q4", 3.5, 5, 0.61)],
    integrity_flags: [],
    audit_history: [],
    permissions: { can_approve: true, can_override: true, can_escalate: true, can_resolve: false, can_return: false, read_only_reason: null, ...overrides },
    navigation: { prev_id: "sub-0", next_id: "sub-2", next_pending_id: "sub-2", position: 2, queue_size: 3 },
  };
}

beforeEach(() => {
  detail.mockResolvedValue(fixture());
  act.mockResolvedValue({});
});

async function renderWorkspace() {
  render(<ReviewWorkspace submissionId="sub-1" basePath="/ta/reviews" backHref="/ta/reviews" backLabel="Review queue" />);
  await screen.findByText("240122065");
}

describe("ReviewWorkspace", () => {
  it("shows OCR, rubric evidence and AI score, opening on the lowest-confidence question", async () => {
    await renderWorkspace();
    expect(screen.getByText("Q4 handwritten text")).toBeInTheDocument();
    expect(screen.getByText("Q4 AI explanation")).toBeInTheDocument();
    expect(screen.getByText("Correct formula")).toBeInTheDocument();
    expect(within(screen.getByRole("tablist", { name: "Questions" })).getByRole("tab", { selected: true })).toHaveTextContent("Q4");
    expect(await screen.findByAltText("Handwritten answer for Q4")).toBeInTheDocument();
  });

  it("approves with A, sends the expected status, and advances to the next pending submission", async () => {
    await renderWorkspace();
    fireEvent.keyDown(window, { key: "a" });
    await waitFor(() => expect(act).toHaveBeenCalledTimes(1));
    expect(act).toHaveBeenCalledWith("sub-1", expect.objectContaining({ action: "approve", expected_review_status: "ai_evaluated" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/ta/reviews/sub-2"));
  });

  it("does not trigger shortcuts while typing in a field", async () => {
    await renderWorkspace();
    fireEvent.keyDown(window, { key: "o" });
    const dialog = await screen.findByRole("dialog", { name: "Override marks" });
    const input = within(dialog).getByLabelText("New marks for Q4");
    await userEvent.type(input, "a");
    fireEvent.keyDown(input, { key: "a" });
    expect(act).not.toHaveBeenCalled();
  });

  it("validates override marks and requires a reason", async () => {
    await renderWorkspace();
    fireEvent.keyDown(window, { key: "o" });
    const dialog = await screen.findByRole("dialog", { name: "Override marks" });
    const input = within(dialog).getByLabelText("New marks for Q4");
    await userEvent.type(input, "6");
    expect(within(dialog).getByText("Maximum is 5")).toBeInTheDocument();
    const save = within(dialog).getByRole("button", { name: /Save/ });
    expect(save).toBeDisabled();
    await userEvent.clear(input);
    await userEvent.type(input, "4.5");
    expect(save).toBeDisabled(); // reason still missing
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Units were correct");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() =>
      expect(act).toHaveBeenCalledWith(
        "sub-1",
        expect.objectContaining({ action: "override", reason: "Units were correct", overrides: [{ question: "Q4", marks_awarded: 4.5, justification: undefined }] }),
      ),
    );
  });

  it("escalates only with a reason, and requires notes for 'other'", async () => {
    await renderWorkspace();
    fireEvent.keyDown(window, { key: "e" });
    const dialog = await screen.findByRole("dialog", { name: "Escalate to professor" });
    const submit = within(dialog).getByRole("button", { name: "Escalate" });
    expect(submit).toBeDisabled();
    await userEvent.selectOptions(within(dialog).getByLabelText(/Reason/), "other");
    expect(submit).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Notes/), "Page 3 missing");
    await userEvent.click(submit);
    await waitFor(() => expect(act).toHaveBeenCalledWith("sub-1", expect.objectContaining({ action: "escalate", reason: "other", notes: "Page 3 missing" })));
  });

  it("closes a dialog with Escape without acting", async () => {
    await renderWorkspace();
    fireEvent.keyDown(window, { key: "e" });
    await screen.findByRole("dialog");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(act).not.toHaveBeenCalled();
  });

  it("navigates with the arrow keys", async () => {
    await renderWorkspace();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(push).toHaveBeenCalledWith("/ta/reviews/sub-0");
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(push).toHaveBeenCalledWith("/ta/reviews/sub-2");
  });

  it("offers no TA actions on an escalated submission", async () => {
    detail.mockResolvedValue(fixture({ can_approve: false, can_override: false, can_escalate: false, read_only_reason: "Escalated to the professor — awaiting resolution" }, "escalated"));
    await renderWorkspace();
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "a" });
    expect(act).not.toHaveBeenCalled();
    expect(screen.getByText(/awaiting resolution/)).toBeInTheDocument();
  });

  it("surfaces a server rejection (e.g. concurrent change)", async () => {
    act.mockRejectedValueOnce(new Error("Submission is now ta_approved; reload before acting"));
    await renderWorkspace();
    await userEvent.click(screen.getByRole("button", { name: /Approve/ }));
    expect(await screen.findByText(/reload before acting/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
