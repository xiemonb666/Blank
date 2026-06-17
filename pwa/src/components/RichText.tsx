import type { ReactNode } from "react";

interface RichTextProps {
  text: string;
  className?: string;
}

type TextPart = {
  type: "text" | "formula";
  value: string;
};

const DISPLAY_FORMULA_PATTERN = /(?:\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\])/g;
const INLINE_FORMULA_PATTERN = /(?:\\\(([\s\S]+?)\\\)|\$([^$\n]+?)\$)/g;
const RAW_FORMULA_PATTERN = /(?:[A-Za-zΔδθλμσΣΩαβγρφψχ¤][A-Za-z0-9ΔδθλμσΣΩαβγρφψχ¤]*\s*(?:\([^)]*\)|_\{?[-+A-Za-z0-9]+\}?|)\s*=\s*[^,，。；;.\n\u3400-\u9fff]+(?:[,，]\s*[A-Za-zΔδθλμσΣΩαβγρφψχ¤][A-Za-z0-9ΔδθλμσΣΩαβγρφψχ¤]*\s*(?:\([^)]*\)|_\{?[-+A-Za-z0-9]+\}?|)\s*=\s*[^,，。；;.\n\u3400-\u9fff]+)*)/g;
const FORMULA_TRAILING_PUNCTUATION_PATTERN = /[\s,，。；;：:]+$/;
const TEXT_ONLY_PUNCTUATION_PATTERN = /^[,，。；;：:\s]+$/;
const TEXT_AFTER_FORMULA_PUNCTUATION_PATTERN = /^[,，。；;：:\s]+/;

const COMMAND_REPLACEMENTS: Record<string, string> = {
  Delta: "Δ",
  delta: "δ",
  theta: "θ",
  lambda: "λ",
  mu: "μ",
  sigma: "σ",
  Sigma: "Σ",
  Omega: "Ω",
  alpha: "α",
  beta: "β",
  gamma: "γ",
  rho: "ρ",
  phi: "φ",
  psi: "ψ",
  chi: "χ",
  cdot: "·",
  times: "×",
  approx: "≈",
  le: "≤",
  ge: "≥",
  neq: "≠",
  infty: "∞",
};

export function RichText({ text, className }: RichTextProps) {
  const blocks = splitBlocks(text);
  if (blocks.length === 0) return null;

  return (
    <div className={`rich-text ${className ?? ""}`.trim()}>
      {blocks.map((block, blockIndex) => (
        <RichBlock key={`${blockIndex}-${block.slice(0, 18)}`} text={block} />
      ))}
    </div>
  );
}

function RichBlock({ text }: { text: string }) {
  const explicitParts = splitDisplayFormulas(text);
  const parts = explicitParts.flatMap((part) => (part.type === "formula" ? [part] : splitRawFormulas(part.value)));

  return (
    <>
      {parts.map((part, index) =>
        part.type === "formula" ? (
          <div className="math-display" key={`${index}-formula`}>
            <Formula text={part.value} />
          </div>
        ) : (
          <p key={`${index}-text`}>{renderInlineText(part.value)}</p>
        ),
      )}
    </>
  );
}

function splitBlocks(text: string) {
  return text
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);
}

function splitDisplayFormulas(text: string): TextPart[] {
  return splitByPattern(text, DISPLAY_FORMULA_PATTERN, (match) => ({
    type: "formula",
    value: match[1] || match[2] || "",
  }));
}

function splitRawFormulas(text: string): TextPart[] {
  return splitByPattern(text, RAW_FORMULA_PATTERN, (match) => ({
    type: "formula",
    value: match[0],
  }));
}

function splitByPattern(
  text: string,
  pattern: RegExp,
  toPart: (match: RegExpExecArray) => TextPart,
): TextPart[] {
  const parts: TextPart[] = [];
  pattern.lastIndex = 0;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const start = match.index;
    if (start > cursor) {
      pushTextPart(parts, text.slice(cursor, start));
    }
    const part = toPart(match);
    const value = part.type === "formula" ? stripFormulaTrailingPunctuation(part.value) : part.value.trim();
    if (value) parts.push({ type: part.type, value });
    cursor = start + match[0].length;
  }
  pushTextPart(parts, text.slice(cursor));
  return parts.length ? parts : [{ type: "text", value: text }];
}

function stripFormulaTrailingPunctuation(value: string) {
  return value.replace(FORMULA_TRAILING_PUNCTUATION_PATTERN, "").trim();
}

function pushTextPart(parts: TextPart[], value: string) {
  let text = value.trim();
  if (!text || TEXT_ONLY_PUNCTUATION_PATTERN.test(text)) return;
  if (parts[parts.length - 1]?.type === "formula") {
    text = text.replace(TEXT_AFTER_FORMULA_PUNCTUATION_PATTERN, "").trim();
    if (!text || TEXT_ONLY_PUNCTUATION_PATTERN.test(text)) return;
  }
  parts.push({ type: "text", value: text });
}

function renderInlineText(text: string) {
  const nodes: ReactNode[] = [];
  INLINE_FORMULA_PATTERN.lastIndex = 0;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = INLINE_FORMULA_PATTERN.exec(text)) !== null) {
    const start = match.index;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    nodes.push(
      <span className="math-inline" key={`inline-${start}`}>
        <Formula text={match[1] || match[2] || ""} />
      </span>,
    );
    cursor = start + match[0].length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes.length ? nodes : text;
}

function Formula({ text }: { text: string }) {
  return <>{renderMathAtoms(normalizeMath(text))}</>;
}

function normalizeMath(text: string) {
  return text
    .replace(/¤\s*([A-Za-z])/g, "$1\u0307")
    .replace(/\\([A-Za-z]+)/g, (_, command: string) => COMMAND_REPLACEMENTS[command] ?? command)
    .replace(/\*/g, "·")
    .replace(/->/g, "→")
    .replace(/>=/g, "≥")
    .replace(/<=/g, "≤")
    .replace(/!=/g, "≠")
    .replace(/\s+/g, " ")
    .trim();
}

function renderMathAtoms(source: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (char === "_" || char === "^") {
      const parsed = readScript(source, index + 1);
      const content = renderMathAtoms(parsed.value);
      nodes.push(
        char === "_" ? (
          <sub key={`${index}-sub`}>{content}</sub>
        ) : (
          <sup key={`${index}-sup`}>{content}</sup>
        ),
      );
      index = parsed.nextIndex - 1;
      continue;
    }
    if (char === "{" || char === "}") continue;
    nodes.push(char);
  }
  return nodes;
}

function readScript(source: string, startIndex: number) {
  let index = startIndex;
  while (source[index] === " ") index += 1;
  if (source[index] === "{") {
    let depth = 1;
    let end = index + 1;
    while (end < source.length && depth > 0) {
      if (source[end] === "{") depth += 1;
      if (source[end] === "}") depth -= 1;
      end += 1;
    }
    return {
      value: source.slice(index + 1, Math.max(index + 1, end - 1)),
      nextIndex: end,
    };
  }
  if (source[index] === "\\") {
    const match = /^\\[A-Za-z]+/.exec(source.slice(index));
    if (match) {
      return { value: normalizeMath(match[0]), nextIndex: index + match[0].length };
    }
  }
  const match = /^[A-Za-z0-9ΔδθλμσΣΩαβγρφψχ+\-]+/.exec(source.slice(index));
  if (match) {
    return { value: match[0], nextIndex: index + match[0].length };
  }
  return { value: source[index] ?? "", nextIndex: Math.min(index + 1, source.length) };
}
