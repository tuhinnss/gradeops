"use client";

import { createContext, useContext } from "react";
import type { CourseResponse } from "@/lib/types";

export const CourseContext = createContext<{ course: CourseResponse; reload: () => Promise<void> } | null>(null);

export function useCourse() {
  const ctx = useContext(CourseContext);
  if (!ctx) throw new Error("useCourse must be used within a course page");
  return ctx;
}
