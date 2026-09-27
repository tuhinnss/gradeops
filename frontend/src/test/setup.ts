import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// jsdom lacks object URLs (used for authenticated answer images).
Object.assign(URL, {
  createObjectURL: vi.fn(() => "blob:mock"),
  revokeObjectURL: vi.fn(),
});
