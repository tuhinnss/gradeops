"use client";

import { useEffect, useState } from "react";
import { Icon } from "./Icon";

const KEY = "gradeops:theme";

export function ThemeToggle() {
  const [dark, setDark] = useState(true);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(KEY, next ? "dark" : "light");
    } catch {
      /* storage unavailable */
    }
  }
  return (
    <button type="button" onClick={toggle} className="rounded-md p-2 text-fg-muted hover:bg-surface-raised hover:text-fg" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} title="Toggle theme">
      <Icon name={dark ? "sun" : "moon"} />
    </button>
  );
}

/** Inline script run before paint so the stored theme applies without a flash. */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${KEY}");if(t!=="light"){document.documentElement.classList.add("dark")}}catch(e){document.documentElement.classList.add("dark")}})();`;
