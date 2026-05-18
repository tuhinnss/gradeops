"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppNav } from "@/components/AppNav";
import { getPlagiarismReport, getRubricAnalytics, type AnalyticsData } from "@/lib/api";

const STORAGE_KEY = "gradeops:dashboard:v1";

export default function AnalyticsPage() {
  const [rubricId, setRubricId] = useState<string | null>(null);
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [plagiarism, setPlagiarism] = useState<{ flags: { note: string; similarity: number }[] }>({
    flags: [],
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const p = JSON.parse(raw) as { rubricId?: string | null };
        if (p.rubricId) setRubricId(p.rubricId);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!rubricId) return;
    (async () => {
      try {
        const [a, p] = await Promise.all([
          getRubricAnalytics(rubricId),
          getPlagiarismReport(rubricId),
        ]);
        setData(a);
        setPlagiarism(p as { flags: { note: string; similarity: number }[] });
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analytics");
      }
    })();
  }, [rubricId]);

  const qChart = data
    ? Object.entries(data.question_averages).map(([question, avg]) => ({ question, avg }))
    : [];

  const passFail = data
    ? [
        { name: "Pass", value: data.pass_fail.pass, color: "#34d399" },
        { name: "Fail", value: data.pass_fail.fail, color: "#f87171" },
      ]
    : [];

  return (
    <div className="bg-grid min-h-screen">
      <header className="border-b border-white/10 bg-black/40 px-4 py-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-sky-400">Analytics</p>
            <h1 className="text-2xl font-semibold text-white">Cohort insights</h1>
          </div>
          <AppNav />
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-4 py-8">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-zinc-500">
            Rubric ID
            <input
              value={rubricId ?? ""}
              onChange={(e) => setRubricId(e.target.value || null)}
              className="mt-1 block w-72 rounded border border-white/10 bg-black/50 px-2 py-1.5 font-mono text-sm text-white"
              placeholder="From dashboard after rubric upload"
            />
          </label>
          <Link href="/" className="text-sm text-sky-400 hover:underline">
            ← Dashboard
          </Link>
        </div>

        {error && (
          <p className="rounded border border-rose-500/40 bg-rose-950/30 px-4 py-2 text-sm text-rose-100">
            {error}
          </p>
        )}

        {!rubricId && (
          <p className="text-sm text-zinc-500">Upload a rubric on the dashboard to auto-fill the ID.</p>
        )}

        {data && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Evaluated" value={String(data.evaluated_count)} />
              <Stat label="Average" value={`${data.average_marks} / ${data.max_total}`} />
              <Stat label="Hardest Q" value={data.hardest_question ?? "—"} />
              <Stat label="Pending review" value={String(data.review_pending ?? 0)} />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <ChartCard title="Question averages">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={qChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="question" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
                    <Bar dataKey="avg" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Pass / fail (40% threshold)">
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={passFail} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                      {passFail.map((e) => (
                        <Cell key={e.name} fill={e.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            <ChartCard title="Top performers">
              <ul className="space-y-2 text-sm">
                {data.toppers.map((t, i) => (
                  <li key={t.student_id} className="flex justify-between text-zinc-300">
                    <span>
                      #{i + 1} {t.student_id}
                    </span>
                    <span className="font-mono text-emerald-300">{t.total}</span>
                  </li>
                ))}
              </ul>
            </ChartCard>

            {plagiarism.flags?.length > 0 && (
              <ChartCard title="Suspicious similarity flags">
                <ul className="space-y-1 text-xs text-amber-100">
                  {plagiarism.flags.map((f, i) => (
                    <li key={i}>
                      {f.note} ({(f.similarity * 100).toFixed(0)}%)
                    </li>
                  ))}
                </ul>
              </ChartCard>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-zinc-950/60 p-4">
      <p className="text-xs uppercase text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-white">{value}</p>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-white/10 bg-zinc-950/60 p-4">
      <h2 className="mb-4 text-sm font-semibold text-zinc-300">{title}</h2>
      {children}
    </section>
  );
}
