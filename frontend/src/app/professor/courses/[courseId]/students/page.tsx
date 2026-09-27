"use client";

import { useCourse } from "@/components/professor/CourseContext";
import { StudentRoster } from "@/components/professor/StudentRoster";

export default function CourseStudentsPage() {
  const { course, reload } = useCourse();
  return <StudentRoster courseId={course.id} archived={course.status === "archived"} onChanged={() => void reload()} />;
}
