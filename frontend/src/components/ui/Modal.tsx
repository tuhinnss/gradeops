"use client";

import { useEffect, useId, useRef } from "react";
import { Button } from "./Button";
import { cx } from "./cx";

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  title: React.ReactNode;
  description?: React.ReactNode;
  onClose: () => void;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    // Focus the first form control (or the panel) for keyboard users.
    const first = panel.current?.querySelector<HTMLElement>("input, select, textarea, button[data-autofocus]");
    (first ?? panel.current)?.focus();
    return () => {
      window.removeEventListener("keydown", onKey, true);
      if (previouslyFocused.current instanceof HTMLElement) previouslyFocused.current.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cx(
          "relative max-h-[90vh] w-full overflow-y-auto rounded-lg border border-line bg-surface shadow-xl focus:outline-none",
          size === "sm" && "max-w-md",
          size === "md" && "max-w-lg",
          size === "lg" && "max-w-3xl",
        )}
      >
        <div className="border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-base font-semibold text-fg">
            {title}
          </h2>
          {description && <div className="mt-1 text-sm text-fg-muted">{description}</div>}
        </div>
        {children && <div className="px-5 py-4">{children}</div>}
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-surface-raised px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  tone = "primary",
  busy,
  onConfirm,
  onClose,
  children,
  confirmDisabled,
}: {
  open: boolean;
  title: React.ReactNode;
  description?: React.ReactNode;
  confirmLabel?: string;
  tone?: "primary" | "danger" | "success";
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  children?: React.ReactNode;
  confirmDisabled?: boolean;
}) {
  return (
    <Modal
      open={open}
      title={title}
      description={description}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone} onClick={onConfirm} loading={busy} disabled={confirmDisabled}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
