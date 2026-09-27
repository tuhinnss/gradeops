"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthCard } from "@/components/layout/AuthCard";
import { Alert, Button, Input, Label } from "@/components/ui";
import { safeNextPath } from "@/lib/roles";
import { useSession } from "@/lib/session";

function LoginForm() {
  const session = useSession();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Signed in (already, or just now via the form): go to the requested page if
  // this role may open it, otherwise to the role's dashboard.
  useEffect(() => {
    if (session.status === "authenticated") router.replace(safeNextPath(next, session.user.role));
  }, [session.status, session.user, next, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await session.login(email, password); // the effect above performs the redirect
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Sign in" subtitle="Professors and teaching assistants sign in with their university account.">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error && <Alert tone="error">{error}</Alert>}
        {session.authEnabled === false && (
          <Alert tone="info">
            The API is in local demo mode. The single-upload workbench is available <Link href="/" className="underline">without signing in</Link>.
          </Alert>
        )}
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <Button type="submit" variant="primary" loading={busy} className="w-full" disabled={!email || !password}>
          Sign in
        </Button>
        <p className="text-center text-xs text-fg-subtle">
          Teaching assistant without an account?{" "}
          <Link href="/signup" className="text-accent hover:underline">
            Register
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
