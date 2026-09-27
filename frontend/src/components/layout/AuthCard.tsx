import { ThemeToggle } from "./ThemeToggle";

export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="mb-6 flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-accent text-sm font-bold text-white">G</span>
        <span className="text-sm font-semibold tracking-[0.2em] text-fg">GRADEOPS</span>
      </div>
      <div className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-fg">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-fg-muted">{subtitle}</p>}
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}
