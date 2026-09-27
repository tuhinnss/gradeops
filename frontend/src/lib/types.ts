/**
 * Frontend types for the GradeOps API.
 *
 * Generated from the backend's Pydantic schemas: `api-schema.ts` is produced by
 * `npm run gen:api` from `openapi.json` (exported with `python -m scripts.export_openapi`).
 * Never hand-edit shapes here — re-export them so they stay in sync.
 */
import type { components } from "./api-schema";

type S = components["schemas"];

export type UserRole = S["UserRole"];
export type ReviewStatus = S["ReviewStatus"];
export type ExamStatus = S["ExamStatus"];
export type SubmissionStatus = S["SubmissionStatus"];
export type CourseStatus = S["CourseStatus"];
export type IntegrityFlagStatus = S["IntegrityFlagStatus"];

export type UserResponse = S["UserResponse"];
export type UserSummary = S["UserSummary"];
export type TokenResponse = S["TokenResponse"];
export type AuthStatusResponse = S["AuthStatusResponse"];

export type CourseResponse = S["CourseResponse"];
export type CourseCreate = S["CourseCreate"];
export type CourseUpdate = S["CourseUpdate"];
export type StudentResponse = S["StudentResponse"];
export type StudentIn = S["StudentIn"];
export type StudentImportResponse = S["StudentImportResponse"];
export type TAWorkload = S["TAWorkload"];
export type TAAddRequest = S["TAAddRequest"];

export type ExamResponse = S["ExamResponse"];
export type ExamDetailResponse = S["ExamDetailResponse"];
export type TAExamResponse = S["TAExamResponse"];
export type ExamCreate = S["ExamCreate"];
export type ExamUpdate = S["ExamUpdate"];
export type ExamCounts = S["ExamCounts"];
export type ExamAuditItem = S["ExamAuditItem"];
export type ExamStage = ExamResponse["stage"];
export type RubricSummary = S["RubricSummary"];
export type RubricDetail = S["RubricDetail"];
export type RubricSchema = S["RubricSchema-Output"];
export type RubricSchemaInput = S["RubricSchema-Input"];
export type BatchJobResponse = S["BatchJobResponse"];
export type SubmissionRow = S["SubmissionRow"];
export type SubmissionListResponse = S["SubmissionListResponse"];
export type MappingValidateResponse = S["MappingValidateResponse"];
export type MappingItemResult = S["MappingItemResult"];
export type SubmissionUploadResponse = S["SubmissionUploadResponse"];
export type DistributeResponse = S["DistributeResponse"];
export type FinalizationSummary = S["FinalizationSummary"];

export type GradebookResponse = S["GradebookResponse"];
export type GradebookRow = S["GradebookRow"];
export type ExamAnalyticsResponse = S["ExamAnalyticsResponse"];
export type CourseAnalyticsResponse = S["CourseAnalyticsResponse"];
export type QuestionStats = S["QuestionStats"];
export type ScoreSummary = S["ScoreSummary"];
export type IntegrityFlagResponse = S["IntegrityFlagResponse"];

export type ProfessorDashboardResponse = S["ProfessorDashboardResponse"];
export type TADashboardResponse = S["TADashboardResponse"];
export type ActivityItem = S["ActivityItem"];
export type EscalationResponse = S["EscalationResponse"];

export type ReviewQueueResponse = S["ReviewQueueResponse"];
export type ReviewQueueItem = S["ReviewQueueItem"];
export type ReviewDetailResponse = S["ReviewDetailResponse"];
export type ReviewQuestion = S["ReviewQuestion"];
export type ReviewPermissions = S["ReviewPermissions"];
export type ReviewAuditItem = S["ReviewAuditItem"];
export type CriterionScore = S["CriterionScore"];
export type SubmissionReviewResponse = S["SubmissionReviewResponse"];
export type ReviewActionRequest = S["ReviewActionRequest"];
export type QuestionOverride = S["QuestionOverride"];
export type ReviewHistoryResponse = S["ReviewHistoryResponse"];
export type ReviewHistoryItem = S["ReviewHistoryItem"];

/** Escalation reason codes accepted by POST /review/{id}/action. */
export const ESCALATION_REASONS = [
  { value: "ambiguous_answer", label: "Ambiguous answer" },
  { value: "ocr_unreliable", label: "OCR unreliable" },
  { value: "rubric_unclear", label: "Rubric unclear" },
  { value: "integrity_concern", label: "Potential integrity issue" },
  { value: "ai_grading_incorrect", label: "AI grading appears incorrect" },
  { value: "other", label: "Other" },
] as const;
export type EscalationReason = (typeof ESCALATION_REASONS)[number]["value"];
