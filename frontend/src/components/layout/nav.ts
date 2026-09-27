import type { IconName } from "./Icon";
import type { UserRole } from "@/lib/types";

export type NavItem = { href: string; label: string; icon: IconName; exact?: boolean };

export const PROFESSOR_NAV: NavItem[] = [
  { href: "/professor", label: "Overview", icon: "home", exact: true },
  { href: "/professor/courses", label: "Courses", icon: "book" },
  { href: "/professor/exams", label: "Exams", icon: "clipboard" },
  { href: "/professor/rubrics", label: "Rubrics", icon: "list" },
  { href: "/professor/submissions", label: "Submissions", icon: "file" },
  { href: "/professor/tas", label: "TA Management", icon: "users" },
  { href: "/professor/reviews/escalated", label: "Review & Escalations", icon: "flag" },
  { href: "/professor/analytics", label: "Analytics", icon: "chart" },
  { href: "/professor/integrity", label: "Integrity", icon: "shield" },
  { href: "/professor/gradebook", label: "Gradebook", icon: "table" },
  { href: "/professor/settings", label: "Settings", icon: "gear" },
];

export const TA_NAV: NavItem[] = [
  { href: "/ta", label: "Overview", icon: "home", exact: true },
  { href: "/ta/reviews", label: "Review Queue", icon: "inbox" },
  { href: "/ta/exams", label: "My Exams", icon: "clipboard" },
  { href: "/ta/escalations", label: "Escalations", icon: "flag" },
  { href: "/ta/history", label: "Review History", icon: "history" },
  { href: "/ta/settings", label: "Settings", icon: "gear" },
];

export function navForRole(role: UserRole): NavItem[] {
  return role === "professor" ? PROFESSOR_NAV : TA_NAV;
}

export function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
