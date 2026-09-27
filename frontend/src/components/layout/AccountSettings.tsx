"use client";

import { useState } from "react";
import { Alert, Button, Card, CardBody, CardHeader, Input, Label } from "@/components/ui";
import { request } from "@/lib/client";
import { ROLE_LABEL } from "@/lib/roles";
import { useSession } from "@/lib/session";

export function AccountSettings() {
  const { user } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (next !== confirm) return setResult({ tone: "error", text: "New passwords do not match" });
    setBusy(true);
    setResult(null);
    try {
      await request<void>("/auth/change-password", { json: { current_password: current, new_password: next } });
      setResult({ tone: "success", text: "Password updated." });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setResult({ tone: "error", text: err instanceof Error ? err.message : "Could not update password" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Account" />
        <CardBody>
          <dl className="grid grid-cols-3 gap-y-2 text-sm">
            <dt className="text-fg-subtle">Name</dt>
            <dd className="col-span-2 text-fg">{user?.full_name || "—"}</dd>
            <dt className="text-fg-subtle">Email</dt>
            <dd className="col-span-2 text-fg">{user?.email}</dd>
            <dt className="text-fg-subtle">Role</dt>
            <dd className="col-span-2 text-fg">{user ? ROLE_LABEL[user.role] : "—"}</dd>
          </dl>
          <p className="mt-4 text-xs text-fg-subtle">Roles are assigned by administrators and cannot be changed here.</p>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Change password" />
        <CardBody>
          <form onSubmit={onSubmit} className="space-y-3">
            {result && <Alert tone={result.tone}>{result.text}</Alert>}
            <div>
              <Label htmlFor="pw-current">Current password</Label>
              <Input id="pw-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
            </div>
            <div>
              <Label htmlFor="pw-new" hint="(min 8 characters)">New password</Label>
              <Input id="pw-new" type="password" autoComplete="new-password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required />
            </div>
            <div>
              <Label htmlFor="pw-confirm">Confirm new password</Label>
              <Input id="pw-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </div>
            <Button type="submit" variant="primary" loading={busy} disabled={!current || next.length < 8}>
              Update password
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
