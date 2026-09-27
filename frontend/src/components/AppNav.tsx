"use client";

import Link from "next/link";
import { homeForRole } from "@/lib/roles";
import { useSession } from "@/lib/session";

/** Navigation for the legacy workbench pages. */
export function AppNav() {
  const session = useSession();
  return (
    <nav className="flex flex-wrap gap-3 text-sm">
      {session.status === "authenticated" && (
        <Link href={homeForRole(session.user.role)} className="text-zinc-400 transition hover:text-white">
          ← Dashboard
        </Link>
      )}
      <Link href="/workbench" className="text-zinc-400 transition hover:text-white">
        Workbench
      </Link>
      <Link href="/analytics" className="text-zinc-400 transition hover:text-white">
        Rubric analytics
      </Link>
      {session.status !== "authenticated" && (
        <Link href="/login" className="text-zinc-400 transition hover:text-white">
          Sign in
        </Link>
      )}
    </nav>
  );
}
