import type { Tone } from "@/lib/format";
import { cx } from "./cx";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-fg-muted ring-line",
  info: "bg-sky-500/10 text-sky-700 ring-sky-500/25 dark:text-sky-300",
  success: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/25 dark:text-emerald-300",
  warning: "bg-amber-500/10 text-amber-800 ring-amber-500/30 dark:text-amber-300",
  danger: "bg-rose-500/10 text-rose-700 ring-rose-500/25 dark:text-rose-300",
  violet: "bg-violet-500/10 text-violet-700 ring-violet-500/25 dark:text-violet-300",
};

export function Badge({ tone = "neutral", children, className, title }: { tone?: Tone; children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", TONES[tone], className)}>
      {children}
    </span>
  );
}
