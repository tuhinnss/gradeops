import Link from "next/link";

export function AppNav() {
  return (
    <nav className="flex flex-wrap gap-3 text-sm">
      <Link href="/" className="text-zinc-400 transition hover:text-white">
        Dashboard
      </Link>
      <Link href="/analytics" className="text-zinc-400 transition hover:text-white">
        Analytics
      </Link>
      <Link href="/login" className="text-zinc-400 transition hover:text-white">
        Login
      </Link>
      <Link href="/signup" className="text-zinc-400 transition hover:text-white">
        Sign up
      </Link>
    </nav>
  );
}
