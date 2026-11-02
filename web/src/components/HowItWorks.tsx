"use client";

import { type ReactNode, useEffect, useRef, useState, useSyncExternalStore } from "react";

const STEP_MS = [1600, 1600, 2400];

const CHUNKS = [
  { edge: "border-cyan-400", line: "bg-cyan-400/70", card: "border-cyan-400/50 bg-cyan-400/10" },
  { edge: "border-violet-400", line: "bg-violet-400/70", card: "border-violet-400/50 bg-violet-400/10" },
  { edge: "border-amber-400", line: "bg-amber-400/70", card: "border-amber-400/50 bg-amber-400/10" },
];

const STEPS = [
  { title: "Your document", text: "PDF, Word, web page, Markdown or text" },
  { title: "We chunk it", text: "By size, by section, or by meaning" },
  { title: "You get chunks back", text: "JSON with headings and pages, ready to embed" },
];

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function useReducedMotion() {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  );
}

export function HowItWorks() {
  const ref = useRef<HTMLOListElement>(null);
  const [visible, setVisible] = useState(false);
  const [phase, setPhase] = useState(0);
  const reduced = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.3 });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || reduced) return;
    const id = setTimeout(() => setPhase((current) => (current + 1) % STEPS.length), STEP_MS[phase]);
    return () => clearTimeout(id);
  }, [visible, reduced, phase]);

  const active = (step: number) => reduced || phase === step;
  const split = reduced || phase >= 1;
  const delivered = reduced || phase === 2;

  return (
    <div className="mt-3 w-full min-w-0 max-w-2xl rounded-2xl border border-zinc-800 bg-zinc-950/60 p-5">
      <p className="text-xs font-semibold tracking-wider text-cyan-300 uppercase">How it works</p>
      <ol ref={ref} className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-3">
        {STEPS.map((step, index) => (
          <li key={step.title} className="relative flex w-full min-w-0 flex-col items-center gap-3 px-1 text-center">
            <div className="flex h-20 items-center" aria-hidden>
              {index === 0 && <DocumentVisual active={active(0)} />}
              {index === 1 && <ChunkVisual active={active(1)} split={split} />}
              {index === 2 && <ChunksVisual delivered={delivered} />}
            </div>
            {index < STEPS.length - 1 && (
              <span
                className="absolute top-10 right-[calc(-50%+2.5rem)] left-[calc(50%+2.5rem)] hidden border-t border-dashed border-zinc-700 sm:block"
                aria-hidden
              >
                {!reduced && phase === index + 1 && (
                  <span className="animate-flow absolute -top-[3.5px] h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px] shadow-cyan-400" />
                )}
              </span>
            )}
            <div className="flex w-full flex-col gap-1">
              <span
                className={`text-sm font-medium transition-colors duration-500 ${active(index) ? "text-cyan-200" : "text-zinc-300"}`}
              >
                <span className="mr-1.5 text-zinc-500">{index + 1}.</span>
                {step.title}
              </span>
              <span className="text-xs leading-snug text-zinc-500">{step.text}</span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Page({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <div
      className={`flex h-20 w-16 flex-col justify-center gap-1.5 rounded-lg border bg-zinc-900 p-2 transition-all duration-500 ${
        active ? "-translate-y-0.5 border-cyan-400/60 shadow-[0_0_24px_-6px] shadow-cyan-400/50" : "border-zinc-700"
      }`}
    >
      {children}
    </div>
  );
}

function Line({ width = "w-full", tone = "bg-zinc-600" }: { width?: string; tone?: string }) {
  return <span className={`block h-1 rounded-full transition-colors duration-500 ${width} ${tone}`} />;
}

function DocumentVisual({ active }: { active: boolean }) {
  return (
    <Page active={active}>
      <Line width="w-2/3" tone="bg-zinc-400" />
      <Line />
      <Line width="w-11/12" />
      <Line />
      <Line width="w-3/4" />
      <Line width="w-11/12" />
      <Line width="w-1/2" />
    </Page>
  );
}

const SPLIT_OFFSET = ["-translate-y-1", "", "translate-y-1"];

function ChunkVisual({ active, split }: { active: boolean; split: boolean }) {
  return (
    <Page active={active}>
      {CHUNKS.map((chunk, index) => (
        <div
          key={chunk.edge}
          className={`flex flex-col gap-1 border-l-2 pl-1 transition-all duration-500 ${
            split ? `${chunk.edge} ${SPLIT_OFFSET[index]}` : "border-transparent"
          }`}
        >
          <Line tone={split ? chunk.line : "bg-zinc-600"} />
          <Line width="w-3/4" tone={split ? chunk.line : "bg-zinc-600"} />
        </div>
      ))}
    </Page>
  );
}

function ChunksVisual({ delivered }: { delivered: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      {CHUNKS.map((chunk, index) => (
        <div
          key={chunk.edge}
          style={{ transitionDelay: delivered ? `${index * 150}ms` : "0ms" }}
          className={`flex h-5 w-16 items-center gap-1 rounded-md border px-1.5 transition-all duration-500 ${chunk.card} ${
            delivered ? "translate-x-0 opacity-100" : "translate-x-3 opacity-0"
          }`}
        >
          <span className="font-mono text-[9px] leading-none text-zinc-400">{"{}"}</span>
          <span className={`h-1 flex-1 rounded-full ${chunk.line}`} />
        </div>
      ))}
    </div>
  );
}
