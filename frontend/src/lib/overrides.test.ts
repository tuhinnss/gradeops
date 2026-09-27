import { describe, expect, it } from "vitest";
import { changedOverrides, validateOverride, type OverrideDraft } from "./overrides";

const draft = (value: string, extra: Partial<OverrideDraft> = {}): OverrideDraft => ({ question: "Q4", maxMarks: 5, current: 3.5, value, comment: "", ...extra });

describe("override validation", () => {
  it("enforces 0 <= marks <= question maximum", () => {
    expect(validateOverride(draft("5"))).toBeNull();
    expect(validateOverride(draft("0"))).toBeNull();
    expect(validateOverride(draft("5.5"))).toMatch(/Maximum is 5/);
    expect(validateOverride(draft("-1"))).toMatch(/negative/);
    expect(validateOverride(draft("abc"))).toMatch(/number/);
    expect(validateOverride(draft(""))).toBeNull();
  });

  it("only submits changed, valid questions", () => {
    const out = changedOverrides([
      draft("4", { question: "Q1" }),
      draft("3.5", { question: "Q2" }), // unchanged
      draft("", { question: "Q3" }), // untouched
      draft("9", { question: "Q4" }), // invalid
      draft("3.5", { question: "Q5", comment: "Units fine" }), // comment only
    ]);
    expect(out).toEqual([
      { question: "Q1", marks_awarded: 4, justification: undefined },
      { question: "Q5", marks_awarded: 3.5, justification: "Units fine" },
    ]);
  });
});
