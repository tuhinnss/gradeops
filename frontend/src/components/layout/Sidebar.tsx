"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/components/ui";
import { Icon } from "./Icon";
import { isActive, type NavItem } from "./nav";

export function Sidebar({ items, badges, onNavigate }: { items: NavItem[]; badges?: Record<string, number>; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2 border-b border-line px-4">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-xs font-bold text-white">G</span>
        <span className="text-sm font-semibold tracking-[0.18em] text-fg">GRADEOPS</span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2" aria-label="Main">
        {items.map((item) => {
          const active = isActive(pathname, item);
          const badge = badges?.[item.href];
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cx(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition",
                active ? "bg-accent/10 font-medium text-accent-strong dark:text-accent-strong" : "text-fg-muted hover:bg-surface-raised hover:text-fg",
              )}
            >
              <Icon name={item.icon} className="h-4 w-4 shrink-0" />
              <span className="truncate">{item.label}</span>
              {badge ? <span className="tabular ml-auto rounded-full bg-rose-500/15 px-1.5 text-[11px] font-semibold text-rose-600 dark:text-rose-300">{badge}</span> : null}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
