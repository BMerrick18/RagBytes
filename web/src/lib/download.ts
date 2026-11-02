import type { ChunkResponse } from "./types";

export function downloadJson(result: ChunkResponse) {
  save(JSON.stringify(result, null, 2), `${baseName(result.filename)}.chunks.json`, "application/json");
}

/** One line per chunk, with the text to embed under `text`, in the shape most vector stores import. */
export function downloadJsonl(result: ChunkResponse) {
  const lines = result.chunks.map((chunk) =>
    JSON.stringify({ id: chunk.chunk_id, text: chunk.embed_text, metadata: chunk.metadata }),
  );
  save(lines.join("\n") + "\n", `${baseName(result.filename)}.chunks.jsonl`, "application/x-ndjson");
}

function baseName(filename: string): string {
  return filename.replace(/\.[^.]+$/, "") || "document";
}

function save(contents: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
