import { authHeaders } from "./auth";

const DEFAULT_API = "http://localhost:8000";
export function getApiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? DEFAULT_API;
  return base;
}

export const API_PREFIX = "/api/v1";

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBase()}${p}`;
}

export type RubricUploadResponse = {
  id: string;
  message: string;
  filename: string;
  question_count: number;
};

export type UploadResponse = {
  id: string;
  message: string;
  filename: string;
};

export type QuestionResult = {
  question: string;
  marks_awarded: number;
  max_marks: number;
  justification: string;
  confidence: number;
  is_blank: boolean;
  key_points_matched?: string[];
  key_points_missed?: string[];
  negative_triggers?: string[];
};

export type PlagiarismFlag = {
  question: string;
  student_id_a: string;
  student_id_b: string;
  similarity: number;
  note: string;
};

export type EvaluationResponse = {
  submission_id: string;
  student_id: string;
  results: QuestionResult[];
  total: number;
  max_total: number;
  plagiarism_flags: PlagiarismFlag[];
  annotated_pdf_url: string | null;
  review_status?: string;
};

export type BulkUploadItem = { id: string; student_id: string; filename: string };

export type BulkUploadResponse = {
  uploaded: BulkUploadItem[];
  failed: { filename?: string; error: string }[];
  message: string;
};

export type BatchJobResponse = {
  id: string;
  rubric_id: string;
  status: string;
  total_count: number;
  completed_count: number;
  failed_count: number;
  progress_percent: number;
  submission_ids: string[];
  errors: { submission_id?: string; error: string }[];
};

export type AnalyticsData = {
  rubric_id: string;
  submission_count: number;
  evaluated_count: number;
  average_marks: number;
  max_total: number;
  toppers: { student_id: string; total: number }[];
  question_averages: Record<string, number>;
  pass_fail: { pass: number; fail: number };
  hardest_question: string | null;
  easiest_question: string | null;
  review_pending?: number;
  review_approved?: number;
};

export type ReviewState = {
  submission_id: string;
  student_id: string;
  review_status: string;
  reviewer_notes: string | null;
  results: QuestionResult[];
  total: number;
  max_total: number;
  audit_history: {
    id: string;
    action: string;
    question: string | null;
    old_marks: number | null;
    new_marks: number | null;
    notes: string | null;
    created_at: string | null;
  }[];
};

export async function uploadRubric(file: File, name: string): Promise<RubricUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);

  const res = await fetch(apiUrl(`${API_PREFIX}/upload/rubric`), {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });

  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(formatError(err, res.statusText));
  }
  return res.json();
}

export async function uploadAnswerSheet(
  file: File,
  studentId: string,
  rubricId?: string | null
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("student_id", studentId);
  if (rubricId) form.append("rubric_id", rubricId);

  const res = await fetch(apiUrl(`${API_PREFIX}/upload/answer-sheet`), {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });

  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(formatError(err, res.statusText));
  }
  return res.json();
}

export type EvaluateAllResponse = {
  job_id: string | null;
  status: string;
  total_processed: number;
  success_count: number;
  failed_count: number;
  current: number;
  errors: { submission_id?: string; error: string }[];
};

export async function startEvaluateAll(
  rubricId: string,
  submissionIds: string[],
  runPlagiarismCheck = true
): Promise<EvaluateAllResponse> {
  const res = await fetch(apiUrl(`${API_PREFIX}/evaluate/all`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      rubric_id: rubricId,
      submission_ids: submissionIds,
      run_plagiarism_check: runPlagiarismCheck,
    }),
  });
  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(formatError(err, res.statusText));
  }
  return res.json();
}

export async function getEvaluateAllJob(jobId: string): Promise<EvaluateAllResponse> {
  const res = await fetch(apiUrl(`${API_PREFIX}/evaluate/all/${jobId}`), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(formatError(err, res.statusText));
  }
  return res.json();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Start evaluate-all job and poll until complete. */
export async function evaluateAll(
  rubricId: string,
  submissionIds: string[],
  onProgress?: (current: number, total: number) => void,
  runPlagiarismCheck = true
): Promise<EvaluateAllResponse> {
  const started = await startEvaluateAll(rubricId, submissionIds, runPlagiarismCheck);
  if (!started.job_id || started.total_processed === 0) {
    return started;
  }

  for (;;) {
    const status = await getEvaluateAllJob(started.job_id);
    onProgress?.(status.current, status.total_processed);
    if (status.status === "completed") {
      return status;
    }
    await sleep(1500);
  }
}

export async function evaluateSubmission(
  submissionId: string,
  rubricId?: string | null,
  runPlagiarismCheck = true
): Promise<EvaluationResponse> {
  const res = await fetch(apiUrl(`${API_PREFIX}/evaluate/run`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      submission_id: submissionId,
      rubric_id: rubricId ?? null,
      run_plagiarism_check: runPlagiarismCheck,
    }),
  });

  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(formatError(err, res.statusText));
  }
  return res.json();
}

export async function getResults(submissionId: string): Promise<Record<string, unknown>> {
  const res = await fetch(apiUrl(`${API_PREFIX}/results/${submissionId}`), {
    method: "GET",
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(formatError(err, res.statusText));
  }
  return res.json();
}

export function annotatedPdfHref(annotatedPdfUrl: string | null, submissionId: string): string {
  if (annotatedPdfUrl?.startsWith("http")) return annotatedPdfUrl;
  const path = annotatedPdfUrl ?? `${API_PREFIX}/results/${submissionId}/annotated-pdf`;
  return apiUrl(path);
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return { detail: await res.text() };
  }
}

export async function bulkUploadPdfs(
  files: File[],
  rubricId?: string | null
): Promise<BulkUploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (rubricId) form.append("rubric_id", rubricId);

  const res = await fetch(apiUrl(`${API_PREFIX}/bulk/answer-sheets`), {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function bulkUploadZip(
  file: File,
  rubricId?: string | null
): Promise<BulkUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (rubricId) form.append("rubric_id", rubricId);

  const res = await fetch(apiUrl(`${API_PREFIX}/bulk/answer-sheets/zip`), {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function createBatchJob(
  rubricId: string,
  submissionIds: string[],
  runPlagiarism = true
): Promise<BatchJobResponse> {
  const res = await fetch(apiUrl(`${API_PREFIX}/bulk/jobs`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      rubric_id: rubricId,
      submission_ids: submissionIds,
      run_plagiarism_check: runPlagiarism,
    }),
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function getBatchJob(jobId: string): Promise<BatchJobResponse> {
  const res = await fetch(apiUrl(`${API_PREFIX}/bulk/jobs/${jobId}`), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function getRubricAnalytics(rubricId: string): Promise<AnalyticsData> {
  const res = await fetch(apiUrl(`${API_PREFIX}/analytics/rubric/${rubricId}`), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function getPlagiarismReport(rubricId: string) {
  const res = await fetch(apiUrl(`${API_PREFIX}/analytics/rubric/${rubricId}/plagiarism`), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function getReviewState(submissionId: string): Promise<ReviewState> {
  const res = await fetch(apiUrl(`${API_PREFIX}/review/${submissionId}`), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function submitReviewAction(
  submissionId: string,
  action: "approve" | "reject" | "override",
  notes?: string,
  overrides?: { question: string; marks_awarded: number; justification?: string }[]
): Promise<ReviewState> {
  const res = await fetch(apiUrl(`${API_PREFIX}/review/${submissionId}/action`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ action, notes, overrides: overrides ?? [] }),
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function login(email: string, password: string) {
  const res = await fetch(apiUrl(`${API_PREFIX}/auth/login`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

export async function register(
  email: string,
  password: string,
  fullName: string,
  role: "instructor" | "ta" = "ta"
) {
  const res = await fetch(apiUrl(`${API_PREFIX}/auth/register`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName, role }),
  });
  if (!res.ok) throw new Error(formatError(await safeJson(res), res.statusText));
  return res.json();
}

function formatError(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const o = body as Record<string, unknown>;
    if (typeof o.detail === "string") return o.detail;
    if (o.detail && typeof o.detail === "object") {
      const d = o.detail as Record<string, unknown>;
      if (typeof d.message === "string") return d.message;
    }
    if (typeof o.message === "string") return o.message;
  }
  return fallback;
}
