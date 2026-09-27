import { cx } from "./cx";

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto", className)}>
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return (
    <thead className="border-b border-line bg-surface-raised text-[11px] font-semibold uppercase tracking-wide text-fg-subtle">
      {children}
    </thead>
  );
}

export function TH({ children, className, align = "left" }: { children?: React.ReactNode; className?: string; align?: "left" | "right" | "center" }) {
  return <th scope="col" className={cx("px-3 py-2 font-semibold", align === "right" && "text-right", align === "center" && "text-center", className)}>{children}</th>;
}

export function TR({ children, className, onClick }: { children: React.ReactNode; className?: string; onClick?: () => void }) {
  return (
    <tr onClick={onClick} className={cx("border-b border-line last:border-0", onClick && "cursor-pointer hover:bg-surface-raised", className)}>
      {children}
    </tr>
  );
}

export function TD({ children, className, align = "left", colSpan }: { children?: React.ReactNode; className?: string; align?: "left" | "right" | "center"; colSpan?: number }) {
  return (
    <td colSpan={colSpan} className={cx("px-3 py-2 align-middle text-fg", align === "right" && "tabular text-right", align === "center" && "text-center", className)}>
      {children}
    </td>
  );
}
