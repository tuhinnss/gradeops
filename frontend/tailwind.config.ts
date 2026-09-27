import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      // Semantic colour tokens; values live in globals.css for light and dark themes.
      colors: {
        bg: token("bg"),
        surface: { DEFAULT: token("surface"), raised: token("surface-raised"), sunken: token("surface-sunken") },
        line: { DEFAULT: token("line"), strong: token("line-strong") },
        fg: { DEFAULT: token("fg"), muted: token("fg-muted"), subtle: token("fg-subtle") },
        accent: { DEFAULT: token("accent"), strong: token("accent-strong"), soft: token("accent-soft") },
      },
    },
  },
  plugins: [],
};

export default config;
