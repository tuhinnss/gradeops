"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ReviewWorkspace } from "@/components/grading/ReviewWorkspace";

function ProfessorReview() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const action = useSearchParams().get("action") === "override" ? "override" : null;
  return (
    <ReviewWorkspace
      submissionId={submissionId}
      basePath="/professor/reviews"
      backHref="/professor/submissions"
      backLabel="Submissions"
      initialAction={action}
    />
  );
}

export default function ProfessorReviewPage() {
  return (
    <Suspense>
      <ProfessorReview />
    </Suspense>
  );
}
