import Link from "next/link";
import type { Tone } from "@/lib/format";
import { cx } from "./cx";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <section className={cx("rounded-lg border border-line bg-surface", className)}>{children}</section>;
}

export function CardHeader({ title, description, actions }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-fg-subtle">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cx("p-4", className)}>{children}</div>;
}

const STAT_ACCENT: Record<Tone, string> = {
  neutral: "",
  info: "text-sky-700 dark:text-sky-300",
  success: "text-emerald-700 dark:text-emerald-300",
  warning: "text-amber-700 dark:text-amber-300",
  danger: "text-rose-700 dark:text-rose-300",
  violet: "text-violet-700 dark:text-violet-300",
};

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
  href,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: Tone;
  href?: string;
}) {
  const body = (
    <>
      <p className="text-xs font-medium text-fg-subtle">{label}</p>
      <p className={cx("tabular mt-1 text-2xl font-semibold text-fg", STAT_ACCENT[tone])}>{value}</p>
      {hint && <p className="mt-0.5 truncate text-xs text-fg-subtle">{hint}</p>}
    </>
  );
  const cls = "block rounded-lg border border-line bg-surface px-4 py-3";
  return href ? (
    <Link href={href} className={cx(cls, "transition hover:border-line-strong hover:bg-surface-raised")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function PageHeader({
  title,
  subtitle,
  eyebrow,
  actions,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  eyebrow?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium text-fg-subtle">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-fg-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
