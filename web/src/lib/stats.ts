import type { Chunk, ChunkFormat } from "./types";

export interface LengthBucket {
  label: string;
  count: number;
}

export interface ChunkStats {
  count: number;
  totalCharacters: number;
  medianLength: number;
  minLength: number;
  maxLength: number;
  pages: number;
  formats: Partial<Record<ChunkFormat, number>>;
  buckets: LengthBucket[];
}

const BUCKETS: { label: string; max: number }[] = [
  { label: "< 250", max: 250 },
  { label: "250–500", max: 500 },
  { label: "500–1k", max: 1000 },
  { label: "1k–1.5k", max: 1500 },
  { label: "1.5k–2k", max: 2000 },
  { label: "> 2k", max: Infinity },
];

export function chunkStats(chunks: Chunk[]): ChunkStats {
  const lengths = chunks.map((chunk) => chunk.embed_text.length).sort((a, b) => a - b);
  const formats: Partial<Record<ChunkFormat, number>> = {};
  const pages = new Set<number>();
  for (const chunk of chunks) {
    formats[chunk.metadata.format] = (formats[chunk.metadata.format] ?? 0) + 1;
    for (const page of chunk.metadata.pages ?? []) pages.add(page);
    if (chunk.metadata.page !== null) pages.add(chunk.metadata.page);
  }
  const buckets = BUCKETS.map((bucket) => ({ label: bucket.label, count: 0 }));
  for (const length of lengths) {
    buckets[BUCKETS.findIndex((bucket) => length < bucket.max)].count += 1;
  }
  return {
    count: chunks.length,
    totalCharacters: lengths.reduce((sum, length) => sum + length, 0),
    medianLength: median(lengths),
    minLength: lengths[0] ?? 0,
    maxLength: lengths[lengths.length - 1] ?? 0,
    pages: pages.size,
    formats,
    buckets,
  };
}

function median(sorted: number[]): number {
  if (sorted.length === 0) return 0;
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return sorted[middle];
  return Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

export function isBinaryMedia(chunk: Chunk): boolean {
  const type = chunk.metadata.media_type;
  return Boolean(type) && !type!.startsWith("text/") && !type!.includes("xml");
}

export function formatNumber(value: number): string {
  return value.toLocaleString("en-GB");
}
