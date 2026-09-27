"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Input, Label, Modal, Textarea } from "@/components/ui";
import { courses } from "@/lib/endpoints";
import type { CourseResponse } from "@/lib/types";

export function CourseFormDialog({ open, course, onClose, onSaved }: { open: boolean; course?: CourseResponse; onClose: () => void; onSaved: (c: CourseResponse) => void }) {
  const [form, setForm] = useState({ name: "", course_code: "", semester: "", academic_year: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm({
      name: course?.name ?? "",
      course_code: course?.course_code ?? "",
      semester: course?.semester ?? "",
      academic_year: course?.academic_year ?? "",
      description: course?.description ?? "",
    });
  }, [open, course]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: form.name.trim(),
        course_code: form.course_code.trim(),
        semester: form.semester.trim() || null,
        academic_year: form.academic_year.trim() || null,
        description: form.description.trim() || null,
      };
      onSaved(course ? await courses.update(course.id, body) : await courses.create(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save course");
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={course ? "Edit course" : "Create course"}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" loading={busy} disabled={!form.name.trim() || !form.course_code.trim()} onClick={() => void save()}>
            {course ? "Save changes" : "Create course"}
          </Button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {error && <Alert tone="error" className="sm:col-span-2">{error}</Alert>}
        <div>
          <Label htmlFor="c-code">Course code</Label>
          <Input id="c-code" placeholder="CS3001" value={form.course_code} onChange={set("course_code")} maxLength={32} />
        </div>
        <div>
          <Label htmlFor="c-name">Course name</Label>
          <Input id="c-name" placeholder="Data Structures" value={form.name} onChange={set("name")} maxLength={255} />
        </div>
        <div>
          <Label htmlFor="c-sem">Semester</Label>
          <Input id="c-sem" placeholder="Autumn" value={form.semester} onChange={set("semester")} maxLength={64} />
        </div>
        <div>
          <Label htmlFor="c-year">Academic year</Label>
          <Input id="c-year" placeholder="2026-27" value={form.academic_year} onChange={set("academic_year")} maxLength={16} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="c-desc" hint="(optional)">Description</Label>
          <Textarea id="c-desc" rows={3} value={form.description} onChange={set("description")} />
        </div>
      </div>
    </Modal>
  );
}
