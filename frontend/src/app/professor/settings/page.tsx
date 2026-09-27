"use client";

import Link from "next/link";
import { AccountSettings } from "@/components/layout/AccountSettings";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui";
import { getApiBase } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function ProfessorSettingsPage() {
  const session = useSession();
  return (
    <>
      <PageHeader title="Settings" />
      <AccountSettings />
      <Card className="mt-4">
        <CardHeader title="Workspace" />
        <CardBody className="space-y-2 text-sm text-fg-muted">
          <p>
            API: <span className="font-mono text-fg">{getApiBase()}</span> · authentication {session.authEnabled === false ? "disabled (demo mode)" : "enabled"}
          </p>
          <p>
            The original single-upload grading tool is still available as the <Link href="/workbench" className="text-accent hover:underline">workbench</Link> for quick one-off grading outside a course.
          </p>
        </CardBody>
      </Card>
    </>
  );
}
