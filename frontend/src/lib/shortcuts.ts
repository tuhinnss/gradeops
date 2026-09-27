/** Review-screen keyboard shortcuts (pure logic, unit-tested). */

export type ShortcutAction =
  | { type: "approve" }
  | { type: "override" }
  | { type: "escalate" }
  | { type: "prev" }
  | { type: "next" }
  | { type: "details" }
  | { type: "help" }
  | { type: "question"; index: number };

export const SHORTCUT_HELP: { keys: string; label: string }[] = [
  { keys: "A", label: "Approve" },
  { keys: "O", label: "Open override" },
  { keys: "E", label: "Escalate" },
  { keys: "←  →", label: "Previous / next submission" },
  { keys: "1 – 9", label: "Jump to question" },
  { keys: "Space", label: "Show / hide review details" },
  { keys: "Esc", label: "Close dialog" },
  { keys: "?", label: "Show shortcuts" },
];

type KeyLike = {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  target?: EventTarget | null;
};

/** True when the user is typing in a form control (shortcuts must not fire). */
export function isTypingTarget(target: EventTarget | null | undefined): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== "string") return false;
  const el = target as HTMLElement;
  const tag = el.tagName.toLowerCase();
  if (tag === "textarea" || tag === "select") return true;
  if (tag === "input") {
    const type = ((el as HTMLInputElement).type || "text").toLowerCase();
    return !["checkbox", "radio", "button", "submit", "reset"].includes(type);
  }
  return el.isContentEditable || el.getAttribute?.("contenteditable") === "true";
}

export function shortcutFor(e: KeyLike): ShortcutAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (isTypingTarget(e.target)) return null;
  switch (e.key) {
    case "a":
    case "A":
      return { type: "approve" };
    case "o":
    case "O":
      return { type: "override" };
    case "e":
    case "E":
      return { type: "escalate" };
    case "ArrowLeft":
      return { type: "prev" };
    case "ArrowRight":
      return { type: "next" };
    case " ":
    case "Spacebar":
      return { type: "details" };
    case "?":
      return { type: "help" };
    default:
      if (/^[1-9]$/.test(e.key)) return { type: "question", index: Number(e.key) - 1 };
      return null;
  }
}
