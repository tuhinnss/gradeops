"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getResults, type EvaluationResponse, type QuestionResult } from "@/lib/api";

export type StoredSubmission = { id: string; studentId: string; filename: string };
export type WorkbenchSubmission = StoredSubmission & { evaluation?: EvaluationResponse; loading?: boolean; error?: string };

type Persisted = {
  rubricId: string | null;
  rubricName: string;
  rubricFilename: string | null;
  questionCount: number | null;
  submissions: StoredSubmission[];
};

export const WORKBENCH_STORAGE_KEY = "gradeops:dashboard:v1";

function loadPersisted(): Persisted | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(WORKBENCH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Persisted) : null;
  } catch {
    return null;
  }
}

/** Server evaluation → the dashboard's EvaluationResponse shape (null if not evaluated). */
export async function fetchEvaluation(s: StoredSubmission): Promise<EvaluationResponse | null> {
  try {
    const data = await getResults(s.id);
    if (data.results && Array.isArray(data.results)) {
      return {
        submission_id: String(data.submission_id ?? s.id),
        student_id: String(data.student_id ?? s.studentId),
        results: data.results as QuestionResult[],
        total: Number(data.total ?? 0),
        max_total: Number(data.max_total ?? data.total ?? 0),
        plagiarism_flags: (data.plagiarism_flags as EvaluationResponse["plagiarism_flags"]) ?? [],
        annotated_pdf_url: (data.annotated_pdf_url as string | null) ?? null,
      };
    }
  } catch {
    /* not evaluated yet */
  }
  return null;
}

/**
 * Workbench state: current rubric and uploaded sheets, persisted to localStorage
 * (IDs only — marks are always re-read from the server).
 */
export function useWorkbenchSession() {
  const [rubricName, setRubricName] = useState("Exam Rubric");
  const [rubricId, setRubricId] = useState<string | null>(null);
  const [rubricFilename, setRubricFilename] = useState<string | null>(null);
  const [questionCount, setQuestionCount] = useState<number | null>(null);
  const [submissions, setSubmissions] = useState<WorkbenchSubmission[]>([]);
  const hydrated = useRef(false);

  useEffect(() => {
    const p = loadPersisted();
    if (p) {
      setRubricId(p.rubricId);
      setRubricName(p.rubricName);
      setRubricFilename(p.rubricFilename);
      setQuestionCount(p.questionCount);
      setSubmissions(p.submissions.map((s) => ({ ...s })));
    }
    hydrated.current = true;
  }, []);

  useEffect(() => {
    if (!hydrated.current) return;
    localStorage.setItem(
      WORKBENCH_STORAGE_KEY,
      JSON.stringify({
        rubricId,
        rubricName,
        rubricFilename,
        questionCount,
        submissions: submissions.map(({ id, studentId, filename }) => ({ id, studentId, filename })),
      } satisfies Persisted),
    );
  }, [rubricId, rubricName, rubricFilename, questionCount, submissions]);

  // Hydrate evaluations for any submission that has none loaded yet.
  const idKey = submissions.map((s) => s.id).join(",");
  useEffect(() => {
    if (!idKey) return;
    let cancelled = false;
    void (async () => {
      const next = await Promise.all(
        submissions.map(async (s) => (s.evaluation ? s : { ...s, evaluation: (await fetchEvaluation(s)) ?? undefined })),
      );
      if (!cancelled) setSubmissions(next);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once per id list
  }, [idKey]);

  const refreshAll = useCallback(async (list: WorkbenchSubmission[]) => {
    const next = await Promise.all(
      list.map(async (s) => ({ ...s, loading: false, evaluation: (await fetchEvaluation(s)) ?? s.evaluation })),
    );
    setSubmissions(next);
  }, []);

  const clear = useCallback(() => {
    localStorage.removeItem(WORKBENCH_STORAGE_KEY);
    setRubricId(null);
    setRubricFilename(null);
    setQuestionCount(null);
    setSubmissions([]);
  }, []);

  return {
    rubricName, setRubricName, rubricId, setRubricId, rubricFilename, setRubricFilename,
    questionCount, setQuestionCount, submissions, setSubmissions, refreshAll, clear,
  };
}
