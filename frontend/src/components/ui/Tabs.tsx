"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./cx";

export type TabItem = { href: string; label: string; exact?: boolean; count?: number };

export function RouteTabs({ items }: { items: TabItem[] }) {
  const pathname = usePathname();
  return (
    <nav className="-mb-px flex gap-1 overflow-x-auto border-b border-line" aria-label="Sections">
      {items.map((item) => {
        const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "whitespace-nowrap border-b-2 px-3 py-2 text-sm transition",
              active ? "border-accent font-medium text-fg" : "border-transparent text-fg-muted hover:text-fg",
            )}
          >
            {item.label}
            {item.count !== undefined && <span className="ml-1.5 rounded-full bg-surface-sunken px-1.5 text-[11px] text-fg-muted">{item.count}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

export function SegmentedTabs<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label?: string }) {
  return (
    <div className="inline-flex rounded-md border border-line bg-surface-raised p-0.5" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          type="button"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx("rounded px-3 py-1 text-xs font-medium transition", o.value === value ? "bg-surface text-fg shadow-sm" : "text-fg-muted hover:text-fg")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
