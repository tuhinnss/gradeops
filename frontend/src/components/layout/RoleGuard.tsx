"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ButtonLink, Spinner } from "@/components/ui";
import { homeForRole, ROLE_LABEL } from "@/lib/roles";
import { useSession } from "@/lib/session";
import type { UserRole } from "@/lib/types";

/**
 * Client-side route guard for role dashboards. This only shapes navigation —
 * every API call is authorised by the backend independently.
 */
export function RoleGuard({ role, children }: { role: UserRole; children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const wrongRole = session.status === "authenticated" && session.user.role !== role;

  useEffect(() => {
    if (session.status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (wrongRole) {
      const t = setTimeout(() => router.replace(homeForRole(session.user!.role)), 2500);
      return () => clearTimeout(t);
    }
  }, [session.status, wrongRole, pathname, router, session.user]);

  if (session.status !== "authenticated") {
    return (
      <div className="grid min-h-screen place-items-center text-fg-muted" aria-busy="true">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (wrongRole) {
    const home = homeForRole(session.user.role);
    return (
      <div className="grid min-h-screen place-items-center px-4">
        <div className="max-w-sm text-center" role="alert">
          <p className="text-sm font-semibold text-rose-600 dark:text-rose-400">403 — Not permitted</p>
          <h1 className="mt-2 text-lg font-semibold text-fg">This area is for {ROLE_LABEL[role]}s</h1>
          <p className="mt-1 text-sm text-fg-muted">You are signed in as a {ROLE_LABEL[session.user.role]}. Redirecting you to your dashboard…</p>
          <ButtonLink href={home} variant="primary" className="mt-4">
            Go to my dashboard
          </ButtonLink>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
