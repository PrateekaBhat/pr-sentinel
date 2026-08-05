/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B1220",
        panel: "#121A2B",
        raised: "#17213A",
        steel: "#22304A",
        fog: "#8B96A8",
        paper: "#E7ECF3",
        amber: "#F5A623",
        risk: {
          low: "#3DD68C",
          medium: "#F5A623",
          high: "#E5484D",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(231,236,243,0.04) inset, 0 20px 40px -24px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};
