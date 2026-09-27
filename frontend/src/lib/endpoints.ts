/** Typed wrappers for the role-scoped GradeOps API. */
import { rawRequest, request } from "./client";
import type {
  ActivityItem,
  BatchJobResponse,
  CourseAnalyticsResponse,
  CourseCreate,
  CourseResponse,
  CourseUpdate,
  DistributeResponse,
  EscalationResponse,
  ExamAnalyticsResponse,
  ExamCreate,
  ExamDetailResponse,
  ExamResponse,
  ExamUpdate,
  FinalizationSummary,
  GradebookResponse,
  IntegrityFlagResponse,
  IntegrityFlagStatus,
  MappingValidateResponse,
  ProfessorDashboardResponse,
  ReviewActionRequest,
  ReviewDetailResponse,
  ReviewHistoryResponse,
  ReviewQueueResponse,
  RubricDetail,
  RubricSchemaInput,
  RubricSummary,
  StudentImportResponse,
  StudentIn,
  StudentResponse,
  SubmissionListResponse,
  SubmissionReviewResponse,
  SubmissionUploadResponse,
  TADashboardResponse,
  TAExamResponse,
  TAWorkload,
  TAAddRequest,
  UserSummary,
} from "./types";

export type QueueFilters = {
  exam_id?: string;
  course_id?: string;
  status?: string;
  min_confidence?: number;
  max_confidence?: number;
  integrity?: boolean;
  manual?: boolean;
  student?: string;
  question?: string;
  sort?: "confidence_asc" | "confidence_desc" | "newest" | "oldest";
  limit?: number;
  offset?: number;
};

export const courses = {
  list: (status: "active" | "archived" | "all" = "active") =>
    request<CourseResponse[]>("/courses", { query: { status } }),
  get: (id: string) => request<CourseResponse>(`/courses/${id}`),
  create: (body: CourseCreate) => request<CourseResponse>("/courses", { json: body }),
  update: (id: string, body: CourseUpdate) => request<CourseResponse>(`/courses/${id}`, { method: "PATCH", json: body }),
  archive: (id: string) => request<CourseResponse>(`/courses/${id}`, { method: "DELETE" }),
  students: (id: string) => request<StudentResponse[]>(`/courses/${id}/students`),
  addStudents: (id: string, students: StudentIn[]) =>
    request<StudentImportResponse>(`/courses/${id}/students`, { json: { students } }),
  importCsv: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<StudentImportResponse>(`/courses/${id}/students/import-csv`, { form });
  },
  dropStudent: (id: string, studentRecordId: string) =>
    request<void>(`/courses/${id}/students/${studentRecordId}`, { method: "DELETE" }),
  tas: (id: string) => request<TAWorkload[]>(`/courses/${id}/tas`),
  addTa: (id: string, body: TAAddRequest) => request<TAWorkload>(`/courses/${id}/tas`, { json: body }),
  removeTa: (id: string, userId: string) => request<void>(`/courses/${id}/tas/${userId}`, { method: "DELETE" }),
  analytics: (id: string) => request<CourseAnalyticsResponse>(`/courses/${id}/analytics`),
  activity: (id: string) => request<ActivityItem[]>(`/courses/${id}/activity`),
};

export const exams = {
  list: (query: { course_id?: string; status?: string } = {}) => request<ExamResponse[]>("/exams", { query }),
  get: (id: string) => request<ExamDetailResponse>(`/exams/${id}`),
  create: (body: ExamCreate) => request<ExamDetailResponse>("/exams", { json: body }),
  update: (id: string, body: ExamUpdate) => request<ExamDetailResponse>(`/exams/${id}`, { method: "PATCH", json: body }),
  rubric: (id: string) => request<RubricDetail>(`/exams/${id}/rubric`),
  uploadRubric: (id: string, file: File, name?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    return request<ExamDetailResponse>(`/exams/${id}/rubric`, { form });
  },
  linkRubric: (id: string, rubricId: string) =>
    request<ExamDetailResponse>(`/exams/${id}/rubric`, { method: "PUT", json: { rubric_id: rubricId } }),
  assignTa: (id: string, taId: string) => request<UserSummary[]>(`/exams/${id}/tas`, { json: { ta_id: taId } }),
  unassignTa: (id: string, taId: string) => request<UserSummary[]>(`/exams/${id}/tas/${taId}`, { method: "DELETE" }),
  distribute: (id: string, rebalance = false) =>
    request<DistributeResponse>(`/exams/${id}/distribute`, { json: { rebalance } }),
  submissions: (id: string, query: { review_status?: string; status?: string } = {}) =>
    request<SubmissionListResponse>(`/exams/${id}/submissions`, { query: { ...query, limit: 1000 } }),
  validateMapping: (id: string, items: { filename: string; student_id?: string | null }[], autoEnroll: boolean) =>
    request<MappingValidateResponse>(`/exams/${id}/submissions/validate`, {
      json: { items },
      query: { auto_enroll: autoEnroll },
    }),
  uploadSubmissions: (id: string, files: File[], studentIds: (string | null)[], autoEnroll: boolean) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    form.append("student_ids", JSON.stringify(studentIds));
    form.append("auto_enroll", String(autoEnroll));
    return request<SubmissionUploadResponse>(`/exams/${id}/submissions`, { form });
  },
  deleteSubmission: (id: string, submissionId: string) =>
    request<void>(`/exams/${id}/submissions/${submissionId}`, { method: "DELETE" }),
  evaluate: (id: string, reevaluate = false, runPlagiarismCheck = true) =>
    request<BatchJobResponse>(`/exams/${id}/evaluate`, {
      json: { reevaluate, run_plagiarism_check: runPlagiarismCheck },
    }),
  job: (jobId: string) => request<BatchJobResponse>(`/bulk/jobs/${jobId}`),
  publishSummary: (id: string) => request<FinalizationSummary>(`/exams/${id}/publish-summary`),
  approve: (id: string, notes?: string) => request<ExamDetailResponse>(`/exams/${id}/approve`, { json: { notes } }),
  lock: (id: string, notes?: string) => request<ExamDetailResponse>(`/exams/${id}/lock`, { json: { notes } }),
  publish: (id: string, acknowledgeIntegrity: boolean, notes?: string) =>
    request<ExamDetailResponse>(`/exams/${id}/publish`, {
      json: { notes, acknowledge_integrity_flags: acknowledgeIntegrity },
    }),
  reopen: (id: string, reason: string) => request<ExamDetailResponse>(`/exams/${id}/reopen`, { json: { reason } }),
  gradebook: (id: string) => request<GradebookResponse>(`/exams/${id}/gradebook`),
  analytics: (id: string) => request<ExamAnalyticsResponse>(`/exams/${id}/analytics`),
  integrity: (id: string) => request<IntegrityFlagResponse[]>(`/exams/${id}/integrity`),
  /** Download the gradebook CSV through the authenticated client. */
  downloadGradebook: async (id: string, final: boolean) => {
    const res = await rawRequest(`/exams/${id}/gradebook.csv`, { query: { final } });
    const disposition = res.headers.get("content-disposition") ?? "";
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "gradebook.csv";
    return { blob: await res.blob(), filename: name };
  },
};

export const rubrics = {
  list: () => request<RubricSummary[]>("/rubrics"),
  get: (id: string) => request<RubricDetail>(`/rubrics/${id}`),
  update: (id: string, body: { name?: string; structured_data?: RubricSchemaInput }) =>
    request<RubricDetail>(`/rubrics/${id}`, { method: "PUT", json: body }),
};

export const professor = {
  dashboard: () => request<ProfessorDashboardResponse>("/professor/dashboard"),
  escalations: (query: { exam_id?: string; include_resolved?: boolean } = {}) =>
    request<EscalationResponse[]>("/professor/escalations", { query }),
  integrity: (query: { exam_id?: string; status?: IntegrityFlagStatus } = {}) =>
    request<IntegrityFlagResponse[]>("/professor/integrity", { query }),
  resolveFlag: (flagId: string, status: IntegrityFlagStatus, notes: string) =>
    request<IntegrityFlagResponse>(`/professor/integrity/${flagId}`, { method: "PATCH", json: { status, notes } }),
  submissions: (filters: QueueFilters) => request<ReviewQueueResponse>("/professor/submissions", { query: filters }),
};

export const ta = {
  dashboard: () => request<TADashboardResponse>("/ta/dashboard"),
  exams: () => request<TAExamResponse[]>("/ta/exams"),
  queue: (filters: QueueFilters) => request<ReviewQueueResponse>("/ta/reviews", { query: filters }),
  history: (query: { action?: string; limit?: number; offset?: number } = {}) =>
    request<ReviewHistoryResponse>("/ta/history", { query }),
};

export const review = {
  detail: (submissionId: string) => request<ReviewDetailResponse>(`/review/${submissionId}/detail`),
  act: (submissionId: string, body: ReviewActionRequest) =>
    request<SubmissionReviewResponse>(`/review/${submissionId}/action`, { json: body }),
  /** Authenticated image fetch → object URL (caller must revoke). */
  answerImage: async (submissionId: string, question: string | null, page: number | null) => {
    const res =
      question !== null
        ? await rawRequest(`/review/${submissionId}/answer-image`, { query: { question } })
        : await rawRequest(`/review/${submissionId}/pages/${page ?? 0}`);
    return {
      url: URL.createObjectURL(await res.blob()),
      page: Number(res.headers.get("x-page-index") ?? page ?? 0),
      cropped: res.headers.get("x-cropped") === "1",
    };
  },
};
