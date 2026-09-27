import type { UserRole } from "./types";

/** Landing page for each role after login. */
export function homeForRole(role: UserRole): "/professor" | "/ta" {
  return role === "professor" ? "/professor" : "/ta";
}

/** Which role owns a route prefix (null = shared/public). */
export function roleForPath(pathname: string): UserRole | null {
  if (pathname === "/professor" || pathname.startsWith("/professor/")) return "professor";
  if (pathname === "/ta" || pathname.startsWith("/ta/")) return "ta";
  return null;
}

/**
 * Where a user may go after login. Only same-origin relative paths the role may
 * open are honoured (prevents open redirects and bouncing TAs into /professor).
 */
export function safeNextPath(next: string | null | undefined, role: UserRole): string {
  const home = homeForRole(role);
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return home;
  const owner = roleForPath(next.split("?")[0]);
  if (owner && owner !== role) return home;
  if (next.startsWith("/login") || next.startsWith("/signup")) return home;
  return next;
}

export const ROLE_LABEL: Record<UserRole, string> = { professor: "Professor", ta: "Teaching Assistant" };
