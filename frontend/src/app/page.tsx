"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { GradeOpsDashboard } from "@/components/GradeOpsDashboard";
import { Spinner } from "@/components/ui";
import { homeForRole } from "@/lib/roles";
import { useSession } from "@/lib/session";

/**
 * Entry point: signed-in users go to their role dashboard, others to /login.
 * With AUTH_ENABLED=false on the API (local demo mode) anonymous visitors get
 * the original single-upload workbench, exactly as before.
 */
export default function Home() {
  const session = useSession();
  const router = useRouter();
  const legacyDemo = session.status === "anonymous" && session.authEnabled === false;

  useEffect(() => {
    if (session.status === "authenticated") router.replace(homeForRole(session.user.role));
    else if (session.status === "anonymous" && !legacyDemo) router.replace("/login");
  }, [session.status, session.user, legacyDemo, router]);

  if (legacyDemo) {
    return (
      <div className="legacy-dark">
        <GradeOpsDashboard />
      </div>
    );
  }
  return (
    <div className="grid min-h-screen place-items-center text-fg-muted" aria-busy="true">
      <Spinner className="h-6 w-6" />
    </div>
  );
}
