"use client";

import { Icon } from "@/components/layout/Icon";
import { SHORTCUT_HELP } from "@/lib/shortcuts";

export function ShortcutHelp({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div className="relative">
      <button type="button" onClick={onToggle} className="rounded-md p-2 text-fg-muted hover:bg-surface-raised hover:text-fg" aria-expanded={open} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
        <Icon name="keyboard" />
      </button>
      {open && (
        <div role="tooltip" className="absolute right-0 z-20 mt-2 w-64 rounded-lg border border-line bg-surface p-3 shadow-lg">
          <p className="mb-2 text-xs font-semibold text-fg">Keyboard shortcuts</p>
          <dl className="space-y-1 text-xs">
            {SHORTCUT_HELP.map((s) => (
              <div key={s.keys} className="flex justify-between gap-3">
                <dt className="text-fg-muted">{s.label}</dt>
                <dd>
                  <kbd className="rounded border border-line bg-surface-raised px-1.5 font-mono text-[11px] text-fg">{s.keys}</kbd>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[11px] text-fg-subtle">Shortcuts are disabled while typing.</p>
        </div>
      )}
    </div>
  );
}
