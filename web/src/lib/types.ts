import type { AppliedSemanticOptions, SemanticOptions } from "@/lib/semantic";

export type ChunkFormat = "text" | "list" | "table" | "image" | "chart" | "code" | "complex";

export interface ChunkMetadata {
  filename: string;
  file_id: string;
  chunk_number: number;
  headings: string[];
  heading: string | null;
  subheading: string | null;
  page: number | null;
  format: ChunkFormat;
  media_type: string | null;
  details: { start: number; end: number };
}

/** One chunk. `content` is base64 when `metadata.media_type` is a binary type such as an image. */
export interface Chunk {
  chunk_id: string;
  metadata: ChunkMetadata;
  embed_text: string;
  content: string;
}

export interface ChunkResponse {
  filename: string;
  file_id: string;
  chunks: Chunk[];
  /** Present on semantic responses: the settings the chunks were cut with. */
  options?: AppliedSemanticOptions;
}

export type JobStatus = "queued" | "running" | "done" | "error";

export interface Job {
  id: string;
  file: File;
  tier: string;
  /** The semantic settings this job was run with, when its tier is semantic. */
  semantic?: SemanticOptions;
  status: JobStatus;
  result?: ChunkResponse;
  error?: string;
  elapsedMs?: number;
}
