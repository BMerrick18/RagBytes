"use client";

import { useEffect, useId, useState } from "react";
import { CollapseButton } from "@/components/CollapseButton";
import { DEMO_CV, DEMO_TIERS, type DemoChunk } from "@/lib/cv-demo";
import { SAMPLE_DOCUMENT } from "@/lib/sample";
import { formatNumber } from "@/lib/stats";
import { TIERS } from "@/lib/tiers";

const STEP_MS = 900;

const TONES = [
  {
    block: "border-cyan-400 bg-cyan-400/10",
    dot: "bg-cyan-400",
    card: "border-cyan-400/40",
  },
  {
    block: "border-violet-400 bg-violet-400/10",
    dot: "bg-violet-400",
    card: "border-violet-400/40",
  },
  {
    block: "border-amber-400 bg-amber-400/10",
    dot: "bg-amber-400",
    card: "border-amber-400/40",
  },
  {
    block: "border-emerald-400 bg-emerald-400/10",
    dot: "bg-emerald-400",
    card: "border-emerald-400/40",
  },
  {
    block: "border-pink-400 bg-pink-400/10",
    dot: "bg-pink-400",
    card: "border-pink-400/40",
  },
  {
    block: "border-lime-400 bg-lime-400/10",
    dot: "bg-lime-400",
    card: "border-lime-400/40",
  },
  {
    block: "border-sky-400 bg-sky-400/10",
    dot: "bg-sky-400",
    card: "border-sky-400/40",
  },
  {
    block: "border-orange-400 bg-orange-400/10",
    dot: "bg-orange-400",
    card: "border-orange-400/40",
  },
];

function tone(index: number) {
  return TONES[index % TONES.length];
}

export function ChunkingDemo({ tier, startOpen = false }: { tier: string; startOpen?: boolean }) {
  const [shown, setShown] = useState(tier);
  const [followedTier, setFollowedTier] = useState(tier);
  const [step, setStep] = useState(0);
  const [open, setOpen] = useState(startOpen);
  const bodyId = useId();
  const { chunks, illustration, explanation } = DEMO_TIERS[shown];
  const done = step >= chunks.length;

  if (tier !== followedTier) {
    setFollowedTier(tier);
    setShown(tier);
    setStep(0);
  }

  useEffect(() => {
    if (!open || done) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const id = setTimeout(() => setStep(reduced ? chunks.length : step + 1), step === 0 ? 300 : STEP_MS);
    return () => clearTimeout(id);
  }, [open, step, done, chunks.length, shown]);

  function show(id: string) {
    setShown(id);
    setStep(0);
  }

  function toggle() {
    setOpen(!open);
    setStep(0);
  }

  const sized = chunks.filter((chunk) => chunk.chars !== undefined);
  const average = sized.length ? sized.reduce((sum, chunk) => sum + chunk.chars!, 0) / sized.length : 0;

  return (
    <div className="flex w-full min-w-0 flex-col gap-5 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h3 className="font-semibold text-zinc-100">See how each tier chunks a document</h3>
          <p className="text-sm text-zinc-400">Watch the sample report being split, one chunk at a time.</p>
        </div>
        {open && (
          <div
            role="tablist"
            aria-label="Tier to animate"
            className="flex flex-wrap gap-1 rounded-lg bg-zinc-950/60 p-1"
          >
            {TIERS.map((option) => (
              <button
                key={option.id}
                type="button"
                role="tab"
                aria-selected={option.id === shown}
                onClick={() => show(option.id)}
                className={`rounded-md px-3 py-3 text-sm font-medium transition-colors md:py-1.5 ${
                  option.id === shown ? "bg-zinc-800 text-cyan-200" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {option.name}
                {!option.available && (
                  <span className="ml-1.5 text-[10px] uppercase tracking-wider text-zinc-500">soon</span>
                )}
              </button>
            ))}
          </div>
        )}
        <div className="hidden lg:block">
          <CollapseButton open={open} onToggle={toggle} controls={bodyId} />
        </div>
      </div>

      {open && (
        <div id={bodyId} className="flex flex-col gap-5">
          <p className="text-sm leading-relaxed text-zinc-300">{explanation}</p>

          <div className="grid min-w-0 grid-cols-1 items-start gap-5 md:grid-cols-2">
            <DocumentView />

            <div className="flex min-w-0 flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <p className="text-zinc-400" aria-live="polite">
                  <span className="font-semibold text-zinc-100">{Math.min(step, chunks.length)}</span> of{" "}
                  {chunks.length} chunks
                  {sized.length > 0 && done && <> · average {formatNumber(Math.round(average))} characters</>}
                </p>
                <button
                  type="button"
                  onClick={() => setStep(0)}
                  disabled={!done}
                  className="rounded-md px-2.5 py-3 font-medium text-cyan-300 transition-colors hover:bg-zinc-800 disabled:cursor-default disabled:text-zinc-600 disabled:hover:bg-transparent md:py-1"
                >
                  {done ? "Replay" : "Chunking…"}
                </button>
              </div>
              {illustration && (
                <p className="rounded-lg border border-dashed border-zinc-700 px-3 py-2 text-xs text-zinc-400">
                  {TIERS.find((option) => option.id === shown)?.available
                    ? "A sketch of the idea. An upload uses live embeddings, and a chunk stays inside its heading."
                    : "Coming soon. This is an illustration of what the tier will do, not real output."}
                </p>
              )}
              <ol className="flex flex-col gap-2">
                {chunks.map((chunk, index) => (
                  <ChunkCard key={`${shown}-${index}`} chunk={chunk} index={index} lit={index < step} />
                ))}
              </ol>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function listItems(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim().replace(/^(?:- |\d+\. )/, ""))
    .filter(Boolean);
}

function showSectionHeading(index: number, force: boolean) {
  const section = DEMO_CV.sections[index];
  const previous = DEMO_CV.sections[index - 1];
  if (!force && section.heading === DEMO_CV.title) return false;
  return force || section.heading !== previous?.heading;
}

function DocumentView() {
  return (
    <div aria-hidden className="flex min-w-0 flex-col gap-3 rounded-xl bg-zinc-950/70 p-4 ring-1 ring-zinc-800">
      <p className="min-w-0 break-words text-xs font-semibold uppercase tracking-wider text-zinc-500">
        {SAMPLE_DOCUMENT.name}
      </p>
      <article className="flex flex-col gap-3">
        <h4 className="text-lg font-semibold text-zinc-100">{DEMO_CV.title}</h4>
        {DEMO_CV.sections.map((_, index) => (
          <SectionBody key={index} index={index} showHeading={showSectionHeading(index, false)} />
        ))}
      </article>
    </div>
  );
}

function SectionBody({ index, showHeading }: { index: number; showHeading: boolean }) {
  const section = DEMO_CV.sections[index];
  return (
    <div className="flex flex-col gap-1.5">
      {showHeading && <h5 className="text-sm font-semibold text-zinc-100">{section.heading}</h5>}
      {section.kind === "list" ? (
        <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed text-zinc-300">
          {listItems(section.text).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm leading-relaxed text-zinc-300">{section.text}</p>
      )}
    </div>
  );
}

function ChunkText({ text, sections }: { text: string; sections: number[] }) {
  const headings = new Set(sections.map((index) => DEMO_CV.sections[index].heading));
  headings.add(DEMO_CV.title);
  const lines = text.split("\n");
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap text-zinc-300">
      {lines.map((line, index) => (
        <span key={index}>
          {index > 0 && "\n"}
          {headings.has(line) ? <span className="font-semibold text-zinc-100">{line}</span> : line}
        </span>
      ))}
    </p>
  );
}

function ChunkCard({ chunk, index, lit }: { chunk: DemoChunk; index: number; lit: boolean }) {
  return (
    <li
      className={`flex flex-col gap-2 rounded-lg border p-3 transition-colors duration-500 motion-reduce:transition-none ${
        lit ? tone(index).block : "border-zinc-800 bg-zinc-950/40"
      }`}
    >
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex items-center gap-2 font-semibold text-zinc-100">
          <span className={`h-2.5 w-2.5 rounded-full ${tone(index).dot}`} />
          Chunk {index + 1}
          {chunk.topic && <span className="font-normal text-zinc-400">· {chunk.topic}</span>}
        </span>
        {chunk.chars !== undefined && (
          <span className="shrink-0 text-xs text-zinc-500">{formatNumber(chunk.chars)} characters</span>
        )}
      </div>
      {chunk.text ? (
        <ChunkText text={chunk.text} sections={chunk.sections} />
      ) : (
        <div className="flex flex-col gap-2">
          {chunk.sections.map((section, offset) => (
            <SectionBody key={section} index={section} showHeading={showSectionHeading(section, offset === 0)} />
          ))}
        </div>
      )}
      {chunk.why && (
        <p className="text-xs leading-relaxed text-zinc-400">
          <span className="font-semibold text-amber-300">Why </span>
          {chunk.why}
        </p>
      )}
      {chunk.summary && (
        <div className="flex flex-col gap-1.5 border-t border-zinc-800 pt-2">
          <p className="text-xs leading-relaxed text-zinc-300">
            <span className="font-semibold text-cyan-300">Summary </span>
            {chunk.summary}
          </p>
          <div className="flex flex-wrap gap-1">
            {chunk.keywords?.map((keyword) => (
              <span key={keyword} className="rounded-full bg-cyan-400/10 px-2 py-0.5 text-[11px] text-cyan-200">
                {keyword}
              </span>
            ))}
          </div>
        </div>
      )}
    </li>
  );
}

