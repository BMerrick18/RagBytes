"use client";

import { useMemo, useState } from "react";
import { ChunkCard, FORMAT_STYLES } from "@/components/ChunkCard";
import { downloadJson, downloadJsonl } from "@/lib/download";
import { chunkStats, formatNumber } from "@/lib/stats";
import type { ChunkFormat, ChunkResponse } from "@/lib/types";

const PAGE_SIZE = 40;

export function ResultsView({ result, elapsedMs }: { result: ChunkResponse; elapsedMs?: number }) {
  const [query, setQuery] = useState("");
  const [format, setFormat] = useState<ChunkFormat | "all">("all");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const stats = useMemo(() => chunkStats(result.chunks), [result]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return result.chunks.filter(
      (chunk) =>
        (format === "all" || chunk.metadata.format === format) &&
        (!needle || chunk.embed_text.toLowerCase().includes(needle)),
    );
  }, [result, query, format]);

  const tallest = Math.max(1, ...stats.buckets.map((bucket) => bucket.count));

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">{result.filename}</h2>
          <p className="text-sm text-zinc-400">
            {formatNumber(stats.count)} chunks
            {stats.pages > 0 && ` across ${stats.pages} pages`}
            {elapsedMs !== undefined && ` · processed in ${(elapsedMs / 1000).toFixed(1)}s`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => downloadJsonl(result)}
            className="rounded-lg bg-cyan-400 px-3 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-cyan-300"
          >
            Download JSONL
          </button>
          <button
            type="button"
            onClick={() => downloadJson(result)}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-800"
          >
            Download JSON
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Chunks" value={formatNumber(stats.count)} />
        <Stat label="Median length" value={`${formatNumber(stats.medianLength)} chars`} />
        <Stat label="Shortest / longest" value={`${formatNumber(stats.minLength)} / ${formatNumber(stats.maxLength)}`} />
        <Stat label="Total text" value={`${formatNumber(stats.totalCharacters)} chars`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-sm font-medium text-zinc-300">Chunk length</p>
          <div className="mt-3 flex h-28 items-end gap-2">
            {stats.buckets.map((bucket) => (
              <div key={bucket.label} className="flex flex-1 flex-col items-center gap-1">
                <span className="text-xs text-zinc-400">{bucket.count || ""}</span>
                <div
                  className="w-full rounded-t bg-cyan-400/70"
                  style={{ height: `${(bucket.count / tallest) * 72}px` }}
                />
                <span className="text-[11px] text-zinc-500">{bucket.label}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-sm font-medium text-zinc-300">Formats</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <FilterChip active={format === "all"} onClick={() => setFormat("all")} label="All" count={stats.count} />
            {(Object.entries(stats.formats) as [ChunkFormat, number][]).map(([name, count]) => (
              <FilterChip
                key={name}
                active={format === name}
                onClick={() => setFormat(name)}
                label={name}
                count={count}
                tone={FORMAT_STYLES[name]}
              />
            ))}
          </div>
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setLimit(PAGE_SIZE);
            }}
            placeholder="Search chunk text…"
            className="mt-4 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-cyan-400 focus:outline-none"
          />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {filtered.length === 0 && (
          <p className="rounded-xl border border-zinc-800 p-6 text-center text-sm text-zinc-400">
            No chunks match this filter.
          </p>
        )}
        {filtered.slice(0, limit).map((chunk) => (
          <ChunkCard key={chunk.chunk_id} chunk={chunk} />
        ))}
        {filtered.length > limit && (
          <button
            type="button"
            onClick={() => setLimit(limit + PAGE_SIZE)}
            className="self-center rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
          >
            Show more ({formatNumber(filtered.length - limit)} left)
          </button>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <p className="text-xs uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-100">{value}</p>
    </div>
  );
}

interface FilterChipProps {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  tone?: string;
}

function FilterChip({ active, onClick, label, count, tone }: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-md px-2.5 py-1 text-sm ring-1 ring-inset transition-opacity ${
        tone ?? "bg-zinc-800 text-zinc-200 ring-zinc-700"
      } ${active ? "opacity-100 ring-2" : "opacity-60 hover:opacity-90"}`}
    >
      {label} <span className="text-xs opacity-70">{count}</span>
    </button>
  );
}
