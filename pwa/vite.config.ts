import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const DEV_SCRIPT_CSP = "script-src 'self' 'unsafe-inline'";
const DEV_STYLE_CSP = "style-src 'self' 'unsafe-inline'";
const PROD_SCRIPT_CSP = "script-src 'self'";
const PROD_STYLE_CSP = "style-src 'self'";

export default defineConfig(({ command }) => ({
  base: "./",
  plugins: [
    react(),
    {
      name: "blank-production-csp",
      transformIndexHtml(html) {
        if (command !== "build") return html;
        return html.replace(DEV_SCRIPT_CSP, PROD_SCRIPT_CSP).replace(DEV_STYLE_CSP, PROD_STYLE_CSP);
      },
    },
  ],
}));
