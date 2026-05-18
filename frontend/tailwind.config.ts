import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        surface: {
          DEFAULT: "#0c0e12",
          raised: "#12151c",
          border: "#1e2430",
        },
        accent: {
          DEFAULT: "#3b82f6",
          muted: "#2563eb",
        },
      },
    },
  },
  plugins: [],
};

export default config;
