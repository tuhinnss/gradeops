"use client";

import Link from "next/link";
import { Badge } from "@/components/ui";
import { ROLE_LABEL } from "@/lib/roles";
import { useSession } from "@/lib/session";
import { Icon } from "./Icon";
import { ThemeToggle } from "./ThemeToggle";

export type Notice = { href: string; label: string; count: number };

export function Topbar({ onMenu, notices }: { onMenu: () => void; notices: Notice[] }) {
  const session = useSession();
  const user = session.user;
  const total = notices.reduce((n, x) => n + x.count, 0);
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur">
      <button type="button" onClick={onMenu} className="rounded-md p-2 text-fg-muted hover:bg-surface-raised lg:hidden" aria-label="Open navigation">
        <Icon name="menu" />
      </button>
      <div className="ml-auto flex items-center gap-1">
        <details className="relative">
          <summary className="relative list-none rounded-md p-2 text-fg-muted hover:bg-surface-raised hover:text-fg [&::-webkit-details-marker]:hidden" aria-label={`Notifications (${total})`}>
            <Icon name="bell" />
            {total > 0 && <span className="tabular absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-rose-600 px-1 text-center text-[10px] font-semibold leading-[18px] text-white">{total > 99 ? "99+" : total}</span>}
          </summary>
          <div className="absolute right-0 mt-2 w-64 rounded-lg border border-line bg-surface p-1 shadow-lg">
            {notices.filter((n) => n.count > 0).length === 0 ? (
              <p className="px-3 py-2 text-sm text-fg-subtle">Nothing needs your attention.</p>
            ) : (
              notices
                .filter((n) => n.count > 0)
                .map((n) => (
                  <Link key={n.href} href={n.href} className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-fg hover:bg-surface-raised">
                    {n.label}
                    <span className="tabular text-xs font-semibold text-fg-muted">{n.count}</span>
                  </Link>
                ))
            )}
          </div>
        </details>
        <ThemeToggle />
        {user && (
          <div className="ml-2 hidden items-center gap-2 border-l border-line pl-3 sm:flex">
            <div className="text-right leading-tight">
              <div className="text-sm font-medium text-fg">{user.full_name || user.email}</div>
              <div className="text-[11px] text-fg-subtle">{user.email}</div>
            </div>
            <Badge tone={user.role === "professor" ? "violet" : "info"}>{ROLE_LABEL[user.role]}</Badge>
          </div>
        )}
        <button type="button" onClick={session.logout} className="ml-1 rounded-md p-2 text-fg-muted hover:bg-surface-raised hover:text-fg" aria-label="Sign out" title="Sign out">
          <Icon name="logout" />
        </button>
      </div>
    </header>
  );
}
