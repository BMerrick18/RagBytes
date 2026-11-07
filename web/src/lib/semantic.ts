import { formatNumber } from "@/lib/stats";

export type SemanticStyle = "precise" | "balanced" | "broad";

export interface SemanticOptions {
  style: SemanticStyle;
  strictHeadings: boolean;
  /** Characters. Null uses the style's own limit. */
  maxChunkChars: number | null;
}

/** The settings the API reports it used, under `options` on a semantic response. */
export interface AppliedSemanticOptions {
  style: SemanticStyle;
  strict_headings: boolean;
  max_chunk_chars: number;
}

/** Each style's own size limit, as set in the API's styles.py. */
export const SEMANTIC_STYLES: { id: SemanticStyle; name: string; summary: string; maxChars: number }[] = [
  {
    id: "precise",
    name: "Precise",
    summary: "Small, tightly focused chunks. Suits FAQ bots and question answering.",
    maxChars: 1200,
  },
  {
    id: "balanced",
    name: "Balanced",
    summary: "The default. Suits general search.",
    maxChars: 2000,
  },
  {
    id: "broad",
    name: "Broad",
    summary: "Larger chunks that keep more context. Suits long-context models and summaries.",
    maxChars: 3000,
  },
];

export const DEFAULT_SEMANTIC_OPTIONS: SemanticOptions = { style: "balanced", strictHeadings: false, maxChunkChars: null };

export const MAX_CHUNK_CHARS_RANGE = { min: 500, max: 8000 };

export function styleName(style: SemanticStyle): string {
  return SEMANTIC_STYLES.find((option) => option.id === style)?.name ?? style;
}

/** The form fields to send, leaving out any that match the API's defaults. */
export function semanticFields(options: SemanticOptions): [string, string][] {
  const fields: [string, string][] = [];
  if (options.style !== DEFAULT_SEMANTIC_OPTIONS.style) fields.push(["style", options.style]);
  if (options.strictHeadings) fields.push(["strict_headings", "true"]);
  if (options.maxChunkChars !== null) fields.push(["max_chunk_chars", String(options.maxChunkChars)]);
  return fields;
}

export function maxChunkCharsProblem(value: number | null): string | null {
  if (value === null) return null;
  if (!Number.isInteger(value) || value < MAX_CHUNK_CHARS_RANGE.min || value > MAX_CHUNK_CHARS_RANGE.max) {
    return `Use a whole number from ${formatNumber(MAX_CHUNK_CHARS_RANGE.min)} to ${formatNumber(MAX_CHUNK_CHARS_RANGE.max)}.`;
  }
  return null;
}

export function describeApplied(options: AppliedSemanticOptions): string {
  const parts = [`${styleName(options.style)} style`, `chunks up to ${formatNumber(options.max_chunk_chars)} characters`];
  if (options.strict_headings) parts.push("strict headings");
  return parts.join(" · ");
}
