import { cx } from "./cx";

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className ?? "h-4 w-4")} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-surface-sunken", className ?? "h-4 w-full")} />;
}

export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx("space-y-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className="h-[88px] w-full rounded-lg" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-col items-center justify-center rounded-lg border border-dashed border-line px-6 py-10 text-center", className)}>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-fg-subtle">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm">
      <span className="text-rose-700 dark:text-rose-300">{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="text-xs font-medium text-rose-700 underline dark:text-rose-300">
          Try again
        </button>
      )}
    </div>
  );
}

const ALERT_TONES = {
  info: "border-sky-500/30 bg-sky-500/5 text-sky-800 dark:text-sky-200",
  success: "border-emerald-500/30 bg-emerald-500/5 text-emerald-800 dark:text-emerald-200",
  warning: "border-amber-500/30 bg-amber-500/5 text-amber-800 dark:text-amber-200",
  error: "border-rose-500/30 bg-rose-500/5 text-rose-800 dark:text-rose-200",
} as const;

export function Alert({
  tone = "info",
  children,
  onDismiss,
  className,
}: {
  tone?: keyof typeof ALERT_TONES;
  children: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
}) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm", ALERT_TONES[tone], className)}>
      <div className="min-w-0">{children}</div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="shrink-0 opacity-70 hover:opacity-100" aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}

export function ProgressBar({ value, max = 100, tone = "accent", label }: { value: number; max?: number; tone?: "accent" | "success" | "warning"; label?: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const bar = tone === "success" ? "bg-emerald-500" : tone === "warning" ? "bg-amber-500" : "bg-accent";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={cx("h-full rounded-full transition-all", bar)} style={{ width: `${pct}%` }} />
    </div>
  );
}
