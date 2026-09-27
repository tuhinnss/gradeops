"use client";

import { GradeOpsDashboard } from "@/components/GradeOpsDashboard";
import { RoleGuard } from "@/components/layout/RoleGuard";
import { useSession } from "@/lib/session";

/** Legacy single-upload workbench: professors only (open to all in API demo mode). */
export default function WorkbenchPage() {
  const session = useSession();
  const page = (
    <div className="legacy-dark">
      <GradeOpsDashboard />
    </div>
  );
  if (session.status === "anonymous" && session.authEnabled === false) return page;
  return <RoleGuard role="professor">{page}</RoleGuard>;
}
