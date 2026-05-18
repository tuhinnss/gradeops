"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { register } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
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
      const res = await register(email, password, fullName, "ta");
      setToken(res.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
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
        <h1 className="text-xl font-semibold text-white">Create account</h1>
        <p className="mt-1 text-sm text-zinc-500">First registered user becomes instructor.</p>
        {error && <p className="mt-4 text-sm text-rose-400">{error}</p>}
        <label className="mt-6 block text-xs text-zinc-500">Full name</label>
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-white"
        />
        <label className="mt-4 block text-xs text-zinc-500">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-white"
        />
        <label className="mt-4 block text-xs text-zinc-500">Password (min 8)</label>
        <input
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-white"
        />
        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-lg bg-sky-600 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? "Creating…" : "Register"}
        </button>
        <p className="mt-4 text-center text-xs text-zinc-500">
          Already have an account?{" "}
          <Link href="/login" className="text-sky-400 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
