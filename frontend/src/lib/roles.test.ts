import { describe, expect, it } from "vitest";
import { homeForRole, roleForPath, safeNextPath } from "./roles";

describe("role routing", () => {
  it("sends each role to its own dashboard", () => {
    expect(homeForRole("professor")).toBe("/professor");
    expect(homeForRole("ta")).toBe("/ta");
  });

  it("knows which role owns a path", () => {
    expect(roleForPath("/professor")).toBe("professor");
    expect(roleForPath("/professor/exams/1")).toBe("professor");
    expect(roleForPath("/ta/reviews")).toBe("ta");
    expect(roleForPath("/tax")).toBeNull();
    expect(roleForPath("/workbench")).toBeNull();
  });

  it("honours a safe next path for the right role", () => {
    expect(safeNextPath("/ta/reviews/abc", "ta")).toBe("/ta/reviews/abc");
    expect(safeNextPath("/professor/exams?x=1", "professor")).toBe("/professor/exams?x=1");
  });

  it("never bounces a TA into professor pages after login", () => {
    expect(safeNextPath("/professor/exams", "ta")).toBe("/ta");
    expect(safeNextPath("/ta/reviews", "professor")).toBe("/professor");
  });

  it("rejects open redirects and loops", () => {
    expect(safeNextPath("https://evil.example", "ta")).toBe("/ta");
    expect(safeNextPath("//evil.example/x", "ta")).toBe("/ta");
    expect(safeNextPath("/\\evil.example", "ta")).toBe("/ta");
    expect(safeNextPath("/login", "professor")).toBe("/professor");
    expect(safeNextPath(null, "professor")).toBe("/professor");
  });
});
