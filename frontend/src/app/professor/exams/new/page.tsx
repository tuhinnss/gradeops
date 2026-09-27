"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ExamPipeline } from "@/components/professor/ExamPipeline";
import { ProcessingPanel } from "@/components/professor/ProcessingPanel";
import { RubricPanel } from "@/components/professor/RubricPanel";
import { UploadSubmissionsPanel } from "@/components/professor/UploadSubmissionsPanel";
import { Alert, Button, ButtonLink, Card, CardBody, CardHeader, cx, EmptyState, Input, Label, PageHeader, Select, SkeletonRows } from "@/components/ui";
import { courses, exams } from "@/lib/endpoints";
import { useApi } from "@/lib/hooks";

const STEPS = ["Exam details", "Rubric", "Answer sheets", "Start processing"];

function Stepper({ current }: { current: number }) {
  return (
    <ol className="mb-5 flex flex-wrap gap-2 text-xs">
      {STEPS.map((s, i) => (
        <li key={s} className={cx("flex items-center gap-2 rounded-full border px-3 py-1", i === current ? "border-accent bg-accent/10 font-semibold text-fg" : i < current ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-300" : "border-line text-fg-subtle")}>
          <span className="tabular">{i < current ? "✓" : i + 1}</span> {s}
        </li>
      ))}
    </ol>
  );
}

function DetailsStep({ onCreated }: { onCreated: (id: string) => void }) {
  const params = useSearchParams();
  const list = useApi(() => courses.list("active"), []);
  const [form, setForm] = useState({ course_id: params.get("course") ?? "", name: "", exam_type: "midterm", exam_date: "", total_marks: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const exam = await exams.create({
        course_id: form.course_id,
        name: form.name.trim(),
        exam_type: form.exam_type as "midterm",
        exam_date: form.exam_date || null,
        total_marks: form.total_marks ? Number(form.total_marks) : null,
        description: null,
        rubric_id: null,
      });
      onCreated(exam.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create exam");
      setBusy(false);
    }
  }

  if (list.data && list.data.length === 0) {
    return <EmptyState title="Create a course first" description="Exams belong to a course." action={<ButtonLink href="/professor/courses" variant="primary">Go to courses</ButtonLink>} />;
  }
  return (
    <Card>
      <CardHeader title="Exam details" />
      <form onSubmit={create} className="grid gap-4 p-4 sm:grid-cols-2">
        {error && <Alert tone="error" className="sm:col-span-2">{error}</Alert>}
        <div className="sm:col-span-2">
          <Label htmlFor="x-course">Course</Label>
          <Select id="x-course" required value={form.course_id} onChange={set("course_id")}>
            <option value="" disabled>
              Select a course…
            </option>
            {list.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.course_code} · {c.name} {c.semester ? `(${c.semester} ${c.academic_year ?? ""})` : ""}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="x-name">Exam name</Label>
          <Input id="x-name" required placeholder="Mid Semester Examination" value={form.name} onChange={set("name")} maxLength={255} />
        </div>
        <div>
          <Label htmlFor="x-type">Type</Label>
          <Select id="x-type" value={form.exam_type} onChange={set("exam_type")}>
            {["quiz", "midterm", "final", "assignment", "exam", "other"].map((t) => (
              <option key={t} value={t}>
                {t[0].toUpperCase() + t.slice(1)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="x-date">Date</Label>
          <Input id="x-date" type="date" value={form.exam_date} onChange={set("exam_date")} />
        </div>
        <div>
          <Label htmlFor="x-total">Maximum marks</Label>
          <Input id="x-total" type="number" min={0.5} step={0.5} placeholder="50" value={form.total_marks} onChange={set("total_marks")} />
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" variant="primary" loading={busy} disabled={!form.course_id || !form.name.trim()}>
            Create exam & continue
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Wizard() {
  const params = useSearchParams();
  const router = useRouter();
  const examId = params.get("exam");
  const step = examId ? Math.min(3, Math.max(1, Number(params.get("step") ?? 1))) : 0;
  const exam = useApi(() => (examId ? exams.get(examId) : Promise.resolve(null)), [examId, step]);
  const go = (id: string, s: number) => router.replace(`/professor/exams/new?exam=${id}&step=${s}`);

  return (
    <>
      <PageHeader title="New exam" subtitle={exam.data ? `${exam.data.course_code} · ${exam.data.name}` : "Set up an exam, its rubric and answer sheets, then start AI grading."} />
      <Stepper current={step} />
      {step === 0 && <DetailsStep onCreated={(id) => go(id, 1)} />}
      {step > 0 && !exam.data && <SkeletonRows rows={4} />}
      {step > 0 && exam.data && (
        <div className="space-y-4">
          {step === 1 && (
            <>
              <RubricPanel exam={exam.data} editable onChanged={(e) => exam.setData(e)} />
              <div className="flex justify-end">
                <Button variant="primary" disabled={!exam.data.rubric} onClick={() => go(exam.data!.id, 2)}>
                  Continue to answer sheets
                </Button>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <UploadSubmissionsPanel examId={exam.data.id} onUploaded={() => void exam.reload()} />
              <Card>
                <CardBody className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="text-fg-muted">
                    <b className="tabular text-fg">{exam.data.counts.submissions}</b> answer sheet(s) uploaded so far.
                  </span>
                  <div className="flex gap-2">
                    <Button onClick={() => go(exam.data!.id, 1)}>Back</Button>
                    <Button variant="primary" disabled={!exam.data.counts.submissions} onClick={() => go(exam.data!.id, 3)}>
                      Continue
                    </Button>
                  </div>
                </CardBody>
              </Card>
            </>
          )}
          {step === 3 && (
            <>
              <Card>
                <CardBody>
                  <ExamPipeline exam={exam.data} />
                </CardBody>
              </Card>
              <ProcessingPanel exam={exam.data} onChanged={() => void exam.reload()} />
              <div className="flex justify-end gap-2">
                <Button onClick={() => go(exam.data!.id, 2)}>Back</Button>
                <ButtonLink href={`/professor/exams/${exam.data.id}`} variant="primary">
                  Open exam dashboard
                </ButtonLink>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}

export default function NewExamPage() {
  return (
    <Suspense fallback={<SkeletonRows rows={4} />}>
      <Wizard />
    </Suspense>
  );
}
