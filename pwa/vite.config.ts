import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const DEV_SCRIPT_CSP = "script-src 'self' 'unsafe-inline'";
const DEV_STYLE_CSP = "style-src 'self' 'unsafe-inline'";
const PROD_SCRIPT_CSP = "script-src 'self'";
const PROD_STYLE_CSP = "style-src 'self'";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBase = env.VITE_API_BASE_URL?.trim() || "http://127.0.0.1:8000";
  const connectSrc = `${apiBase} http://127.0.0.1:8000 http://localhost:8000`;

  return {
    base: "./",
    plugins: [
      react(),
      {
        name: "blank-csp",
        transformIndexHtml(html) {
          let result = html.replace("%BLANK_CONNECT_SRC%", connectSrc);
          if (command === "build") {
            result = result.replace(DEV_SCRIPT_CSP, PROD_SCRIPT_CSP).replace(DEV_STYLE_CSP, PROD_STYLE_CSP);
          }
          return result;
        },
      },
    ],
  };
});
