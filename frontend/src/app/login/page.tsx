"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login(email, password);
      setToken(res.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-grid flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-2xl border border-white/10 bg-zinc-950/80 p-8 shadow-xl"
      >
        <h1 className="text-xl font-semibold text-white">Sign in</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Auth is optional — enable <code className="text-zinc-400">AUTH_ENABLED</code> on the API.
        </p>
        {error && <p className="mt-4 text-sm text-rose-400">{error}</p>}
        <label className="mt-6 block text-xs text-zinc-500">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-white"
        />
        <label className="mt-4 block text-xs text-zinc-500">Password</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-white"
        />
        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-lg bg-sky-600 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="mt-4 text-center text-xs text-zinc-500">
          No account?{" "}
          <Link href="/signup" className="text-sky-400 hover:underline">
            Register
          </Link>
        </p>
        <Link href="/" className="mt-4 block text-center text-xs text-zinc-600 hover:text-zinc-400">
          ← Dashboard
        </Link>
      </form>
    </div>
  );
}
