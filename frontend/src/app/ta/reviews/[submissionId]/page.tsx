"use client";

import { useParams } from "next/navigation";
import { ReviewWorkspace } from "@/components/grading/ReviewWorkspace";

export default function TAReviewPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  return <ReviewWorkspace submissionId={submissionId} basePath="/ta/reviews" backHref="/ta/reviews" backLabel="Review queue" />;
}
