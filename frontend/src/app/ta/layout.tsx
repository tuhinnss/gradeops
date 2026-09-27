"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import type { Notice } from "@/components/layout/Topbar";
import { ta } from "@/lib/endpoints";
import { useInterval } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function TALayout({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const [notices, setNotices] = useState<Notice[]>([]);
  const isTA = session.status === "authenticated" && session.user.role === "ta";

  const load = useCallback(async () => {
    try {
      const d = await ta.dashboard();
      setNotices([{ href: "/ta/reviews", label: "Submissions awaiting your review", count: d.pending_reviews }]);
    } catch {
      /* the page itself reports errors */
    }
  }, []);
  const pathname = usePathname();
  // Refresh counts on navigation (e.g. after resolving an escalation) and every minute.
  useEffect(() => {
    if (isTA) void load();
  }, [isTA, load, pathname]);
  useInterval(load, 60_000, isTA);

  return (
    <AppShell role="ta" notices={notices} badges={{ "/ta/reviews": notices[0]?.count ?? 0 }}>
      {children}
    </AppShell>
  );
}
