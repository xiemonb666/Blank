import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const indexHtml = readFileSync(join(root, "index.html"), "utf8");
const distIndexPath = join(root, "dist", "index.html");
const distIndexHtml = existsSync(distIndexPath) ? readFileSync(distIndexPath, "utf8") : "";
const apiSource = readFileSync(join(root, "src", "api.ts"), "utf8");
const appSource = readFileSync(join(root, "src", "App.tsx"), "utf8");
const v2HookSource = readFileSync(join(root, "src", "hooks", "useV2Chat.ts"), "utf8");

const requiredDevCsp = [
  "default-src 'self'",
  "base-uri 'none'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "connect-src 'self'",
];

for (const directive of requiredDevCsp) {
  if (!indexHtml.includes(directive)) {
    throw new Error(`Missing development CSP directive: ${directive}`);
  }
}

if (distIndexHtml) {
  const requiredProdCsp = [
    "default-src 'self'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "connect-src 'self'",
  ];
  for (const directive of requiredProdCsp) {
    if (!distIndexHtml.includes(directive)) {
      throw new Error(`Missing production CSP directive: ${directive}`);
    }
  }
  if (distIndexHtml.includes("'unsafe-inline'")) {
    throw new Error("Production build CSP must not allow unsafe-inline.");
  }
  if (distIndexHtml.includes('src="/assets/') || distIndexHtml.includes('href="/assets/')) {
    throw new Error("Production build assets must use relative paths for subpath/file deployments.");
  }
}

const forbiddenFrontendApis = ["dangerouslySetInnerHTML", "innerHTML", "document.write", "eval("];
for (const pattern of forbiddenFrontendApis) {
  if (appSource.includes(pattern) || apiSource.includes(pattern)) {
    throw new Error(`Forbidden frontend API detected: ${pattern}`);
  }
}

for (const pattern of ["base.protocol !== \"https:\"", "localhost", "127.0.0.1"]) {
  if (!apiSource.includes(pattern)) {
    throw new Error(`API base URL guard is missing expected check: ${pattern}`);
  }
}

for (const pattern of ["__Host-blank_csrf", "X-CSRF-Token", "csrfHeaderFor(\"POST\")"]) {
  if (!apiSource.includes(pattern)) {
    throw new Error(`CSRF request guard is missing expected check: ${pattern}`);
  }
}

if (!v2HookSource.includes("csrfHeaderFor(\"POST\")")) {
  throw new Error("V2 stream request must include CSRF header.");
}

if (v2HookSource.includes("Authorization") || v2HookSource.includes("Bearer") || apiSource.includes("Authorization") || apiSource.includes("Bearer")) {
  throw new Error("V2 stream request must not send pseudo Bearer tokens; use Cookie + CSRF only.");
}

for (const pattern of ["token: string", "token?: string", "_token"]) {
  if (apiSource.includes(pattern) || v2HookSource.includes(pattern)) {
    throw new Error(`Frontend API clients must not expose legacy token parameters: ${pattern}`);
  }
}

for (const pattern of ["/api/auth/reauth", "重新验证管理员密码", "runAdminWrite"]) {
  if (!apiSource.includes(pattern) && !appSource.includes(pattern)) {
    throw new Error(`Admin reauth guard is missing expected check: ${pattern}`);
  }
}

console.log("frontend security checks passed");
