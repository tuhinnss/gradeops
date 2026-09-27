"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import type { Notice } from "@/components/layout/Topbar";
import { professor } from "@/lib/endpoints";
import { useInterval } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export default function ProfessorLayout({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const [notices, setNotices] = useState<Notice[]>([]);
  const isProfessor = session.status === "authenticated" && session.user.role === "professor";

  const load = useCallback(async () => {
    try {
      const d = await professor.dashboard();
      setNotices([
        { href: "/professor/reviews/escalated", label: "Escalations to resolve", count: d.escalated },
        { href: "/professor/integrity", label: "Similarity flags to review", count: d.integrity_flags_open },
        { href: "/professor/submissions?status=reviewed", label: "TA-reviewed, awaiting your approval", count: d.awaiting_professor_approval },
      ]);
    } catch {
      /* the page itself reports errors */
    }
  }, []);
  const pathname = usePathname();
  // Refresh counts on navigation (e.g. after resolving an escalation) and every minute.
  useEffect(() => {
    if (isProfessor) void load();
  }, [isProfessor, load, pathname]);
  useInterval(load, 60_000, isProfessor);

  const badges = {
    "/professor/reviews/escalated": notices[0]?.count ?? 0,
    "/professor/integrity": notices[1]?.count ?? 0,
  };
  return (
    <AppShell role="professor" notices={notices} badges={badges}>
      {children}
    </AppShell>
  );
}
