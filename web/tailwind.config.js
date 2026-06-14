/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        ink: {
          950: "#0a0c10",
          900: "#0e1117",
          850: "#141821",
          800: "#1a1f2b",
          700: "#252b3a",
          600: "#363d51",
        },
        chalk: {
          DEFAULT: "#e6e9f0",
          dim: "#a3acc2",
          faint: "#6b7493",
        },
        // semantic accents
        gridiron: "#3ddc97", // primary green (field)
        sky: "#4cc2ff",
        amber: "#ffb454",
        rose: "#ff6b81",
        violet: "#a78bfa",
        // analysis "basis" tags
        basisFantasy: "#4cc2ff",
        basisReal: "#3ddc97",
        basisBoth: "#a78bfa",
        // NFL positions
        posQB: "#ff6b81",
        posRB: "#3ddc97",
        posWR: "#4cc2ff",
        posTE: "#ffb454",
        posDEF: "#a3acc2",
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(61,220,151,0.25), 0 0 24px -6px rgba(61,220,151,0.35)",
      },
      borderRadius: { xl2: "1rem" },
    },
  },
  plugins: [],
};
