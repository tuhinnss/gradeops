"use client";

import { useState } from "react";
import { CourseCard } from "@/components/professor/CourseCard";
import { CourseFormDialog } from "@/components/professor/CourseFormDialog";
import { Button, ButtonLink, ConfirmDialog, EmptyState, ErrorState, PageHeader, SegmentedTabs, SkeletonCards } from "@/components/ui";
import { courses } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";
import type { CourseResponse } from "@/lib/types";

export default function CoursesPage() {
  const [status, setStatus] = useState<"active" | "archived">("active");
  const list = useApi(() => courses.list(status), [status]);
  const [editing, setEditing] = useState<CourseResponse | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<CourseResponse | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggleArchive(c: CourseResponse) {
    setBusy(true);
    try {
      if (c.status === "active") await courses.archive(c.id);
      else await courses.update(c.id, { status: "active" });
      setArchiving(null);
      await list.reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Courses"
        subtitle="Courses you teach. Archived courses keep all grades and history."
        actions={
          <>
            <SegmentedTabs value={status} onChange={setStatus} options={[{ value: "active", label: "Active" }, { value: "archived", label: "Archived" }]} />
            <Button variant="primary" onClick={() => setEditing(null)}>
              New course
            </Button>
          </>
        }
      />
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <SkeletonCards count={3} />}
      {list.data && list.data.length === 0 && (
        <EmptyState
          title={status === "active" ? "No active courses" : "No archived courses"}
          description={status === "active" ? "Create a course to add students, TAs and exams." : undefined}
          action={status === "active" ? <Button variant="primary" onClick={() => setEditing(null)}>Create course</Button> : undefined}
        />
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {list.data?.map((c) => (
          <CourseCard
            key={c.id}
            course={c}
            actions={
              <>
                <ButtonLink href={`/professor/courses/${c.id}`} size="sm" variant="primary">
                  Open
                </ButtonLink>
                <Button size="sm" onClick={() => setEditing(c)}>
                  Manage
                </Button>
                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setArchiving(c)}>
                  {c.status === "active" ? "Archive" : "Unarchive"}
                </Button>
              </>
            }
          />
        ))}
      </div>
      <CourseFormDialog
        open={editing !== undefined}
        course={editing ?? undefined}
        onClose={() => setEditing(undefined)}
        onSaved={() => {
          setEditing(undefined);
          void list.reload();
        }}
      />
      <ConfirmDialog
        open={!!archiving}
        title={archiving?.status === "active" ? `Archive ${archiving?.course_code}?` : `Unarchive ${archiving?.course_code}?`}
        description={
          archiving?.status === "active"
            ? "TAs lose access and no new exams can be added. Grades, submissions and audit history are kept, and you can unarchive at any time."
            : "The course becomes active again and its TAs regain access."
        }
        confirmLabel={archiving?.status === "active" ? "Archive course" : "Unarchive"}
        tone={archiving?.status === "active" ? "danger" : "primary"}
        busy={busy}
        onClose={() => setArchiving(null)}
        onConfirm={() => archiving && void toggleArchive(archiving)}
      />
    </>
  );
}
