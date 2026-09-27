import Link from "next/link";
import { forwardRef } from "react";
import { cx } from "./cx";
import { Spinner } from "./Feedback";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong border border-transparent",
  secondary: "bg-surface text-fg border border-line hover:bg-surface-raised",
  ghost: "text-fg-muted hover:text-fg hover:bg-surface-raised border border-transparent",
  danger: "bg-rose-600 text-white hover:bg-rose-500 border border-transparent",
  success: "bg-emerald-600 text-white hover:bg-emerald-500 border border-transparent",
};
const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-9 px-4 text-sm gap-2",
};
const BASE =
  "inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:opacity-50 disabled:pointer-events-none";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cx(BASE, VARIANTS[variant], SIZES[size], className)}
      {...rest}
    >
      {loading && <Spinner className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
});

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className={cx(BASE, VARIANTS[variant], SIZES[size], className)}>
      {children}
    </Link>
  );
}
