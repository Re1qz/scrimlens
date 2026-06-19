import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        apex: {
          orange: "#E8630A",
          dark: "#0A0A0F",
          card: "#13131A",
          border: "#1E1E2E",
        },
      },
    },
  },
  plugins: [],
};

export default config;
