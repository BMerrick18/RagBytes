"use client";

import { useState } from "react";
import { formatNumber, isBinaryMedia } from "@/lib/stats";
import type { Chunk, ChunkFormat } from "@/lib/types";

const PREVIEW_LIMIT = 600;

export const FORMAT_STYLES: Record<ChunkFormat, string> = {
  text: "bg-sky-400/10 text-sky-300 ring-sky-400/30",
  list: "bg-violet-400/10 text-violet-300 ring-violet-400/30",
  table: "bg-amber-400/10 text-amber-300 ring-amber-400/30",
  image: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30",
  chart: "bg-pink-400/10 text-pink-300 ring-pink-400/30",
  code: "bg-lime-400/10 text-lime-300 ring-lime-400/30",
  complex: "bg-rose-400/10 text-rose-300 ring-rose-400/30",
};

type View = "embed" | "content";

export function ChunkCard({ chunk }: { chunk: Chunk }) {
  const [view, setView] = useState<View>("embed");
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const { metadata } = chunk;
  const binary = isBinaryMedia(chunk);
  const showEmbed = view === "embed" || binary;
  const trail = metadata.title ? [metadata.title, ...metadata.headings] : metadata.headings;
  const path = trail.join(" > ");
  const pathPrefix = `${path}\n\n`;
  const headed = showEmbed && path !== "" && chunk.embed_text.startsWith(pathPrefix);
  const text = !showEmbed ? chunk.content : headed ? chunk.embed_text.slice(pathPrefix.length) : chunk.embed_text;
  const long = text.length > PREVIEW_LIMIT;
  const shown = expanded || !long ? text : `${text.slice(0, PREVIEW_LIMIT).trimEnd()}…`;

  async function copy() {
    await navigator.clipboard.writeText(chunk.embed_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-zinc-500">#{metadata.chunk_number}</span>
        <span className={`rounded-md px-2 py-0.5 font-medium ring-1 ring-inset ${FORMAT_STYLES[metadata.format]}`}>
          {metadata.format}
        </span>
        {metadata.page !== null && <span className="text-zinc-400">Page {metadata.page}</span>}
        <span className="text-zinc-500">{formatNumber(chunk.embed_text.length)} characters</span>
        <div className="ml-auto flex flex-wrap items-center gap-1">
          {!binary && (
            <div className="flex rounded-md bg-zinc-800/80 p-0.5">
              {(["embed", "content"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setView(option)}
                  className={`rounded px-2 py-0.5 transition-colors ${
                    view === option ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {option === "embed" ? "Embed text" : "Content"}
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={copy}
            className="rounded-md px-2 py-1 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </header>

      {trail.length > 0 && !headed && (
        <nav aria-label="Heading path" className="mt-2 flex flex-wrap items-center gap-1 text-sm text-zinc-300">
          {trail.map((heading, index) => (
            <span key={index} className="flex items-center gap-1">
              {index > 0 && <span className="text-zinc-600">›</span>}
              <span className="max-w-[28ch] truncate" title={heading}>
                {heading}
              </span>
            </span>
          ))}
        </nav>
      )}

      {binary && (
        // eslint-disable-next-line @next/next/no-img-element -- base64 content from the API, not a static asset
        <img
          src={`data:${metadata.media_type};base64,${chunk.content}`}
          alt={chunk.embed_text}
          className="mt-3 max-h-72 rounded-lg border border-zinc-800 bg-white object-contain p-1"
        />
      )}

      <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-[13px] leading-relaxed text-zinc-200">
        {headed && (
          <>
            <span
              className="font-sans text-sm font-semibold text-cyan-300"
              title="Heading path, embedded with the chunk so it keeps its place in the document"
            >
              {path}
            </span>
            {"\n\n"}
          </>
        )}
        {shown}
      </pre>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-sm font-medium text-cyan-300 hover:text-cyan-200"
        >
          {expanded ? "Show less" : "Show all"}
        </button>
      )}
    </article>
  );
}
