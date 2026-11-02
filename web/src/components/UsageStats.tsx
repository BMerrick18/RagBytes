"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { formatNumber } from "@/lib/stats";

interface Totals {
  documents: number;
  chunks: number;
}

const COUNT_MS = 900;

/** Site-wide totals, fetched again whenever `refresh` changes. */
export function UsageStats({ refresh }: { refresh: number }) {
  const [totals, setTotals] = useState<Totals | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/stats", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: Totals | null) => {
        if (!cancelled && body) setTotals(body);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-2 gap-3">
        <Stat label="Documents chunked" value={totals?.documents} />
        <Stat label="Chunks made" value={totals?.chunks} />
      </dl>
      <div className="hidden items-start gap-3 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4 md:flex">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          aria-hidden
          className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3 5 6v5c0 4.5 3 8.5 7 10 4-1.5 7-5.5 7-10V6l-7-3Z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="m9 12 2 2 4-4" />
        </svg>
        <div className="flex flex-col gap-0.5">
          <p className="font-semibold text-emerald-200">No data is stored</p>
          <p className="text-sm text-zinc-400">
            Files are chunked in memory and discarded as soon as the chunks are returned.{" "}
            <Link href="/privacy" className="text-zinc-300 underline underline-offset-4 hover:text-zinc-100">
              Privacy
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-2xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className="text-2xl font-semibold tabular-nums text-zinc-50">
        {value === undefined ? <span className="text-zinc-600">–</span> : <CountUp value={value} />}
      </dd>
    </div>
  );
}

function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    const start = from.current;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const began = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = reduced ? 1 : Math.min(1, (now - began) / COUNT_MS);
      const eased = 1 - (1 - progress) ** 3;
      from.current = Math.round(start + (value - start) * eased);
      setShown(from.current);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <>{formatNumber(shown)}</>;
}
