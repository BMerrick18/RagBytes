"use client";

import { useState, type ReactNode } from "react";
import { ApiResponse, callApi, type ApiResult } from "@/components/ApiResponse";
import { EndpointRow } from "@/components/EndpointRow";

export function RunnableGet({ base, path, children }: { base: string; path: string; children: ReactNode }) {
  const [result, setResult] = useState<ApiResult | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    setResult(await callApi(`${base}${path}`));
    setRunning(false);
  }

  return (
    <EndpointRow
      verb="GET"
      path={path}
      action={
        <button
          type="button"
          onClick={run}
          disabled={running}
          className="shrink-0 self-start rounded-md border border-zinc-700 px-3 py-1 text-sm font-medium text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-800 disabled:opacity-50"
        >
          {running ? "Running…" : "Run"}
        </button>
      }
      below={result && <ApiResponse result={result} />}
    >
      {children}
    </EndpointRow>
  );
}
