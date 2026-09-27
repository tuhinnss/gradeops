"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard } from "@/components/layout/AuthCard";
import { Alert, Button, Input, Label } from "@/components/ui";
import { setToken } from "@/lib/auth";
import { request } from "@/lib/client";
import { useSession } from "@/lib/session";
import type { TokenResponse } from "@/lib/types";

export default function SignupPage() {
  const router = useRouter();
  const session = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await request<TokenResponse>("/auth/register", {
        json: { email, password, full_name: fullName },
      });
      setToken(res.access_token);
      await session.refresh();
      router.replace("/ta");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Create a TA account"
      subtitle="You will see courses once a professor adds you. Professor accounts are created by an administrator."
    >
      <form onSubmit={onSubmit} className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <div>
          <Label htmlFor="name">Full name</Label>
          <Input id="name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="password" hint="(min 8 characters)">Password</Label>
          <Input id="password" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <Button type="submit" variant="primary" loading={busy} className="w-full" disabled={!email || password.length < 8}>
          Create account
        </Button>
        <p className="text-center text-xs text-fg-subtle">
          Already registered?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
