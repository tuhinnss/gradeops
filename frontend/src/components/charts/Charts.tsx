"use client";

/**
 * Lightweight, theme-aware charts (HTML/CSS). Mark specs: bars ≤ 24px thick with
 * a 4px rounded data-end and square baseline, hairline recessive grid, 2px
 * surface gaps between stacked segments, a hover/focus tooltip on every mark,
 * text in text tokens (never the series colour). Colours come from the
 * validated --viz-* tokens in globals.css.
 */
import { useState } from "react";
import { cx } from "@/components/ui";

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div role="tooltip" className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs text-fg shadow-md">
      {children}
    </div>
  );
}

export type ColumnDatum = { label: string; value: number; tooltip?: string };

/** Single-series column chart (e.g. score distribution). */
export function ColumnChart({ data, height = 180, unit, ariaLabel }: { data: ColumnDatum[]; height?: number; unit: string; ariaLabel: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const top = Math.max(0, ...data.map((d) => d.value));
  const integer = data.every((d) => Number.isInteger(d.value));
  // Count axes get whole-number ticks (never "0.5 students").
  const max = integer && top <= 4 ? Math.max(1, top) : niceMax(top);
  const ticks = integer && max <= 4 ? Array.from({ length: max + 1 }, (_, i) => max - i) : [max, max / 2, 0];
  return (
    <figure aria-label={ariaLabel} className="w-full">
      <div className="flex gap-2">
        <div className="tabular flex flex-col justify-between text-right text-[11px] text-fg-subtle" style={{ height }} aria-hidden>
          {ticks.map((t) => (
            <span key={t} className="-translate-y-1/2 leading-none last:translate-y-0">
              {Number.isInteger(t) ? t : t.toFixed(1)}
            </span>
          ))}
        </div>
        <div className="relative flex-1">
          <div className="absolute inset-0 flex flex-col justify-between" aria-hidden>
            {ticks.map((t) => (
              <div key={t} className="h-px w-full" style={{ background: "var(--viz-grid)" }} />
            ))}
          </div>
          <div className="relative flex items-end" style={{ height }}>
            {data.map((d, i) => (
              <div key={d.label} className="relative flex h-full flex-1 items-end justify-center" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <button
                  type="button"
                  className="w-full max-w-[24px] rounded-t-[4px] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  style={{ height: `${(d.value / max) * 100}%`, minHeight: d.value > 0 ? 2 : 0, background: "var(--viz-series)", opacity: hover === null || hover === i ? 1 : 0.55 }}
                  aria-label={`${d.label}: ${d.value} ${unit}`}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                />
                {hover === i && (
                  <Tip>
                    <span className="font-medium">{d.label}</span> · {d.tooltip ?? `${d.value} ${unit}`}
                  </Tip>
                )}
              </div>
            ))}
          </div>
          <div className="mt-1 flex" aria-hidden>
            {data.map((d, i) => (
              <span key={d.label} className="tabular flex-1 text-center text-[10px] text-fg-subtle">
                {i % 2 === 0 || data.length <= 6 ? d.label : ""}
              </span>
            ))}
          </div>
        </div>
      </div>
    </figure>
  );
}

export type BarDatum = { label: string; value: number; display: string; sublabel?: string; highlight?: boolean };

/** Horizontal bar list (e.g. average % per question); value at the bar tip. */
export function BarList({ data, max, ariaLabel }: { data: BarDatum[]; max: number; ariaLabel: string }) {
  const [hover, setHover] = useState<number | null>(null);
  return (
    <figure aria-label={ariaLabel} className="space-y-1.5">
      {data.map((d, i) => (
        <div key={d.label} className="grid grid-cols-[4.5rem_1fr] items-center gap-3 text-xs" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          <span className={cx("truncate text-right", d.highlight ? "font-semibold text-fg" : "text-fg-muted")}>{d.label}</span>
          <div className="relative flex items-center gap-2">
            <div
              className="h-[10px] rounded-r-[4px]"
              style={{ width: `${Math.max(0, Math.min(1, d.value / (max || 1))) * 85}%`, minWidth: d.value > 0 ? 2 : 0, background: "var(--viz-series)", opacity: hover === null || hover === i ? 1 : 0.55 }}
              tabIndex={0}
              role="img"
              aria-label={`${d.label}: ${d.display}${d.sublabel ? `, ${d.sublabel}` : ""}`}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            />
            <span className="tabular text-fg">{d.display}</span>
            {hover === i && d.sublabel && <Tip>{d.sublabel}</Tip>}
          </div>
        </div>
      ))}
    </figure>
  );
}

export type StackSegment = { key: string; label: string; value: number };
const ORDINAL = ["var(--viz-ord-high)", "var(--viz-ord-mid)", "var(--viz-ord-low)"];

/** Legend for ordinal stacks (identity never relies on colour alone: table carries values). */
export function StackLegend({ labels }: { labels: string[] }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-fg-muted">
      {labels.map((l, i) => (
        <span key={l} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: ORDINAL[i] }} aria-hidden />
          {l}
        </span>
      ))}
    </div>
  );
}

/** 100% stacked bar of ordered categories (e.g. full / partial / zero credit). */
export function StackedBar({ segments, ariaLabel }: { segments: StackSegment[]; ariaLabel: string }) {
  const [hover, setHover] = useState<string | null>(null);
  const total = segments.reduce((n, s) => n + s.value, 0) || 1;
  return (
    <div className="relative flex h-[10px] w-full gap-[2px]" role="img" aria-label={ariaLabel}>
      {segments.map((s, i) =>
        s.value > 0 ? (
          <div
            key={s.key}
            className={cx("relative h-full", i === segments.length - 1 || segments.slice(i + 1).every((x) => x.value === 0) ? "rounded-r-[4px]" : "")}
            style={{ width: `${(s.value / total) * 100}%`, background: ORDINAL[i] }}
            onMouseEnter={() => setHover(s.key)}
            onMouseLeave={() => setHover(null)}
          >
            {hover === s.key && (
              <Tip>
                {s.label}: {s.value.toFixed(0)}%
              </Tip>
            )}
          </div>
        ) : null,
      )}
    </div>
  );
}
