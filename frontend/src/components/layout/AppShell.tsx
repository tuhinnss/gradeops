"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cx } from "@/components/ui";
import { RoleGuard } from "./RoleGuard";
import { Sidebar } from "./Sidebar";
import { Topbar, type Notice } from "./Topbar";
import { navForRole } from "./nav";
import type { UserRole } from "@/lib/types";

export function AppShell({
  role,
  notices = [],
  badges,
  children,
}: {
  role: UserRole;
  notices?: Notice[];
  badges?: Record<string, number>;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => setOpen(false), [pathname]);
  const items = navForRole(role);
  return (
    <RoleGuard role={role}>
      <div className="min-h-screen lg:pl-60">
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 border-r border-line bg-surface lg:block">
          <Sidebar items={items} badges={badges} />
        </aside>
        <div className={cx("fixed inset-0 z-50 lg:hidden", open ? "block" : "hidden")}>
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-line bg-surface">
            <Sidebar items={items} badges={badges} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
        <Topbar onMenu={() => setOpen(true)} notices={notices} />
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
      </div>
    </RoleGuard>
  );
}
