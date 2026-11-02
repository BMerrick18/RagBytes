"use client";

import { useId, useState } from "react";
import { formatNumber } from "@/lib/stats";

export interface ApiResult {
  status: number;
  ok: boolean;
  ms: number;
  body: unknown;
  error?: string;
}

const LONG_VALUE = 400;

export async function callApi(url: string, init?: RequestInit): Promise<ApiResult> {
  const started = performance.now();
  try {
    const response = await fetch(url, init);
    const text = await response.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {}
    return { status: response.status, ok: response.ok, ms: performance.now() - started, body };
  } catch {
    return {
      status: 0,
      ok: false,
      ms: performance.now() - started,
      body: null,
      error: `Couldn't reach ${new URL(url).origin}. Check it's running and that your connection allows it.`,
    };
  }
}

function shorten(_key: string, value: unknown) {
  if (typeof value === "string" && value.length > LONG_VALUE) {
    return `${value.slice(0, LONG_VALUE)}… (${formatNumber(value.length - LONG_VALUE)} more characters)`;
  }
  return value;
}

export function ApiResponse({ result, summary }: { result: ApiResult; summary?: string }) {
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(true);
  const [shownResult, setShownResult] = useState(result);
  const bodyId = useId();
  const full = typeof result.body === "string" ? result.body : JSON.stringify(result.body, null, 2);
  const shown = typeof result.body === "string" ? result.body : JSON.stringify(result.body, shorten, 2);
  const tone = result.ok
    ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30"
    : "bg-rose-400/10 text-rose-300 ring-rose-400/30";

  if (result !== shownResult) {
    setShownResult(result);
    setOpen(true);
  }

  async function copy() {
    await navigator.clipboard.writeText(full);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <figure className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
      <figcaption
        className={`flex flex-wrap items-center gap-3 px-4 py-2 text-xs ${open ? "border-b border-zinc-800" : ""}`}
      >
        <span className={`rounded-md px-2 py-0.5 font-mono font-semibold ring-1 ring-inset ${tone}`}>
          {result.status || "Failed"}
        </span>
        <span className="text-zinc-400">{formatNumber(Math.round(result.ms))} ms</span>
        {summary && <span className="text-zinc-300">{summary}</span>}
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={bodyId}
          className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
        >
          {open ? "Minimise" : "Show"}
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden
            className={`h-3.5 w-3.5 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
          </svg>
        </button>
        {!result.error && (
          <button
            type="button"
            onClick={copy}
            className="rounded-md px-2 py-1 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
          >
            {copied ? "Copied" : "Copy response"}
          </button>
        )}
      </figcaption>
      {open &&
        (result.error ? (
          <p id={bodyId} className="p-4 text-sm text-rose-300">
            {result.error}
          </p>
        ) : (
          <pre
            id={bodyId}
            className="max-h-[28rem] overflow-auto p-4 font-mono text-[13px] leading-relaxed text-zinc-200"
          >
            {shown}
          </pre>
        ))}
    </figure>
  );
}
