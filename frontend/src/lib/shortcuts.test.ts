import { describe, expect, it } from "vitest";
import { isTypingTarget, shortcutFor } from "./shortcuts";

const el = (tag: string, attrs: Record<string, string> = {}) => {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  return e;
};

describe("review shortcuts", () => {
  it("maps keys to actions", () => {
    expect(shortcutFor({ key: "a" })).toEqual({ type: "approve" });
    expect(shortcutFor({ key: "O" })).toEqual({ type: "override" });
    expect(shortcutFor({ key: "e" })).toEqual({ type: "escalate" });
    expect(shortcutFor({ key: "ArrowLeft" })).toEqual({ type: "prev" });
    expect(shortcutFor({ key: "ArrowRight" })).toEqual({ type: "next" });
    expect(shortcutFor({ key: " " })).toEqual({ type: "details" });
    expect(shortcutFor({ key: "3" })).toEqual({ type: "question", index: 2 });
    expect(shortcutFor({ key: "x" })).toBeNull();
  });

  it("does not fire while typing in form fields", () => {
    for (const target of [el("input"), el("input", { type: "number" }), el("textarea"), el("select")]) {
      expect(isTypingTarget(target)).toBe(true);
      expect(shortcutFor({ key: "a", target })).toBeNull();
    }
    const editable = el("div", { contenteditable: "true" });
    expect(shortcutFor({ key: "e", target: editable })).toBeNull();
  });

  it("still fires on checkboxes and buttons", () => {
    expect(shortcutFor({ key: "a", target: el("input", { type: "checkbox" }) })).toEqual({ type: "approve" });
    expect(shortcutFor({ key: "a", target: el("button") })).toEqual({ type: "approve" });
  });

  it("ignores modified keys (browser shortcuts)", () => {
    expect(shortcutFor({ key: "a", ctrlKey: true })).toBeNull();
    expect(shortcutFor({ key: "e", metaKey: true })).toBeNull();
  });
});
