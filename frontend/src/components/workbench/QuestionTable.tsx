import type { QuestionResult } from "@/lib/api";

export function QuestionTable({ results }: { results: QuestionResult[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-zinc-500">
            <th className="py-2 pr-4">Question</th>
            <th className="py-2 pr-4">Marks</th>
            <th className="py-2 pr-4">Confidence</th>
            <th className="py-2">Remark / justification</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.question} className="border-b border-white/5 align-top text-zinc-200">
              <td className="py-3 pr-4 font-mono text-sky-300">
                {r.question}
                {r.is_blank && <span className="ml-2 rounded bg-rose-500/20 px-1.5 text-[10px] text-rose-300">blank</span>}
              </td>
              <td className="whitespace-nowrap py-3 pr-4">
                <span className="font-semibold text-white">{r.marks_awarded}</span>
                <span className="text-zinc-500"> / {r.max_marks}</span>
              </td>
              <td className="py-3 pr-4 text-zinc-400">{(r.confidence * 100).toFixed(0)}%</td>
              <td className="py-3 text-xs leading-relaxed text-zinc-400">{r.justification}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
