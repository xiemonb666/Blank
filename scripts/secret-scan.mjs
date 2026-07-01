#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = process.cwd();
const excludedDirs = new Set([
  ".build",
  ".pytest_cache",
  ".sourcekit-lsp",
  ".swiftpm",
  "DerivedData",
  "Packages",
  "backups",
  "node_modules",
  "dist",
  "__pycache__",
  ".venv",
  ".git",
  ".tools",
  "data",
]);

const excludedFiles = new Set([
  "package-lock.json",
  ".package-lock.json",
]);

const textExtensions = new Set([
  ".conf",
  ".css",
  ".env",
  ".example",
  ".html",
  ".js",
  ".json",
  ".local",
  ".md",
  ".mjs",
  ".py",
  ".service",
  ".sh",
  ".timer",
  ".toml",
  ".ts",
  ".tsx",
  ".txt",
  ".yml",
  ".yaml",
]);

const allowedFragments = [
  "replace-with-",
  "replace-before-",
  "change-this",
  "example",
  "blank.example.com",
  "sk-test-",
  "sk-valid-",
  "sk-safe",
  "sk-query",
  "sk-legacy",
  "sk-empty-choices",
  "sk-chat-error",
  "sk-visible-to-model",
  "sk-http-error-secret",
  "sk-json-error-secret",
  "sk-redirect-test",
  "sk-huge-response",
  "sk-proxy-bypass",
  "sk-unit-test",
  "sk-extra-field-secret",
  "sk-dns-rebind-secret",
  "Bearer ***",
  "Bearer exposed-token",
  "Bearer leaked-token",
  "Bearer kimi-access-token",
  "expired-token",
  "token-hash-0123456789abcdef-0123456789",
  "prod-secret-0123456789abcdef-0123456789abcdef",
  "bootstrap-0123456789abcdef-0123456789",
  "Passw0rd123",
  "WrongPassw0rd",
  "ShouldNotEcho123",
  "password123",
  "qwerty123",
  "AUTH_DUMMY_PASSWORD",
  "blank-development-token-hash-key",
];

const detectors = [
  {
    name: "private key",
    pattern: /-----BEGIN (?:RSA |EC |OPENSSH |DSA |)?PRIVATE KEY-----/,
  },
  {
    name: "openai project key",
    pattern: /\bsk-proj-[A-Za-z0-9_-]{20,}\b/,
  },
  {
    name: "openai live key",
    pattern: /\bsk-live-[A-Za-z0-9_-]{20,}\b/,
  },
  {
    name: "long bearer token",
    pattern: /\bBearer\s+[A-Za-z0-9._~+/=-]{32,}\b/,
  },
  {
    name: "jwt",
    pattern: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/,
  },
  {
    name: "aws access key",
    pattern: /\bAKIA[0-9A-Z]{16}\b/,
  },
  {
    name: "github token",
    pattern: /\bgh[pousr]_[A-Za-z0-9_]{30,}\b/,
  },
  {
    name: "hardcoded secret assignment",
    pattern: /\b(?:SECRET|SECRET_KEY|TOKEN_HASH_KEY|ADMIN_BOOTSTRAP_KEY|PASSWORD)\b\s*=\s*["'](?!replace-|change-this|test|example|password|qwerty|Passw0rd|WrongPassw0rd|ShouldNotEcho)[^"']{20,}["']/i,
  },
];

const findings = [];

function extensionOf(path) {
  const basename = path.split("/").pop() ?? "";
  if (basename.endsWith(".env.example")) return ".example";
  const index = basename.lastIndexOf(".");
  return index === -1 ? "" : basename.slice(index);
}

function shouldSkip(path) {
  const rel = relative(root, path);
  const parts = rel.split("/");
  if (parts.some((part) => excludedDirs.has(part))) return true;
  return excludedFiles.has(parts.at(-1) ?? "");
}

function isProbablyTextFile(path) {
  return textExtensions.has(extensionOf(path)) || path.endsWith(".gitignore") || path.endsWith("Plan.md") || path.endsWith("README.md");
}

function lineAllowed(line) {
  return allowedFragments.some((fragment) => line.includes(fragment));
}

function scanFile(path) {
  if (!isProbablyTextFile(path)) return;
  let content;
  try {
    content = readFileSync(path, "utf8");
  } catch {
    return;
  }
  const rel = relative(root, path);
  const lines = content.split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    if (lineAllowed(line)) continue;
    for (const detector of detectors) {
      if (detector.pattern.test(line)) {
        findings.push(`${rel}:${index + 1}: ${detector.name}`);
      }
      detector.pattern.lastIndex = 0;
    }
  }
}

function walk(path) {
  if (shouldSkip(path)) return;
  const stats = statSync(path);
  if (stats.isDirectory()) {
    for (const entry of readdirSync(path)) {
      walk(join(path, entry));
    }
    return;
  }
  if (stats.isFile()) {
    scanFile(path);
  }
}

walk(root);

if (findings.length > 0) {
  console.error("potential secrets detected:");
  for (const finding of findings) {
    console.error(`- ${finding}`);
  }
  process.exit(1);
}

console.log("secret scan passed");
