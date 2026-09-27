"use client";

import { useCourse } from "@/components/professor/CourseContext";
import { TAWorkloadTable } from "@/components/professor/TAWorkloadTable";

export default function CourseTAsPage() {
  const { course, reload } = useCourse();
  return <TAWorkloadTable courseId={course.id} archived={course.status === "archived"} onChanged={() => void reload()} />;
}
