/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "var(--surface)",
          muted: "var(--surface-muted)",
          sunken: "var(--surface-sunken)",
          hover: "var(--surface-hover)",
        },
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
          brand: "var(--line-brand)",
        },
        ink: {
          DEFAULT: "var(--ink)",
          muted: "var(--ink-muted)",
          faint: "var(--ink-faint)",
          placeholder: "var(--ink-placeholder)",
        },
        brand: {
          DEFAULT: "var(--brand)",
          hover: "var(--brand-hover)",
          soft: "var(--brand-soft)",
          ink: "var(--brand-ink)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          hover: "var(--danger-hover)",
          soft: "var(--danger-soft)",
          ink: "var(--danger-ink)",
          line: "var(--danger-line)",
        },
        success: {
          DEFAULT: "var(--success)",
          soft: "var(--success-soft)",
          ink: "var(--success-ink)",
          line: "var(--success-line)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          soft: "var(--warning-soft)",
          ink: "var(--warning-ink)",
          line: "var(--warning-line)",
        },
        info: {
          soft: "var(--info-soft)",
          ink: "var(--info-ink)",
        },
        accent: {
          soft: "var(--accent-soft)",
          ink: "var(--accent-ink)",
        },
      },
      borderRadius: {
        card: "var(--radius-card)",
        "card-lg": "var(--radius-card-lg)",
        control: "var(--radius-control)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
      },
    },
  },
  plugins: [],
}
