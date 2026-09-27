import { forwardRef } from "react";
import { cx } from "./cx";

const CONTROL =
  "rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60";

/** Full width unless the caller sets its own width (w-*), which must win. */
function control(extra: string, className?: string) {
  return cx(CONTROL, extra, /(^|\s)w-/.test(className ?? "") ? "" : "w-full", className);
}

export function Label({ htmlFor, children, hint }: { htmlFor?: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-fg-muted">
      {children}
      {hint && <span className="ml-1 font-normal text-fg-subtle">{hint}</span>}
    </label>
  );
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={control("h-9 py-0", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} className={control("h-9 py-0", className)} {...rest}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={control("", className)} {...rest} />;
});

export function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{children}</p>;
}
